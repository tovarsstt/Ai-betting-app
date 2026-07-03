import express from 'express';
// @ts-expect-error - no types
import cors from 'cors';
import dotenv from 'dotenv';
import { spawn } from 'child_process';
import Anthropic from '@anthropic-ai/sdk';
import path from 'path';
import { fileURLToPath } from 'url';
import { readFileSync, writeFileSync } from 'fs';
import { impliedProb, devig, toDecimal, marginToWinProb, normalCDF } from './src/utils/mathUtils.js';
import { parseJSON, parseOddsForTeams, parseMatchupsFromOdds, parseSelectionIdentity } from './src/utils/parsers.js';
import { getCached, setCache } from './src/utils/cache.js';
import { loadLedger, addPick, settlePick, stampClosingOdds, computeStats, hasPendingDuplicate } from './src/utils/ledger.js';
import { findClose, pendingNeedingClose, inCaptureWindow, type CaptureEvent } from './src/utils/clvCapture.js';
import cron from 'node-cron';
import { getBettingHeuristics, getSportBetContext, getShortHeuristics } from './src/prompts/heuristics.js';
import { getSharpIdentity } from './src/prompts/identity.js';
import { SPORT_KEYS } from './src/services/oddsService.js';
import { ArbitrageService, type ArbitrageOpportunity } from './src/services/arbitrageService.js';
import type { SGPLeg, SwarmAgentData, SwarmFinalPayload, PoissonBoard, SimHitRate, TeamFitRating, PickGrade, AlphaSheetItem, AlphaSheetContainer, ParlayLeg, ParlayBlock, ParlaysPayload } from './src/types/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '.env'), override: true });

// ── Model weights — hot-reloaded every 30 min ─────────────────────────────────
interface ModelWeights {
  math_weight: number;
  sentiment_weight: number;
  dissonance_threshold: number;
  sport_confidence: Record<string, unknown>;
  last_updated: string;
}
function loadModelWeights(): ModelWeights {
  try {
    const raw = readFileSync(path.resolve(__dirname, 'data/model_weights.json'), 'utf8');
    return JSON.parse(raw) as ModelWeights;
  } catch {
    return { math_weight: 0.7, sentiment_weight: 0.3, dissonance_threshold: 8.0, sport_confidence: {}, last_updated: 'default' };
  }
}
let MODEL_WEIGHTS = loadModelWeights();
setInterval(() => { MODEL_WEIGHTS = loadModelWeights(); }, 30 * 60 * 1000);

const app = express();
const port = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json({ limit: '1mb' }));

// ── Simple in-memory rate limit ───────────────────────────────────────────────
const rateCounts = new Map<string, { count: number; reset: number }>();
function rateLimit(req: express.Request, max: number, windowMs: number): boolean {
  const ip = req.ip || req.socket?.remoteAddress || req.headers['x-forwarded-for'] as string || 'fallback';
  const now = Date.now();
  const entry = rateCounts.get(ip);
  if (!entry || now > entry.reset) {
    rateCounts.set(ip, { count: 1, reset: now + windowMs });
    return false;
  }
  entry.count++;
  return entry.count > max;
}

// ── ESPN Historical Data — 100% free, no API key, no signup ──────────────────
// Uses ESPN's undocumented public JSON endpoints (same ones powering espn.com)
// Returns W/L records, home/away splits, recent form, standings — all real data.

const ESPN_BASE = 'https://site.api.espn.com/apis/site/v2/sports';
const ESPN_CORE = 'https://sports.core.api.espn.com/v2/sports';

// Sport slug mapping for ESPN endpoints
const ESPN_SPORT_SLUG: Record<string, { sport: string; league: string }> = {
  NBA:    { sport: 'basketball', league: 'nba' },
  WNBA:   { sport: 'basketball', league: 'wnba' },
  NFL:    { sport: 'football',   league: 'nfl' },
  MLB:    { sport: 'baseball',   league: 'mlb' },
  NHL:    { sport: 'hockey',     league: 'nhl' },
  SOCCER: { sport: 'soccer',     league: 'fifa.world' },
};

interface ESPNTeam { id: string; displayName: string; abbreviation: string; }

// Cache team list per sport (changes rarely)
async function getESPNTeams(sport: string): Promise<ESPNTeam[]> {
  const slug = ESPN_SPORT_SLUG[sport];
  if (!slug) return [];
  const cacheKey = `espn_teams:${sport}`;
  const cached = getCached(cacheKey);
  if (cached) return cached as ESPNTeam[];
  try {
    const res = await fetch(`${ESPN_BASE}/${slug.sport}/${slug.league}/teams`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return [];
    const data = await res.json() as {
      sports?: Array<{ leagues?: Array<{ teams?: Array<{ team: ESPNTeam }> }> }>;
    };
    const teams = (data.sports?.[0]?.leagues?.[0]?.teams ?? []).map(t => t.team);
    setCache(cacheKey, teams, 24 * 60 * 60 * 1000); // 24h — team list is stable
    return teams;
  } catch { return []; }
}

// Fuzzy match team name → ESPN team ID
function matchTeamId(name: string, teams: ESPNTeam[]): string | null {
  if (!name) return null;
  const n = name.toLowerCase();
  // Exact display name match first
  let match = teams.find(t => t.displayName.toLowerCase() === n);
  if (match) return match.id;
  // Partial match on last word (city or nickname)
  const words = n.split(/\s+/);
  for (const word of words.reverse()) {
    if (word.length < 3) continue;
    match = teams.find(t =>
      t.displayName.toLowerCase().includes(word) ||
      t.abbreviation.toLowerCase() === word
    );
    if (match) return match.id;
  }
  return null;
}

// Fetch W/L record + home/away split for a team from ESPN standings
async function fetchESPNTeamRecord(sport: string, teamId: string): Promise<string> {
  const slug = ESPN_SPORT_SLUG[sport];
  if (!slug || !teamId) return '';
  const yr = new Date().getFullYear();
  const cacheKey = `espn_record:${sport}:${teamId}:${yr}`;
  const cached = getCached(cacheKey);
  if (cached) return cached as string;
  try {
    const res = await fetch(
      `https://site.api.espn.com/apis/v2/sports/${slug.sport}/${slug.league}/standings?season=${yr}`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return '';
    const data = await res.json() as {
      children?: Array<{
        standings?: {
          entries?: Array<{
            team: { id: string; displayName: string };
            stats: Array<{ name: string; displayValue: string }>;
          }>;
        };
      }>;
    };
    // Search all conference groups
    for (const group of (data.children ?? [])) {
      const entry = group.standings?.entries?.find(e => e.team.id === teamId);
      if (!entry) continue;
      const s = Object.fromEntries(entry.stats.map(x => [x.name, x.displayValue]));
      const line = [
        `${entry.team.displayName}`,
        s.wins && s.losses ? `Record: ${s.wins}-${s.losses}` : '',
        s.Home ? `Home: ${s.Home}` : '',
        s.Road ? `Away: ${s.Road}` : '',
        s.pointsFor ? `PPG: ${s.pointsFor}` : '',
        s.pointsAgainst ? `OPP PPG: ${s.pointsAgainst}` : '',
        s.streak ? `Streak: ${s.streak}` : '',
      ].filter(Boolean).join(' | ');
      setCache(cacheKey, line, 3 * 60 * 60 * 1000); // 3h
      return line;
    }
    return '';
  } catch { return ''; }
}

// Fetch last 5 game results for a team (real scores, W/L)
async function fetchESPNRecentForm(sport: string, teamId: string): Promise<string> {
  const slug = ESPN_SPORT_SLUG[sport];
  if (!slug || !teamId) return '';
  const cacheKey = `espn_form:${sport}:${teamId}`;
  const cached = getCached(cacheKey);
  if (cached) return cached as string;
  try {
    const yr = new Date().getFullYear();
    const res = await fetch(
      `${ESPN_BASE}/${slug.sport}/${slug.league}/teams/${teamId}/schedule?season=${yr}`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return '';
    const data = await res.json() as {
      events?: Array<{
        name: string;
        date: string;
        competitions?: Array<{
          competitors?: Array<{
            id: string; homeAway: string; winner: boolean;
            score?: { displayValue: string };
            team: { displayName: string };
          }>;
        }>;
      }>;
    };
    // Filter to completed games, take last 5
    const completed = (data.events ?? []).filter(e => {
      const comp = e.competitions?.[0]?.competitors?.[0];
      return comp?.score?.displayValue && comp.score.displayValue !== '0';
    }).slice(-5);

    if (!completed.length) return '';

    const lines = completed.map(e => {
      const comps = e.competitions?.[0]?.competitors ?? [];
      const us = comps.find(c => c.id === teamId);
      const them = comps.find(c => c.id !== teamId);
      if (!us || !them) return null;
      const result = us.winner ? 'W' : 'L';
      const loc = us.homeAway === 'home' ? 'vs' : '@';
      return `${result} ${loc} ${them.team.displayName} ${us.score?.displayValue ?? '?'}-${them.score?.displayValue ?? '?'}`;
    }).filter(Boolean);

    const block = `Last ${lines.length} games: ${lines.join(', ')}`;
    setCache(cacheKey, block, 2 * 60 * 60 * 1000); // 2h
    return block;
  } catch { return ''; }
}

// Master function — assembles real ESPN historical context for a matchup
// Zero external API keys needed. Pure ESPN public data.
async function fetchHistoricalContext(sport: string, matchup: string): Promise<string> {
  const slug = ESPN_SPORT_SLUG[sport];
  if (!slug) return ''; // Tennis/F1 — ESPN team structure doesn't apply

  const teams = matchup.split(/\s+vs\.?\s+/i).map(t => t.trim()).filter(Boolean);
  const t1 = teams[0] || '';
  const t2 = teams[1] || '';
  if (!t1) return '';

  // Resolve team IDs
  const allTeams = await getESPNTeams(sport);
  const id1 = matchTeamId(t1, allTeams);
  const id2 = t2 ? matchTeamId(t2, allTeams) : null;

  if (!id1 && !id2) return '';

  // Fetch records + recent form in parallel
  const fetches = [
    id1 ? fetchESPNTeamRecord(sport, id1) : Promise.resolve(''),
    id1 ? fetchESPNRecentForm(sport, id1) : Promise.resolve(''),
    id2 ? fetchESPNTeamRecord(sport, id2) : Promise.resolve(''),
    id2 ? fetchESPNRecentForm(sport, id2) : Promise.resolve(''),
  ];
  const [rec1, form1, rec2, form2] = await Promise.all(fetches);

  const lines: string[] = [];
  if (rec1)  lines.push(`${t1} — ${rec1}`);
  if (form1) lines.push(`${t1} — ${form1}`);
  if (rec2)  lines.push(`${t2} — ${rec2}`);
  if (form2) lines.push(`${t2} — ${form2}`);

  if (!lines.length) return '';
  return [
    `📊 HISTORICAL DATA — ESPN OFFICIAL (free, no key — cite as [ESPN RECORDS])`,
    `Source: ESPN public API — real ${sport} season data`,
    ...lines,
    `⚠️ ONLY cite numbers that appear VERBATIM above.`,
  ].join('\n');
}

// ── Live Odds API ─────────────────────────────────────────────────────────────
const ODDS_API_KEY = process.env.ODDS_API_KEY || "";
const ODDS_API_BASE = "https://api.the-odds-api.com/v4";

// SPORT_KEYS — imported from src/services/oddsService.ts

interface OddsEvent {
  id: string;
  sport_key: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: Array<{
    key: string;
    markets: Array<{
      key: string;
      outcomes: Array<{ name: string; price: number; point?: number }>;
    }>;
  }>;
}

// Active sport keys from the free /sports endpoint (0 quota cost, cached 12h).
// Lets fetchLiveOdds skip out-of-season keys automatically — no more stale-key bugs.
async function getActiveSportKeys(): Promise<Set<string> | null> {
  const cached = getCached('odds:active-keys');
  if (cached) return cached as Set<string>;
  try {
    const res = await fetch(`${ODDS_API_BASE}/sports/?apiKey=${ODDS_API_KEY}`, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return null;
    const sports = await res.json() as Array<{ key: string; active: boolean }>;
    const activeSet = new Set(sports.filter(s => s.active).map(s => s.key));
    setCache('odds:active-keys', activeSet, 12 * 60 * 60 * 1000);
    return activeSet;
  } catch {
    return null; // on failure, caller falls back to the full configured list
  }
}

// Accent-stripping normalizer + Spanish→English WC team aliases for game search
const normTeam = (s: string): string =>
  s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const ES_TEAM_ALIASES: Record<string, string> = {
  'sudafrica': 'south africa', 'corea del sur': 'south korea', 'corea': 'south korea',
  'republica checa': 'czech republic', 'checa': 'czech', 'alemania': 'germany',
  'francia': 'france', 'espana': 'spain', 'inglaterra': 'england', 'brasil': 'brazil',
  'suiza': 'switzerland', 'catar': 'qatar', 'qatar': 'qatar', 'croacia': 'croatia',
  'japon': 'japan', 'marruecos': 'morocco', 'paises bajos': 'netherlands',
  'holanda': 'netherlands', 'estados unidos': 'united states', 'eeuu': 'united states',
  'escocia': 'scotland', 'egipto': 'egypt', 'nueva zelanda': 'new zealand',
  'noruega': 'norway', 'costa de marfil': 'ivory coast', 'belgica': 'belgium',
  'italia': 'italy', 'portugal': 'portugal', 'argelia': 'algeria', 'tunez': 'tunisia',
  'arabia saudita': 'saudi arabia', 'iran': 'iran', 'grecia': 'greece',
  'turquia': 'turkiye', 'austria': 'austria', 'polonia': 'poland',
};

// Tennis surface from the sport_key — surface is the single biggest betting
// variable (it drives the model). Keyword-matched so it survives exact-key spelling
// drift across the ~60 tour stops; returns an honest "unknown" rather than a wrong
// guess (a fabricated surface would mis-price the whole match).
function tennisSurface(key: string): string {
  const MAJORS: Record<string, string> = {
    'tennis_atp_french_open':  '🏟️ ROLAND GARROS — CLAY (slowest, topspin-dominant, baseline grinders excel, big servers fade)',
    'tennis_wta_french_open':  '🏟️ ROLAND GARROS — CLAY (slowest, topspin-dominant, physical endurance key)',
    'tennis_atp_wimbledon':    '🏟️ WIMBLEDON — GRASS (fastest, serve+volley, big servers/net players dominate, clay specialists fade)',
    'tennis_wta_wimbledon':    '🏟️ WIMBLEDON — GRASS (fastest, serve dominant, low bounce, aggressive baseliners)',
    'tennis_atp_us_open':      '🏟️ US OPEN — HARD (medium-fast, night sessions faster under lights, loud crowd)',
    'tennis_wta_us_open':      '🏟️ US OPEN — HARD (medium-fast, night session crowd/momentum factor)',
    'tennis_atp_aus_open':     '🏟️ AUSTRALIAN OPEN — HARD (medium-slow Plexicushion, January heat policy, long rallies)',
    'tennis_wta_aus_open':     '🏟️ AUSTRALIAN OPEN — HARD (medium-slow Plexicushion, heat delays possible)',
  };
  if (MAJORS[key]) return MAJORS[key];
  const k = key.toLowerCase();
  const GRASS = '🌱 GRASS — fast, low bounce; big servers & aggressive returners overperform, clay specialists fade.';
  const CLAY  = '🟧 CLAY — slowest, high bounce; topspin grinders & stamina win, big servers fade.';
  const HARD  = '🟦 HARD — medium-fast, true bounce; all-court players & big hitters favored.';
  const has = (...w: string[]): boolean => w.some(x => k.includes(x));
  if (k.includes('stuttgart')) return k.includes('wta') ? CLAY : GRASS; // ATP grass, WTA clay
  if (has('wimbledon', 'queens', 'eastbourne', 'mallorca', 'halle', 'homburg', 'hertog', 'birmingham', 'nottingham', 'berlin', 'newport')) return GRASS;
  if (has('french', 'roland', 'monte_carlo', 'madrid', 'rome', 'barcelona', 'hamburg', 'bastad', 'gstaad', 'kitzbuhel', 'umag', 'estoril', 'munich', 'geneva', 'cordoba', 'houston', 'rio')) return CLAY;
  if (has('us_open', 'aus_open', 'australian', 'indian_wells', 'miami', 'cincinnati', 'canada', 'toronto', 'montreal', 'dubai', 'doha', 'acapulco', 'shanghai', 'beijing', 'tokyo', 'vienna', 'basel', 'turin', 'washington', 'adelaide', 'brisbane')) return HARD;
  return '⚠️ surface not auto-identified for this event — CONFIRM the surface before pricing (it is the model\'s biggest input).';
}

async function fetchLiveOdds(sport: string, gameQuery?: string): Promise<string> {
  if (!ODDS_API_KEY) return "Odds API key not configured.";
  const configuredKeys = SPORT_KEYS[sport] || SPORT_KEYS.NBA;
  if (configuredKeys.length === 0) return `No odds API coverage for ${sport}.`;

  // Skip out-of-season keys when the active list is available
  const activeKeys = await getActiveSportKeys();
  let sportKeys = activeKeys
    ? configuredKeys.filter(k => activeKeys.has(k))
    : configuredKeys;

  // TENNIS: cover the WHOLE tour — every active ATP/WTA tournament, not a fixed list
  if (sport === 'TENNIS' && activeKeys) {
    const tennisActive = [...activeKeys]
      .filter(k => k.startsWith('tennis_') && !k.includes('winner'))
      .sort()
      .slice(0, 6); // quota guard: max 6 tournaments per scan
    if (tennisActive.length) sportKeys = tennisActive;
  }

  if (sportKeys.length === 0) return `No ${sport} markets in season right now (all configured keys inactive).`;

  const results: string[] = [];
  const apiErrors: string[] = [];

  let isFirstKey = true;
  for (const key of sportKeys) {
    // Throttle multi-key sports (tennis/soccer) — burst requests trigger HTTP 429
    if (!isFirstKey) await new Promise(r => setTimeout(r, 400));
    isFirstKey = false;
    try {
      // NOTE: alternate_spreads/alternate_totals are NOT supported on the bulk
      // /sports/{key}/odds endpoint (422 INVALID_MARKET) — only per-event endpoint.
      const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
      const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        console.error(`Odds API ${res.status} for ${key}: ${body.slice(0, 200)}`);
        apiErrors.push(`${key}: HTTP ${res.status}`);
        continue;
      }

      const events = await res.json() as OddsEvent[];
      if (!Array.isArray(events) || events.length === 0) continue;

      // Inject tennis surface header before listing events for this tournament
      if (key.startsWith('tennis_')) results.push(tennisSurface(key));

      // Filter by game query if provided.
      // Accent-normalized + Spanish team aliases: "México vs Sudáfrica" must
      // find "Mexico vs South Africa" — a miss here made the engine analyze
      // a DIFFERENT game from the leftover fixtures context.
      const matchesQuery = (e: OddsEvent, q: string): boolean => {
        const tokens = [normTeam(q), ...normTeam(q).split(/\s+vs?\s+|\s+@\s+/i).map(t => t.trim())]
          .filter(t => t.length >= 3)
          .map(t => ES_TEAM_ALIASES[t] ?? t);
        const home = normTeam(e.home_team);
        const away = normTeam(e.away_team);
        return tokens.some(t => home.includes(t) || away.includes(t));
      };
      const filtered = gameQuery
        ? events.filter(e => matchesQuery(e, gameQuery))
        : events.slice(0, 8); // max 8 games to keep prompt lean

      if (gameQuery && filtered.length === 0) {
        apiErrors.push(`match "${gameQuery}" not found in ${key}`);
        continue;
      }

      for (const ev of filtered) {
        const gameTime = new Date(ev.commence_time).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' });
        const pinnacle = ev.bookmakers.find(b => b.key === 'pinnacle') || ev.bookmakers[0];
        if (!pinnacle) continue;

        const lines: string[] = [`${ev.away_team} @ ${ev.home_team} — ${gameTime} ET`];

        const altSpreads: string[] = [];
        const altTotals: string[] = [];
        for (const market of pinnacle.markets) {
          if (market.key === 'h2h') {
            const ml = market.outcomes.map(o => `${o.name} ML ${o.price > 0 ? '+' : ''}${o.price}`).join(' | ');
            lines.push(`  Moneyline: ${ml}`);
            // Devig across ALL outcomes — soccer h2h is 3-way (home/draw/away),
            // so devigging only the first two prices mis-prices every WC match.
            const raws = market.outcomes.map(o => ({ name: o.name, p: impliedProb(o.price) }));
            const rawSum = raws.reduce((s, r) => s + r.p, 0);
            if (rawSum > 0 && raws.length >= 2) {
              const devigged = raws.map(r => `${r.name} ${(r.p / rawSum * 100).toFixed(1)}%`).join(' | ');
              lines.push(`  → Implied(devigged, ${raws.length}-way): ${devigged} | Book vig: ${((rawSum - 1) * 100).toFixed(1)}%`);
            }
          } else if (market.key === 'spreads') {
            const sp = market.outcomes.map(o => `${o.name} ${o.point && o.point > 0 ? '+' : ''}${o.point} (${o.price > 0 ? '+' : ''}${o.price})`).join(' | ');
            lines.push(`  Spread: ${sp}`);
            // Devig spread juice
            if (market.outcomes.length === 2) {
              const [s1, s2] = market.outcomes;
              const sp1r = impliedProb(s1.price), sp2r = impliedProb(s2.price);
              const sdv  = devig(sp1r, sp2r);
              lines.push(`  → Spread devigged: ${s1.name} ${(sdv.p1*100).toFixed(1)}% | ${s2.name} ${(sdv.p2*100).toFixed(1)}% | Vig: ${sdv.vig.toFixed(1)}%`);
            }
          } else if (market.key === 'totals') {
            const tot = market.outcomes.map(o => `${o.name} ${o.point} (${o.price > 0 ? '+' : ''}${o.price})`).join(' | ');
            lines.push(`  Total: ${tot}`);
          } else if (market.key === 'alternate_spreads') {
            const alts = market.outcomes.map(o => `${o.name} ${o.point && o.point > 0 ? '+' : ''}${o.point} (${o.price > 0 ? '+' : ''}${o.price})`);
            for (let i = 0; i < alts.length; i += 2) altSpreads.push(alts.slice(i, i + 2).join(' | '));
          } else if (market.key === 'alternate_totals') {
            const alts = market.outcomes.map(o => `${o.name} ${o.point} (${o.price > 0 ? '+' : ''}${o.price})`);
            for (let i = 0; i < alts.length; i += 2) altTotals.push(alts.slice(i, i + 2).join(' | '));
          }
        }
        if (altSpreads.length) lines.push(`  Alt Spreads: ${altSpreads.slice(0, 4).join(' // ')}`);
        if (altTotals.length) lines.push(`  Alt Totals: ${altTotals.slice(0, 4).join(' // ')}`);
        results.push(lines.join('\n'));
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`Odds fetch failed for ${key}: ${msg}`);
      apiErrors.push(`${key}: ${msg}`);
    }
  }

  if (results.length === 0) {
    if (gameQuery && apiErrors.some(e => e.includes('not found'))) {
      return `⛔ REQUESTED MATCH "${gameQuery}" NOT FOUND in ${sport} live odds. ` +
        `DO NOT analyze a different game. Tell the user the match was not found in tonight's slate and to check the team names.`;
    }
    return apiErrors.length
      ? `ODDS API ERROR — not "no games", the API calls failed: ${apiErrors.join(' | ')}`
      : `No live odds available for ${sport} right now.`;
  }

  // Championship strength prior — cached 12h, ~1 credit/sport/day
  const prior = await fetchChampionshipPrior(sport);
  if (prior) results.push(prior);
  return `LIVE ODDS (Pinnacle/DraftKings) — ${sport}:\n${results.join('\n\n')}`;
}

// ── BallDontLie — real NBA player stats + schedule ───────────────────────────
const BDL_KEY = process.env.BALLDONTLIE_API_KEY || "";

type BDLTeam   = { id: number; full_name: string; abbreviation: string };
type BDLGame   = { id: number; home_team: BDLTeam; visitor_team: BDLTeam; status: string };
type BDLPlayer = { id: number; first_name: string; last_name: string; position: string };
type BDLAvg    = { player_id: number; pts: number; reb: number; ast: number; fg_pct: number; fg3_pct: number; games_played: number };
type BDLStat   = { player: { id: number }; pts: number };

async function fetchNBAGamesToday(): Promise<BDLGame[]> {
  if (!BDL_KEY) return [];
  try {
    const today = new Date().toISOString().split('T')[0];
    const res = await fetch(
      `https://api.balldontlie.io/v1/games?dates[]=${today}&per_page=15`,
      { headers: { Authorization: BDL_KEY }, signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return [];
    const data = await res.json() as { data: BDLGame[] };
    return data.data ?? [];
  } catch { return []; }
}

// Real season averages + last-5 pts form for both matchup teams
async function fetchNBAPlayerStats(matchup: string): Promise<string> {
  if (!BDL_KEY) return "";
  try {
    const games = await fetchNBAGamesToday();
    const keywords = matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim());

    const game = games.find(g =>
      keywords.some(kw =>
        g.home_team.full_name.toLowerCase().includes(kw) ||
        g.visitor_team.full_name.toLowerCase().includes(kw) ||
        g.home_team.abbreviation.toLowerCase().includes(kw) ||
        g.visitor_team.abbreviation.toLowerCase().includes(kw)
      )
    );
    if (!game) return "";

    const month  = new Date().getMonth() + 1;
    const season = month >= 10 ? new Date().getFullYear() : new Date().getFullYear() - 1;
    const teams  = [game.home_team, game.visitor_team];
    const blocks: string[] = [];

    for (const team of teams) {
      const pRes = await fetch(
        `https://api.balldontlie.io/v1/players/active?team_ids[]=${team.id}&per_page=12`,
        { headers: { Authorization: BDL_KEY }, signal: AbortSignal.timeout(5000) }
      );
      if (!pRes.ok) continue;
      const pData = await pRes.json() as { data: BDLPlayer[] };
      if (!pData.data?.length) continue;

      const ids      = pData.data.slice(0, 10).map(p => p.id);
      const idParams = ids.map(id => `player_ids[]=${id}`).join('&');

      const [avgRes, recentRes] = await Promise.all([
        fetch(`https://api.balldontlie.io/v1/season_averages?season=${season}&${idParams}`,
          { headers: { Authorization: BDL_KEY }, signal: AbortSignal.timeout(5000) }),
        fetch(`https://api.balldontlie.io/v1/stats?${idParams}&per_page=50&seasons[]=${season}`,
          { headers: { Authorization: BDL_KEY }, signal: AbortSignal.timeout(5000) }),
      ]);

      const avgData    = avgRes.ok    ? (await avgRes.json()    as { data: BDLAvg[]  }).data : [];
      const recentData = recentRes.ok ? (await recentRes.json() as { data: BDLStat[] }).data : [];

      // last-5 pts per player (API returns most-recent first)
      const recentByPlayer = new Map<number, number[]>();
      for (const s of recentData) {
        const arr = recentByPlayer.get(s.player.id) ?? [];
        if (arr.length < 5) { arr.push(s.pts); recentByPlayer.set(s.player.id, arr); }
      }

      const playerMap = new Map(pData.data.map(p => [p.id, p]));
      const top = avgData.sort((a, b) => b.pts - a.pts).slice(0, 6);

      const lines = [`${team.full_name.toUpperCase()}:`];
      for (const avg of top) {
        const p = playerMap.get(avg.player_id);
        if (!p || avg.games_played < 5) continue;
        const recent    = recentByPlayer.get(avg.player_id) ?? [];
        const recentStr = recent.length ? ` | L${recent.length}: ${recent.join(',')}pts` : '';
        lines.push(
          `  ${p.first_name} ${p.last_name}: ${avg.pts.toFixed(1)}PPG ` +
          `${avg.reb.toFixed(1)}RPG ${avg.ast.toFixed(1)}APG ` +
          `${(avg.fg_pct * 100).toFixed(0)}%FG ${(avg.fg3_pct * 100).toFixed(0)}%3P ` +
          `(${avg.games_played}G)${recentStr}`
        );
      }
      if (lines.length > 1) blocks.push(lines.join('\n'));
    }

    if (!blocks.length) return "";
    return `NBA REAL PLAYER STATS (BallDontLie — ${season}-${String(season + 1).slice(2)} season):\n${blocks.join('\n\n')}`;
  } catch { return ""; }
}

async function fetchNBAScheduleToday(): Promise<string> {
  if (!BDL_KEY) return "";
  try {
    const games = await fetchNBAGamesToday();
    if (!games.length) return "";
    return `NBA TODAY: ${games.map(g => `${g.visitor_team.full_name} @ ${g.home_team.full_name} (${g.status})`).join(' | ')}`;
  } catch { return ""; }
}

// ── ESPN Injury Feed (free, no key required) ──────────────────────────────────
const ESPN_INJURY_ROUTES: Record<string, string> = {
  NBA:    "basketball/nba",
  WNBA:   "basketball/wnba",
  NFL:    "football/nfl",
  NHL:    "hockey/nhl",
  MLB:    "baseball/mlb",
  // World Cup uses ESPN's FIFA feed; domestic MLS removed
  SOCCER: "soccer/fifa.world",
};

async function fetchInjuries(sport: string, matchup?: string): Promise<string> {
  const route = ESPN_INJURY_ROUTES[sport.toUpperCase()];
  if (!route) return "";

  // Extract team keywords from matchup string for filtering
  const teamKeywords = matchup
    ? matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim()).filter(Boolean)
    : [];

  function teamMatches(teamName: string): boolean {
    if (teamKeywords.length === 0) return true;
    const t = teamName.toLowerCase();
    return teamKeywords.some(kw => t.includes(kw) || kw.split(" ").some(word => word.length > 3 && t.includes(word)));
  }

  try {
    const url = `https://site.api.espn.com/apis/site/v2/sports/${route}/injuries`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return "";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = await res.json() as Record<string, any>;

    const lines: string[] = [];

    // Shape A: { injuries: [{ team, injuries: [...players] }] }  — NBA/WNBA/NHL
    if (Array.isArray(raw.injuries)) {
      for (const teamObj of raw.injuries) {
        const teamName = teamObj?.team?.displayName || teamObj?.team?.name || "";
        if (!teamMatches(teamName)) continue; // ← only matchup teams
        const players = Array.isArray(teamObj?.injuries) ? teamObj.injuries : [];
        const injured = players
          .filter((p: Record<string, unknown>) => p?.status && p.status !== "Active")
          .map((p: Record<string, unknown>) => {
            const name = (p?.athlete as Record<string, unknown>)?.displayName || "?";
            const status = p?.status || (p?.details as Record<string, unknown>)?.fantasyStatus || "OUT";
            return `${name} (${status})`;
          })
          .slice(0, 8);
        if (injured.length > 0) lines.push(`${teamName}: ${injured.join(", ")}`);
      }
    }
    // Shape B: { items: [{ athlete, status, ... }] }  — some ESPN endpoints
    else if (Array.isArray(raw.items)) {
      for (const item of raw.items.slice(0, 100)) {
        const teamName = item?.team?.displayName || item?.team?.name || "";
        if (!teamMatches(teamName)) continue; // ← only matchup teams
        const name = item?.athlete?.displayName || item?.displayName || "?";
        const status = item?.status || item?.type?.description || "OUT";
        if (status !== "Active") lines.push(`${teamName ? teamName + ": " : ""}${name} (${status})`);
      }
    }

    if (lines.length === 0) return "No injury data found for these two teams.";
    return `INJURY REPORT — ${sport} (ESPN, matchup teams only):\n${lines.join("\n")}`;
  } catch { return ""; }
}

// ── ESPN News Feed ────────────────────────────────────────────────────────────
const ESPN_NEWS_ROUTES: Record<string, string> = {
  NBA: 'basketball/nba', WNBA: 'basketball/wnba',
  NFL: 'football/nfl',   MLB:  'baseball/mlb',
  NHL: 'hockey/nhl',     SOCCER: 'soccer',
  TENNIS: 'tennis',      UFC: 'mma/ufc',
};

async function fetchESPNNews(sport: string, matchup?: string): Promise<string> {
  const route = ESPN_NEWS_ROUTES[sport.toUpperCase()];
  if (!route) return "";
  try {
    const res = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/${route}/news?limit=10`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return "";
    const data = await res.json() as { articles?: Array<{ headline: string; description?: string }> };
    if (!data.articles?.length) return "";

    const keywords = matchup
      ? matchup.toLowerCase().split(/[\s\W]+/).filter(w => w.length > 3)
      : [];

    const relevant = keywords.length
      ? data.articles.filter(a => {
          const txt = (a.headline + ' ' + (a.description ?? '')).toLowerCase();
          return keywords.some(kw => txt.includes(kw));
        })
      : [];

    const articles = (relevant.length ? relevant : data.articles).slice(0, 5);
    return `${sport} NEWS (ESPN):\n${articles.map(a => `• ${a.headline}`).join('\n')}`;
  } catch { return ""; }
}

// ── ESPN Scoreboard — today's schedule for non-NBA sports ────────────────────
const ESPN_SCOREBOARD_ROUTES: Record<string, string> = {
  NFL:    'football/nfl',
  WNBA:   'basketball/wnba',
  NHL:    'hockey/nhl',
  MLB:    'baseball/mlb',
  SOCCER: 'soccer/fifa.world',
  TENNIS: 'tennis/atp',
};

async function fetchESPNScoreboard(sport: string): Promise<string> {
  const route = ESPN_SCOREBOARD_ROUTES[sport.toUpperCase()];
  if (!route) return "";
  try {
    const res = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/${route}/scoreboard`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return "";
    const data = await res.json() as {
      events?: Array<{
        date: string;
        status: { type: { description: string } };
        competitions: Array<{ competitors: Array<{ team: { displayName: string } }> }>;
      }>
    };
    if (!data.events?.length) return "";

    const games = data.events.slice(0, 10).map(ev => {
      const teams = ev.competitions[0]?.competitors?.map(c => c.team.displayName).join(' @ ') ?? '';
      const time  = new Date(ev.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' });
      const st    = ev.status.type.description;
      return `  ${teams} — ${st === 'Scheduled' ? time + ' ET' : st}`;
    });
    return `${sport} TODAY (ESPN):\n${games.join('\n')}`;
  } catch { return ""; }
}

// ── NBA Stats API — Advanced metrics (pace, OffRtg, DefRtg, NetRtg) ─────────
// Works with proper headers. Fetches all 30 teams at once; cached 30 min.
// Season: auto-detect (Oct–Sep spans two calendar years).
const NBA_STATS_HEADERS: Record<string, string> = {
  "Host": "stats.nba.com",
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "en-US,en;q=0.5",
  "Accept-Encoding": "identity",
  "Connection": "keep-alive",
  "Referer": "https://www.nba.com/",
  "Pragma": "no-cache",
  "Cache-Control": "no-cache",
  "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
  "Sec-Ch-Ua-Mobile": "?0",
  "Sec-Fetch-Dest": "empty",
};

interface NBAMetricRow {
  name: string; teamId: number;
  w: number; l: number; wPct: number;
  offRtg: number; defRtg: number; netRtg: number;
  pace: number; astRatio: number; tovPct: number;
}

let nbaMetricsCache: { data: NBAMetricRow[]; expires: number } | null = null;

function currentNBASeason(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1; // 1-12
  return m >= 10 ? `${y}-${String(y + 1).slice(-2)}` : `${y - 1}-${String(y).slice(-2)}`;
}

async function fetchNBAMetricsAll(): Promise<NBAMetricRow[]> {
  if (nbaMetricsCache && Date.now() < nbaMetricsCache.expires) return nbaMetricsCache.data;
  try {
    const season = currentNBASeason();
    const url = `https://stats.nba.com/stats/teamestimatedmetrics?LeagueID=00&Season=${encodeURIComponent(season)}&SeasonType=Regular%20Season`;
    const res = await fetch(url, { signal: AbortSignal.timeout(8000), headers: NBA_STATS_HEADERS });
    if (!res.ok) return [];
    const json = await res.json() as { resultSet: { headers: string[]; rowSet: unknown[][] } };
    const { headers, rowSet } = json.resultSet;
    const idx = (n: string) => headers.indexOf(n);
    const data: NBAMetricRow[] = rowSet.map(r => ({
      name:     r[idx('TEAM_NAME')]    as string,
      teamId:   r[idx('TEAM_ID')]      as number,
      w:        r[idx('W')]            as number,
      l:        r[idx('L')]            as number,
      wPct:     r[idx('W_PCT')]        as number,
      offRtg:   r[idx('E_OFF_RATING')] as number,
      defRtg:   r[idx('E_DEF_RATING')] as number,
      netRtg:   r[idx('E_NET_RATING')] as number,
      pace:     r[idx('E_PACE')]       as number,
      astRatio: r[idx('E_AST_RATIO')]  as number,
      tovPct:   r[idx('E_TM_TOV_PCT')] as number,
    }));
    nbaMetricsCache = { data, expires: Date.now() + 30 * 60 * 1000 };
    return data;
  } catch { return []; }
}

// Adjusted-rating scoring model (industry standard):
//   ExpScore_A = (A.OffRtg × B.DefRtg / leagueAvg) × avgPace / 100
// League avg OffRtg/DefRtg balance at ~113.5 for 2024-25.
const NBA_LEAGUE_AVG_RTG = 113.5;

function nbaExpectedScores(
  homeOff: number, homeDef: number, homePace: number,
  awayOff: number, awayDef: number, awayPace: number
): { homeScore: number; awayScore: number; total: number; margin: number } {
  const avgPace = (homePace + awayPace) / 2;
  const homeScore = (homeOff * awayDef / NBA_LEAGUE_AVG_RTG) * avgPace / 100;
  const awayScore = (awayOff * homeDef / NBA_LEAGUE_AVG_RTG) * avgPace / 100;
  return { homeScore, awayScore, total: homeScore + awayScore, margin: homeScore - awayScore };
}

async function fetchNBAAdvancedStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const allTeams = await fetchNBAMetricsAll();
  if (allTeams.length === 0) return "";

  const lower = matchup.toLowerCase();
  const parts  = lower.split(/\s+(?:vs\.?|@|-)\s+/);

  const findTeam = (query: string): NBAMetricRow | undefined =>
    allTeams.find(t => {
      const n = t.name.toLowerCase();
      return n.includes(query.trim()) ||
             query.trim().split(/\s+/).some(w => w.length > 3 && n.includes(w));
    });

  const found = parts.map(findTeam).filter((t): t is NBAMetricRow => t !== undefined);
  if (found.length < 2) return "";

  // Convention: parts[0] = away team, parts[1] = home team (standard "Away @ Home" format)
  const [away, home] = found;
  const scores = nbaExpectedScores(home.offRtg, home.defRtg, home.pace, away.offRtg, away.defRtg, away.pace);
  const homeWinProb = marginToWinProb(scores.margin);
  const fmt = (n: number) => n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1);

  return [
    `NBA ADVANCED STATS (stats.nba.com — real numbers, cite exactly):`,
    `  Season: ${currentNBASeason()} Regular Season`,
    `  ${away.name}: ${away.w}-${away.l} (${(away.wPct*100).toFixed(0)}%) | OffRtg:${away.offRtg} DefRtg:${away.defRtg} NetRtg:${fmt(away.netRtg)} Pace:${away.pace} TOV%:${(away.tovPct*100).toFixed(1)}%`,
    `  ${home.name}: ${home.w}-${home.l} (${(home.wPct*100).toFixed(0)}%) | OffRtg:${home.offRtg} DefRtg:${home.defRtg} NetRtg:${fmt(home.netRtg)} Pace:${home.pace} TOV%:${(home.tovPct*100).toFixed(1)}%`,
    `  ── Adjusted-Rating Model ──`,
    `  Expected Total: ${scores.total.toFixed(1)} pts  (${away.name} ${scores.awayScore.toFixed(1)} | ${home.name} ${scores.homeScore.toFixed(1)})`,
    `  Expected Margin: ${home.name} ${fmt(scores.margin)} (model win prob: ${home.name} ${(homeWinProb*100).toFixed(1)}% | ${away.name} ${((1-homeWinProb)*100).toFixed(1)}%)`,
    `  Net-Rating edge: ${away.netRtg > home.netRtg ? away.name : home.name} ${fmt(Math.abs(away.netRtg - home.netRtg))} pts advantage`,
  ].join('\n');
}

// Top-10 / Bottom-10 teams by NetRtg — useful for prophet without a specific matchup
async function fetchNBALeagueSnapshot(): Promise<string> {
  const all = await fetchNBAMetricsAll();
  if (all.length === 0) return "";
  const sorted = [...all].sort((a, b) => b.netRtg - a.netRtg);
  const fmt = (n: number) => n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1);
  const row = (t: NBAMetricRow) =>
    `  ${t.name}: ${t.w}-${t.l} | NetRtg:${fmt(t.netRtg)} OffRtg:${t.offRtg} DefRtg:${t.defRtg} Pace:${t.pace}`;
  return [
    `NBA LEAGUE EFFICIENCY (stats.nba.com — ${currentNBASeason()} Regular Season):`,
    `Top 5 by NetRtg:`,
    ...sorted.slice(0, 5).map(row),
    `Bottom 5 by NetRtg:`,
    ...sorted.slice(-5).reverse().map(row),
  ].join('\n');
}

// ── ESPN NBA Team Stats (free, no auth) ─────────────────────────────────────
// Real team PPG / FG% / 3P% / defensive stats for both NBA teams in a matchup.
const ESPN_NBA_TEAM_IDS: Record<string, number> = {
  "atlanta hawks": 1, "hawks": 1, "atl": 1,
  "boston celtics": 2, "celtics": 2, "bos": 2,
  "brooklyn nets": 17, "nets": 17, "bkn": 17,
  "charlotte hornets": 30, "hornets": 30, "cha": 30,
  "chicago bulls": 4, "bulls": 4, "chi": 4,
  "cleveland cavaliers": 5, "cavaliers": 5, "cavs": 5, "cle": 5,
  "dallas mavericks": 6, "mavericks": 6, "mavs": 6, "dal": 6,
  "denver nuggets": 7, "nuggets": 7, "den": 7,
  "detroit pistons": 8, "pistons": 8, "det": 8,
  "golden state warriors": 9, "warriors": 9, "gsw": 9,
  "houston rockets": 10, "rockets": 10, "hou": 10,
  "indiana pacers": 11, "pacers": 11, "ind": 11,
  "la clippers": 12, "clippers": 12, "lac": 12,
  "los angeles clippers": 12,
  "los angeles lakers": 13, "lakers": 13, "lal": 13, "la lakers": 13,
  "memphis grizzlies": 29, "grizzlies": 29, "mem": 29,
  "miami heat": 14, "heat": 14, "mia": 14,
  "milwaukee bucks": 15, "bucks": 15, "mil": 15,
  "minnesota timberwolves": 16, "timberwolves": 16, "wolves": 16, "min": 16,
  "new orleans pelicans": 3, "pelicans": 3, "nop": 3,
  "new york knicks": 18, "knicks": 18, "nyk": 18,
  "oklahoma city thunder": 25, "thunder": 25, "okc": 25,
  "orlando magic": 19, "magic": 19, "orl": 19,
  "philadelphia 76ers": 20, "76ers": 20, "sixers": 20, "phi": 20,
  "phoenix suns": 21, "suns": 21, "phx": 21,
  "portland trail blazers": 22, "trail blazers": 22, "blazers": 22, "por": 22,
  "sacramento kings": 23, "kings": 23, "sac": 23,
  "san antonio spurs": 24, "spurs": 24, "sas": 24,
  "toronto raptors": 28, "raptors": 28, "tor": 28,
  "utah jazz": 26, "jazz": 26, "uta": 26,
  "washington wizards": 27, "wizards": 27, "was": 27,
};

async function fetchNBATeamStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const lower = matchup.toLowerCase();
  const STAT_KEYS = ['avgPoints','fieldGoalPct','threePointPct','avgRebounds','avgAssists','avgTurnovers','avgBlocks','avgSteals'];
  const STAT_LABELS: Record<string,string> = {
    avgPoints:'PPG', fieldGoalPct:'FG%', threePointPct:'3P%',
    avgRebounds:'REB', avgAssists:'AST', avgTurnovers:'TO',
    avgBlocks:'BLK', avgSteals:'STL',
  };

  const extractTeamId = (part: string): number | null => {
    for (const [key, id] of Object.entries(ESPN_NBA_TEAM_IDS)) {
      if (part.includes(key)) return id;
    }
    return null;
  };

  // Try to split matchup into two team names
  const parts = lower.split(/\s+(?:vs\.?|@|-)\s+/);
  const ids = parts.map(extractTeamId).filter((id): id is number => id !== null);
  if (ids.length === 0) return "";

  const lines: string[] = ["NBA TEAM STATS (ESPN — real numbers, cite these):"];
  await Promise.all(ids.slice(0, 2).map(async (teamId) => {
    try {
      const res = await fetch(
        `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/${teamId}/statistics`,
        { signal: AbortSignal.timeout(5000) }
      );
      if (!res.ok) return;
      const data = await res.json() as {
        results: { stats: { categories: Array<{ stats: Array<{ name: string; displayValue: string }> }> } };
        team: { displayName: string };
      };
      const teamName = data.team?.displayName ?? `Team ${teamId}`;
      const stats: Record<string,string> = {};
      for (const cat of data.results.stats.categories) {
        for (const s of cat.stats) {
          if (STAT_KEYS.includes(s.name)) stats[s.name] = s.displayValue;
        }
      }
      const statStr = STAT_KEYS.filter(k => stats[k]).map(k => `${STAT_LABELS[k]}:${stats[k]}`).join(' | ');
      lines.push(`  ${teamName}: ${statStr}`);
    } catch { /* skip if unavailable */ }
  }));

  return lines.length > 1 ? lines.join('\n') : "";
}

// ── MLB Official Stats API (statsapi.mlb.com — free, no auth) ───────────────
// Real pitcher ERA / K9 / WHIP / last-3-starts for both starters tonight.
// Kills hallucinated pitcher stats — every number below is from the MLB API.
type MLBPitcher = { id: number; fullName: string };
type MLBPitchingStat = {
  era: string; strikeOuts: number; whip: string; inningsPitched: string;
  wins: number; losses: number; gamesStarted: number; strikeoutsPer9Inn: string;
};
type MLBGameLogStat = { era: string; strikeOuts: number; inningsPitched: string };

async function fetchMLBPitcherStats(matchup: string): Promise<string> {
  try {
    const today = new Date().toISOString().split('T')[0];
    const schedRes = await fetch(
      `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=${today}&hydrate=probablePitcher(note)`,
      { signal: AbortSignal.timeout(7000) }
    );
    if (!schedRes.ok) return "";
    const sched = await schedRes.json() as {
      dates: Array<{ games: Array<{
        venue: { name: string };
        teams: {
          home: { team: { name: string }; leagueRecord: { wins: number; losses: number }; probablePitcher?: MLBPitcher };
          away: { team: { name: string }; leagueRecord: { wins: number; losses: number }; probablePitcher?: MLBPitcher };
        };
      }> }>
    };

    const games = sched.dates?.[0]?.games ?? [];
    const keywords = matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim());
    const game = games.find(g =>
      keywords.some(kw =>
        g.teams.home.team.name.toLowerCase().includes(kw) ||
        g.teams.away.team.name.toLowerCase().includes(kw)
      )
    );
    if (!game) return "";

    const season = new Date().getFullYear();
    const sides = [
      { label: 'HOME', t: game.teams.home },
      { label: 'AWAY', t: game.teams.away },
    ];

    const lines = [`MLB PITCHER STATS (official MLB API — real numbers, not estimates):\nVenue: ${game.venue.name}`];

    for (const { label, t } of sides) {
      const rec = `${t.leagueRecord.wins}-${t.leagueRecord.losses}`;
      if (!t.probablePitcher) { lines.push(`  ${label} ${t.team.name} (${rec}): TBD starter`); continue; }

      const pid = t.probablePitcher.id;
      // Try current season first, fall back to previous if empty
      const trySeasons = [season, season - 1];
      let seasonStat: MLBPitchingStat | null = null;
      for (const yr of trySeasons) {
        try {
          const r = await fetch(
            `https://statsapi.mlb.com/api/v1/people/${pid}/stats?stats=season&group=pitching&season=${yr}`,
            { signal: AbortSignal.timeout(5000) }
          );
          if (!r.ok) continue;
          const d = await r.json() as { stats: Array<{ splits: Array<{ stat: MLBPitchingStat }> }> };
          const s = d.stats?.[0]?.splits?.[0]?.stat;
          if (s?.gamesStarted >= 1) { seasonStat = s; break; }
        } catch { continue; }
      }

      // Last 3 starts
      let logStr = '';
      try {
        const lr = await fetch(
          `https://statsapi.mlb.com/api/v1/people/${pid}/stats?stats=gameLog&group=pitching&season=${season}&limit=3`,
          { signal: AbortSignal.timeout(5000) }
        );
        if (lr.ok) {
          const ld = await lr.json() as { stats: Array<{ splits: Array<{ stat: MLBGameLogStat }> }> };
          const logs = ld.stats?.[0]?.splits?.slice(0, 3) ?? [];
          if (logs.length) logStr = ` | L3: ${logs.map(l => `${l.stat.era}ERA ${l.stat.strikeOuts}K ${l.stat.inningsPitched}IP`).join(', ')}`;
        }
      } catch { /* skip */ }

      const statStr = seasonStat
        ? `${seasonStat.era} ERA | ${seasonStat.strikeoutsPer9Inn} K/9 | ${seasonStat.whip} WHIP | ${seasonStat.wins}-${seasonStat.losses} (${seasonStat.gamesStarted}GS)${logStr}`
        : 'season stats not yet available';

      lines.push(`  ${label} ${t.team.name} (${rec}) — ${t.probablePitcher.fullName}: ${statStr}`);
    }

    return lines.join('\n');
  } catch { return ""; }
}

// ── Weather via wttr.in (completely free, no auth) ────────────────────────────
// Only called for outdoor sports: MLB, NFL. Indoor (NBA/NHL) = skip.
const STADIUM_CITIES: Record<string, string> = {
  // MLB
  'yankees': 'New York', 'mets': 'New York', 'red sox': 'Boston',
  'cubs': 'Chicago', 'white sox': 'Chicago', 'dodgers': 'Los Angeles',
  'angels': 'Anaheim', 'giants': 'San Francisco', 'athletics': 'Oakland',
  'padres': 'San Diego', 'rockies': 'Denver', 'diamondbacks': 'Phoenix',
  'cardinals': 'St. Louis', 'brewers': 'Milwaukee', 'reds': 'Cincinnati',
  'pirates': 'Pittsburgh', 'phillies': 'Philadelphia', 'braves': 'Atlanta',
  'marlins': 'Miami', 'nationals': 'Washington', 'orioles': 'Baltimore',
  'blue jays': 'Toronto', 'rays': 'St. Petersburg', 'tigers': 'Detroit',
  'guardians': 'Cleveland', 'royals': 'Kansas City', 'twins': 'Minneapolis',
  'astros': 'Houston', 'rangers': 'Arlington', 'mariners': 'Seattle',
  // NFL
  'patriots': 'Foxborough', 'bills': 'Orchard Park', 'dolphins': 'Miami Gardens',
  'jets': 'East Rutherford', 'ravens': 'Baltimore', 'bengals': 'Cincinnati',
  'browns': 'Cleveland', 'steelers': 'Pittsburgh', 'texans': 'Houston',
  'colts': 'Indianapolis', 'jaguars': 'Jacksonville', 'titans': 'Nashville',
  'chiefs': 'Kansas City', 'raiders': 'Las Vegas', 'chargers': 'Inglewood',
  'broncos': 'Denver', 'cowboys': 'Arlington', 'giants': 'East Rutherford',
  'eagles': 'Philadelphia', 'commanders': 'Landover', 'bears': 'Chicago',
  'lions': 'Detroit', 'packers': 'Green Bay', 'vikings': 'Minneapolis',
  'falcons': 'Atlanta', 'panthers': 'Charlotte', 'saints': 'New Orleans',
  'buccaneers': 'Tampa', 'rams': 'Inglewood', 'seahawks': 'Seattle',
  '49ers': 'Santa Clara', 'cardinals': 'Glendale',
};

async function fetchWeather(matchup: string, sport: string): Promise<string> {
  const s = sport.toUpperCase();
  if (!['MLB', 'NFL'].includes(s)) return ""; // NBA/NHL/Tennis are indoor

  // Extract home team (right side of "vs")
  const parts = matchup.toLowerCase().split(/\s+vs?\.?\s+/i);
  const homeStr = (parts[parts.length - 1] ?? parts[0]).trim();

  let city = '';
  for (const [kw, c] of Object.entries(STADIUM_CITIES)) {
    if (homeStr.includes(kw)) { city = c; break; }
  }
  if (!city) return "";

  try {
    const res = await fetch(
      `https://wttr.in/${encodeURIComponent(city)}?format=j1`,
      { signal: AbortSignal.timeout(5000), headers: { 'Accept': 'application/json', 'User-Agent': 'cavemanlocks/1.0' } }
    );
    if (!res.ok) return "";
    const data = await res.json() as {
      current_condition: Array<{
        temp_F: string; windspeedMiles: string; winddir16Point: string;
        weatherDesc: Array<{ value: string }>; FeelsLikeF: string;
      }>;
      weather: Array<{ hourly: Array<{ time: string; tempF: string; windspeedMiles: string; winddir16Point: string }> }>;
    };
    const w = data.current_condition?.[0];
    if (!w) return "";

    const wind = parseInt(w.windspeedMiles);
    const temp = parseInt(w.temp_F);
    const dir  = w.winddir16Point;
    const desc = w.weatherDesc[0]?.value ?? '';

    const flags: string[] = [];
    if (wind >= 20) flags.push(`⚠️ WIND ${wind}mph ${dir} — lean Under total, fade passing props`);
    else if (wind >= 15) flags.push(`WIND ${wind}mph ${dir} — note: affects passing/ball flight`);
    if (temp <= 40) flags.push(`🥶 COLD (${temp}°F) — lean Under`);
    if (temp >= 88) flags.push(`☀️ HOT (${temp}°F) — if wind OUT: lean Over`);

    return `WEATHER — ${city} now: ${temp}°F | Wind: ${wind}mph ${dir} | ${desc}${flags.length ? '\nBETTING IMPACT: ' + flags.join(' | ') : ''}`;
  } catch { return ""; }
}

// ── NHL Team Stats — ESPN (SV%, GAA, PPG, shots, faceoff%) ───────────────────
const ESPN_NHL_TEAM_IDS: Record<string, number> = {
  "anaheim ducks": 25, "ducks": 25, "ana": 25,
  "boston bruins": 1, "bruins": 1, "bos": 1,
  "buffalo sabres": 2, "sabres": 2, "buf": 2,
  "calgary flames": 3, "flames": 3, "cgy": 3,
  "carolina hurricanes": 7, "hurricanes": 7, "canes": 7, "car": 7,
  "chicago blackhawks": 4, "blackhawks": 4, "chi": 4,
  "colorado avalanche": 17, "avalanche": 17, "avs": 17, "col": 17,
  "columbus blue jackets": 29, "blue jackets": 29, "cbj": 29,
  "dallas stars": 9, "stars": 9, "dal": 9,
  "detroit red wings": 5, "red wings": 5, "det": 5,
  "edmonton oilers": 6, "oilers": 6, "edm": 6,
  "florida panthers": 26, "panthers": 26, "fla": 26,
  "los angeles kings": 8, "kings": 8, "lak": 8, "la kings": 8,
  "minnesota wild": 30, "wild": 30, "mnw": 30,
  "montreal canadiens": 10, "canadiens": 10, "habs": 10, "mtl": 10,
  "nashville predators": 27, "predators": 27, "preds": 27, "nsh": 27,
  "new jersey devils": 11, "devils": 11, "njd": 11,
  "new york islanders": 12, "islanders": 12, "nyi": 12,
  "new york rangers": 13, "rangers": 13, "nyr": 13,
  "ottawa senators": 14, "senators": 14, "sens": 14, "ott": 14,
  "philadelphia flyers": 15, "flyers": 15, "phi": 15,
  "pittsburgh penguins": 16, "penguins": 16, "pens": 16, "pit": 16,
  "san jose sharks": 18, "sharks": 18, "sjs": 18,
  "seattle kraken": 124292, "kraken": 124292, "sea": 124292,
  "st. louis blues": 19, "st louis blues": 19, "blues": 19, "stl": 19,
  "tampa bay lightning": 20, "lightning": 20, "bolts": 20, "tbl": 20,
  "toronto maple leafs": 21, "maple leafs": 21, "leafs": 21, "tor": 21,
  "utah mammoth": 129764, "mammoth": 129764, "utah": 129764,
  "vancouver canucks": 22, "canucks": 22, "van": 22,
  "vegas golden knights": 37, "golden knights": 37, "vgk": 37, "vegas": 37,
  "washington capitals": 23, "capitals": 23, "caps": 23, "wsh": 23,
  "winnipeg jets": 28, "jets": 28, "wpg": 28,
};

async function fetchNHLTeamStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const lower = matchup.toLowerCase();
  const parts = lower.split(/\s+(?:vs\.?|@|-)\s+/);

  const findTeam = (q: string): number | null => {
    for (const [key, id] of Object.entries(ESPN_NHL_TEAM_IDS)) {
      if (q.includes(key)) return id;
    }
    return null;
  };

  const ids = parts.map(findTeam).filter((id): id is number => id !== null);
  if (ids.length === 0) return "";

  const lines: string[] = ["NHL TEAM STATS (ESPN — real numbers, cite exactly):"];
  await Promise.all(ids.slice(0, 2).map(async teamId => {
    try {
      const res = await fetch(
        `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/${teamId}/statistics`,
        { signal: AbortSignal.timeout(5000) }
      );
      if (!res.ok) return;
      const d = await res.json() as {
        results: { stats: { categories: Array<{ stats: Array<{ name: string; displayValue: string }> }> } };
        team: { displayName: string };
      };
      const teamName = d.team?.displayName ?? `Team ${teamId}`;
      const all: Record<string, string> = {};
      for (const cat of d.results.stats.categories)
        for (const s of cat.stats) all[s.name] = s.displayValue;
      const gp = parseFloat(all['gamesPlayed'] || '1') || 1;
      const gf = parseFloat(all['goals'] || '0');
      const ga = parseFloat(all['goalsAgainst'] || '0');
      lines.push(
        `  ${teamName}: ` +
        `GF/G:${(gf/gp).toFixed(2)} | GAA:${all['avgGoalsAgainst'] ?? (ga/gp).toFixed(2)} | ` +
        `SV%:${all['savePct'] ?? '?'} | ` +
        `PPG:${all['powerPlayGoals'] ?? '?'} | ` +
        `FO%:${all['faceoffPercent'] ?? '?'} | ` +
        `SF/G:${(parseFloat(all['shotsTotal']||'0')/gp).toFixed(1)} | ` +
        `SA/G:${(parseFloat(all['shotsAgainst']||'0')/gp).toFixed(1)}`
      );
    } catch { /* skip */ }
  }));
  return lines.length > 1 ? lines.join('\n') : "";
}

// ── World Cup 2026 — today's fixtures + group standings ──────────────────────
// Primary data source for all SOCCER analysis. MLS/EPL tables dropped.
// xG/PPDA/SPI are NOT available from this feed — Claude must NOT invent them.
const WC_VENUE_NOTES: Record<string, string> = {
  'denver':       'ALTITUDE 5280ft — ball travels faster, lean Over, visiting teams gas in 70+',
  'mexico city':  'ALTITUDE 7350ft — extreme fatigue factor, fade team totals in 2nd half',
  'kansas city':  'ALTITUDE ~900ft — mild effect, slight Over lean vs sea-level opponents',
  'dallas':       'HEAT — Dallas in June/July: 95°F+, slow tempo, lean Under 90min, ET goals spike',
  'houston':      'HEAT — humidity compounds fatigue, defensive errors late, lean Under 2.5',
  'miami':        'HEAT/HUMIDITY — worst conditions, fatigue heavy, fade team totals, ET likely',
  'los angeles':  'Neutral conditions, largest stadium atmosphere — expect tight tactical games',
  'new york':     'MetLife outdoor, weather variable — check wind before betting totals',
  'seattle':      'RAIN risk — wet ball, slower play, lean Under on totals',
  'san francisco':'COLD/FOG risk — bay area cooler than inland, favors physical teams',
  'atlanta':      'DOME — controlled conditions, more goals expected, no weather factor',
  'boston':       'Gillette outdoor, coastal wind — check forecast for passing prop adjustments',
  'toronto':      'Outdoor, cooler climate — standard conditions',
  'guadalajara':  'ALTITUDE 5100ft + heat — significant fatigue, lean Under late-game props',
  'monterrey':    'HEAT — northern Mexico summer, extreme temp, fatigue bets apply',
};

async function fetchWorldCupFixtures(): Promise<string> {
  try {
    const res = await fetch(
      'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard',
      { signal: AbortSignal.timeout(6000) }
    );
    if (!res.ok) return "";
    const data = await res.json() as {
      events?: Array<{
        id: string;
        name: string;
        date: string;
        status: { type: { description: string; completed: boolean } };
        competitions: Array<{
          venue?: { fullName?: string; address?: { city?: string } };
          competitors: Array<{
            homeAway: string;
            team: { displayName: string; abbreviation: string };
            score?: string;
            records?: Array<{ summary: string; type: string }>;
          }>;
          odds?: Array<{ details: string; overUnder?: number }>;
        }>;
      }>;
    };
    if (!data.events?.length) return "";

    const lines = [`WORLD CUP 2026 — TODAY'S FIXTURES (ESPN live):`];
    for (const ev of data.events) {
      const comp    = ev.competitions[0];
      const home    = comp.competitors.find(c => c.homeAway === 'home');
      const away    = comp.competitors.find(c => c.homeAway === 'away');
      if (!home || !away) continue;

      const status   = ev.status.type.description;
      const time     = new Date(ev.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' });
      const city     = comp.venue?.address?.city?.toLowerCase() ?? '';
      const venue    = comp.venue?.fullName ?? 'TBD';
      const venueNote = Object.entries(WC_VENUE_NOTES).find(([k]) => city.includes(k))?.[1] ?? '';
      const homeRec  = home.records?.find(r => r.type === 'total')?.summary ?? '';
      const awayRec  = away.records?.find(r => r.type === 'total')?.summary ?? '';
      const ou       = comp.odds?.[0]?.overUnder;

      const scoreStr = ev.status.type.completed
        ? `FINAL ${away.score}-${home.score}`
        : status === 'Scheduled' ? `${time} ET` : status;

      lines.push(
        `  ${away.team.displayName} (${awayRec}) @ ${home.team.displayName} (${homeRec}) — ${scoreStr}` +
        `\n    Venue: ${venue}${venueNote ? ` | ⚠️ ${venueNote}` : ''}` +
        (ou ? `\n    Book Total: ${ou}` : '')
      );
    }
    return lines.join('\n');
  } catch { return ""; }
}

// ── World Cup 2026 advancement scenario tagger ───────────────────────────────
// WC 2026: 3 teams per group, top 2 advance + 8 best 3rd-place qualify.
// Tags each team's BETTING CONTEXT: must-win, can-draw, rotates, eliminated.
function wcAdvancementTag(rank: number, pts: number, gp: number, maxRemainingPts: number, secondPts: number, thirdPts: number): string {
  const remaining = 3 - gp;
  const maxPts = pts + remaining * 3;

  if (gp === 3) {
    // Final standings
    if (rank === 1) return '✅ QUALIFIED 1st — watch rotation risk game 3';
    if (rank === 2) return '✅ QUALIFIED 2nd — competitive performance expected';
    return '🔴 ELIMINATED — expect rotation/youth players. Fade totals/ML hard.';
  }
  // In-progress group
  if (pts >= 6) return '✅ QUALIFIED (6pts) — ROTATION RISK. Fade team totals + ML.';
  if (pts >= 4 && gp === 2) return '🟢 VERY LIKELY THROUGH — may rotate. Reduced motivation possible.';
  if (maxPts < secondPts) return '🔴 ELIMINATED (cannot catch 2nd) — Fade. Rotation/youth risk.';
  if (pts === 0 && gp === 2) return '🔴 MUST WIN game 3 to have any chance. All-in attack. Over lean.';
  if (pts <= 1 && gp === 2) return '⚠️ MUST WIN game 3 — attacking play forced. Lean Over totals.';
  if (pts >= 3 && gp === 2) return '⚡ CAN DRAW to advance — defensive setup possible. Under lean.';
  if (remaining === 1 && pts === 0) return '🔴 MUST WIN — desperate. All-out attack. Big Over lean.';
  return `⚡ ${remaining} game(s) left — ${pts}pts — result matters`;
}

async function fetchWorldCupStandings(): Promise<string> {
  try {
    const res = await fetch(
      'https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings',
      { signal: AbortSignal.timeout(6000) }
    );
    if (!res.ok) return "";
    const data = await res.json() as {
      children?: Array<{
        name?: string;
        standings?: {
          entries?: Array<{
            team: { displayName: string };
            stats: Array<{ name: string; value: number }>;
          }>;
        };
      }>;
    };

    const lines = ['WORLD CUP 2026 GROUP STANDINGS + ADVANCEMENT SCENARIOS (ESPN — real data):'];
    for (const group of data.children ?? []) {
      if (!group.standings?.entries?.length) continue;
      lines.push(`  ${group.name ?? 'Group'}:`);

      // Parse all entries first so we can compute advancement tags
      const entries = group.standings.entries.map(entry => {
        const st: Record<string, number> = {};
        for (const s of entry.stats) st[s.name] = s.value;
        return {
          name: entry.team.displayName,
          gp:  st['gamesPlayed'] ?? 0,
          pts: st['points']      ?? 0,
          w:   st['wins']        ?? 0,
          d:   st['ties']        ?? 0,
          l:   st['losses']      ?? 0,
          gf:  st['pointsFor']   ?? 0,
          ga:  st['pointsAgainst'] ?? 0,
        };
      }).sort((a, b) => b.pts - a.pts || (b.gf - b.ga) - (a.gf - a.ga));

      entries.forEach((e, i) => {
        const gd = e.gf - e.ga;
        const secondPts = entries[1]?.pts ?? 0;
        const thirdPts  = entries[2]?.pts ?? 0;
        const tag = wcAdvancementTag(i + 1, e.pts, e.gp, e.pts + (3 - e.gp) * 3, secondPts, thirdPts);
        lines.push(
          `    ${i + 1}. ${e.name}: ${e.pts}pts | ${e.w}W-${e.d}D-${e.l}L | GF:${e.gf} GA:${e.ga} GD:${gd >= 0 ? '+' : ''}${gd} (${e.gp}GP) — ${tag}`
        );
      });
    }
    return lines.length > 1 ? lines.join('\n') : "";
  } catch { return ""; }
}

// Championship outrights → devigged title probabilities = market's team-strength
// rating. One API call per 12h per sport (cached). Injected into every analysis.
const OUTRIGHT_KEYS: Record<string, { key: string; label: string }> = {
  SOCCER: { key: 'soccer_fifa_world_cup_winner',            label: 'WC 2026 CHAMPION' },
  NBA:    { key: 'basketball_nba_championship_winner',      label: 'NBA CHAMPIONSHIP' },
  MLB:    { key: 'baseball_mlb_world_series_winner',        label: 'WORLD SERIES' },
  NFL:    { key: 'americanfootball_nfl_super_bowl_winner',  label: 'SUPER BOWL' },
  NHL:    { key: 'icehockey_nhl_championship_winner',       label: 'STANLEY CUP' },
};

async function fetchChampionshipPrior(sport: string): Promise<string> {
  const outright = OUTRIGHT_KEYS[sport];
  if (!ODDS_API_KEY || !outright) return '';
  const cacheKey = `outrights:${sport}`;
  const cached = getCached(cacheKey);
  if (cached) return cached as string;
  try {
    // Skip silently if the outright market isn't in season
    const activeKeys = await getActiveSportKeys();
    if (activeKeys && !activeKeys.has(outright.key)) return '';

    const url = `${ODDS_API_BASE}/sports/${outright.key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=outrights&oddsFormat=american`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) {
      console.error(`Outrights fetch failed for ${sport}: HTTP ${res.status}`);
      return '';
    }
    const events = await res.json() as OddsEvent[];
    const outcomes = events[0]?.bookmakers?.[0]?.markets?.find(m => m.key === 'outrights')?.outcomes ?? [];
    if (!outcomes.length) return '';

    const withImplied = outcomes.map(o => ({ name: o.name, price: o.price, implied: impliedProb(o.price) }));
    const overround = withImplied.reduce((s, o) => s + o.implied, 0);
    const top = [...withImplied].sort((a, b) => b.implied - a.implied).slice(0, 14);
    const rows = top.map((o, i) =>
      `${i + 1}. ${o.name} — ${((o.implied / overround) * 100).toFixed(1)}% (${o.price > 0 ? '+' : ''}${o.price})`
    );
    const block =
      `🏆 ${outright.label} STRENGTH PRIOR (devigged title probabilities — the market's team-strength rating):\n` +
      `${rows.join('\n')}\n` +
      `Use as a class prior: a big title-prob gap between two teams = real class gap in their match. ` +
      `Context only — match odds still decide the pick. Teams outside this list are longshots.`;
    setCache(cacheKey, block, 12 * 60 * 60 * 1000);
    return block;
  } catch (e: unknown) {
    console.error(`Outrights error for ${sport}: ${e instanceof Error ? e.message : String(e)}`);
    return '';
  }
}

async function fetchSoccerContext(matchup: string): Promise<string> {
  // Run both WC data calls in parallel (championship prior arrives via fetchLiveOdds)
  const [fixtures, standings] = await Promise.all([
    fetchWorldCupFixtures(),
    fetchWorldCupStandings(),
  ]);

  const parts: string[] = [];
  if (fixtures) parts.push(fixtures);
  if (standings) parts.push(standings);

  // Venue note inline if matchup string contains a city
  if (matchup) {
    const lower = matchup.toLowerCase();
    for (const [city, note] of Object.entries(WC_VENUE_NOTES)) {
      if (lower.includes(city)) {
        parts.push(`⚠️ VENUE FACTOR: ${note}`);
        break;
      }
    }
  }

  // ── BETTING STAKES GUIDE — injected into every WC analysis ───────────────
  parts.push(`
⚽ WC 2026 BETTING STAKES GUIDE — READ BEFORE PICKING:
• Teams tagged ✅ QUALIFIED with games remaining: ROTATION RISK. Fade their ML, fade player totals — starters may rest.
• Teams tagged 🔴 ELIMINATED: Do NOT bet them as favorites. Motivation gone. Backs/youth players enter.
• Teams tagged ⚠️ MUST WIN: Expect attacking play, high line, pressing. Lean Over 2.5 goals, Over team total, BTTS Yes.
• Teams tagged ⚡ CAN DRAW: May play defensively to secure a point. Lean Under 2.5, AH+0.5 on underdog.
• SIMULTANEOUS final group games: No tactical manipulation possible — more honest prices.
• Group game 1: VERIFIED roughly coin-flip on totals (~49-51% under 2.5 in recent WCs). No automatic under — price decides.
• Group game 3 with rotation risk: FADE player props hard. Fade team total. Lean opponent.
• Asian Handicap ALWAYS > 3-way ML. AH+0.5 = draw insurance. Eliminates draw deadweight.
• CRITICAL: Do NOT cite xG, PPDA, or SPI — not in data. Use devigged implied probability from LIVE ODDS only.`);

  parts.push(
    '⚠️ xG/PPDA/SPI data NOT available from this feed. ' +
    'Do NOT invent these numbers. Use implied probability math from the LIVE ODDS block instead. ' +
    'Label any xG estimates as "est." and note they are approximated from line movement.'
  );

  return parts.join('\n\n');
}

// ── F1 Circuit Database (local — no API needed) ───────────────────────────────
interface F1CircuitInfo {
  name: string; type: 'Street' | 'Power' | 'Technical' | 'Mixed';
  qualifyingWeight: number; // 0-1: how much qualifying position predicts race result
  overtaking: 'Extreme' | 'Very High' | 'High' | 'Moderate' | 'Low';
  dnfRate: string; safetyCar: string;
  notes: string;
}
const F1_CIRCUITS: Record<string, F1CircuitInfo> = {
  monaco:       { name:'Circuit de Monaco',              type:'Street',    qualifyingWeight:0.95, overtaking:'Extreme',  dnfRate:'~25%', safetyCar:'Near-certain', notes:'Pole almost always wins. No overtaking. Bet pole sitter. DNF props hold huge value.' },
  singapore:    { name:'Marina Bay Street Circuit',      type:'Street',    qualifyingWeight:0.85, overtaking:'Extreme',  dnfRate:'~20%', safetyCar:'Near-certain', notes:'Night race. Safety car = guaranteed. Long wheelbase cars advantage.' },
  baku:         { name:'Baku City Circuit',              type:'Street',    qualifyingWeight:0.80, overtaking:'Very High', dnfRate:'~18%', safetyCar:'High',         notes:'Long straight allows some overtaking into Turn 1. Safety car extremely likely. Big upsets common.' },
  jeddah:       { name:'Jeddah Corniche Circuit',        type:'Street',    qualifyingWeight:0.85, overtaking:'Very High', dnfRate:'~15%', safetyCar:'High',         notes:'Fastest street circuit. Multiple crashes likely. High-speed walls punish any error.' },
  miami:        { name:'Miami International Autodrome',  type:'Street',    qualifyingWeight:0.75, overtaking:'High',      dnfRate:'~10%', safetyCar:'Moderate',     notes:'Semi-permanent street circuit. Some DRS overtaking zones. Tire management key.' },
  lasvegas:     { name:'Las Vegas Street Circuit',       type:'Street',    qualifyingWeight:0.80, overtaking:'High',      dnfRate:'~12%', safetyCar:'Moderate',     notes:'Night race, cold temps in November. Tire graining in cold = big wildcard.' },
  zandvoort:    { name:'Circuit Zandvoort',              type:'Street',    qualifyingWeight:0.85, overtaking:'Extreme',  dnfRate:'~8%',  safetyCar:'Moderate',     notes:'Banking turns make overtaking nearly impossible. Qualifying result highly predictive.' },
  monza:        { name:'Autodromo Nazionale Monza',      type:'Power',     qualifyingWeight:0.50, overtaking:'Low',       dnfRate:'~8%',  safetyCar:'Low',          notes:'Temple of Speed. Slipstream creates genuine overtaking. Engine power dominant. Low-drag setups.' },
  spa:          { name:'Circuit de Spa-Francorchamps',   type:'Power',     qualifyingWeight:0.55, overtaking:'Low',       dnfRate:'~12%', safetyCar:'Moderate',     notes:'Long Kemmel straight = genuine DRS overtaking. Weather changes rapidly — wet weather wild card.' },
  bahrain:      { name:'Bahrain International Circuit',  type:'Power',     qualifyingWeight:0.55, overtaking:'Low',       dnfRate:'~8%',  safetyCar:'Low',          notes:'Multiple DRS zones. Tire degradation critical. Hot and dusty — evolution of grip during weekend.' },
  abudhabi:     { name:'Yas Marina Circuit',             type:'Power',     qualifyingWeight:0.60, overtaking:'Moderate',  dnfRate:'~5%',  safetyCar:'Low',          notes:'Season finale. Championship pressure = higher risk-taking. DRS zones allow some overtaking.' },
  austin:       { name:'Circuit of the Americas (COTA)', type:'Technical', qualifyingWeight:0.65, overtaking:'Moderate',  dnfRate:'~8%',  safetyCar:'Low',          notes:'Loved by aerodynamic cars (Red Bull, Ferrari). High downforce setup advantage. Bumpy surface.' },
  hungary:      { name:'Hungaroring',                    type:'Technical', qualifyingWeight:0.80, overtaking:'High',      dnfRate:'~5%',  safetyCar:'Low',          notes:'Slow, twisty. Like Monaco without the walls. High downforce = overtaking near-impossible. Qualifying hugely important.' },
  silverstone:  { name:'Silverstone Circuit',            type:'Technical', qualifyingWeight:0.65, overtaking:'Moderate',  dnfRate:'~8%',  safetyCar:'Moderate',     notes:'High-speed flowing corners. Aerodynamic setup crucial. British crowd creates pressure for home teams.' },
  suzuka:       { name:'Suzuka Circuit',                 type:'Technical', qualifyingWeight:0.70, overtaking:'High',      dnfRate:'~10%', safetyCar:'Moderate',     notes:'Beloved technical circuit. High-speed S-curves require precision setup. Weather variable in October.' },
  interlagos:   { name:'Autodromo José Carlos Pace',     type:'Technical', qualifyingWeight:0.65, overtaking:'Moderate',  dnfRate:'~12%', safetyCar:'Moderate',     notes:'Altitude (800m) affects engine power. Rain very common — huge wildcard. Sprint weekends here create extra data.' },
  imola:        { name:'Autodromo Enzo e Dino Ferrari',  type:'Technical', qualifyingWeight:0.75, overtaking:'High',      dnfRate:'~10%', safetyCar:'Moderate',     notes:'Limited overtaking zones. Safety car likely. Old-school circuit rewards technical setup.' },
};

function getF1CircuitContext(matchup: string): string {
  if (!matchup) return "";
  const lower = matchup.toLowerCase();
  for (const [key, info] of Object.entries(F1_CIRCUITS)) {
    if (lower.includes(key) || lower.includes(info.name.toLowerCase())) {
      return [
        `F1 CIRCUIT CONTEXT (${info.name}):`,
        `  Type: ${info.type} Circuit | Overtaking: ${info.overtaking}`,
        `  Qualifying → Race Prediction Weight: ${(info.qualifyingWeight * 100).toFixed(0)}%`,
        `  Historical DNF Rate: ${info.dnfRate} | Safety Car: ${info.safetyCar}`,
        `  Notes: ${info.notes}`,
        `  BETTING IMPLICATION: ${info.type === 'Street'
          ? 'Pole sitter is primary bet. DNF props have value. Backup puck line / podium finish safer than race winner.'
          : info.type === 'Power'
          ? 'Overtaking possible via DRS. Engine power units (Red Bull PU, Ferrari PU) are advantaged. Race winner more open.'
          : 'Setup and aerodynamics dominate. High downforce cars (Red Bull, Ferrari) excel. Mid-field upsets less likely.'}`,
      ].join('\n');
    }
  }
  return "";
}

// ── Tennis context — current tournament scoreboard + surface + seedings ───────
// Determines active tournament from SPORT_KEYS order, fetches today's schedule.
const TENNIS_TOURNAMENT_CONTEXT: Record<string, string> = {
  'tennis_atp_french_open':  'ROLAND GARROS — CLAY | Topspin grinders dominant. Big servers fade. Slow bounce = long rallies. Fade flat hitters. Stamina is #1 edge.',
  'tennis_wta_french_open':  'ROLAND GARROS WTA — CLAY | Baseline endurance dominates. Lefties/topspin players overperform. Fat favorites often backed too hard — target surface specialists vs ranked opponents.',
  'tennis_atp_wimbledon':    'WIMBLEDON — GRASS | ⚡ SURFACE TRANSITION ALPHA WINDOW: Books still using clay Elo for 1-2 weeks into grass. Clay grinders OVERBET by public rounds 1-2 — FADE them. Big servers/grass specialists UNDERVALUED — BACK them before books adjust. 1st set → match winner 72% on grass (highest any surface). Serve hold rate ~90%. Under total games, Under total breaks. Net rushers and serve-volleyers peak value rounds 1-3. ACE count + match winner = strong positive correlation for big servers.',
  'tennis_wta_wimbledon':    'WIMBLEDON WTA — GRASS | ⚡ SURFACE FLIP ALPHA: Aggressive flat-ball strikers > defensive counterpunchers. Books lag clay Elo into grass weeks 1-2. Early rounds = maximum inefficiency — back grass specialists at inflated price. Serve hold ~85% on WTA grass. Under total games standard lean. Last-minute scratch risk HIGH on grass (ankle/knee on slick courts) — confirm warmup before betting.',
  'tennis_atp_us_open':      'US OPEN — HARD/OUTDOOR | Night sessions: ball travels faster under lights, lean big servers slightly. Loud crowd at night = volatile momentum shifts in live betting. Deuce-set tiebreak = coin flip, avoid set-betting.',
  'tennis_wta_us_open':      'US OPEN WTA — HARD/OUTDOOR | Most neutral surface. Overall Elo most predictive. Night session atmosphere = mental edge for US players, factor in nationalism bias on ML.',
  'tennis_atp_aus_open':     'AUSTRALIAN OPEN — HARD/OUTDOOR | Heat policy applies (extreme heat suspensions). Plexicushion medium-slow = longer rallies than US Open. January heat in Melbourne = fatigue factor, lean Under on total games in later sets.',
  'tennis_wta_aus_open':     'AUSTRALIAN OPEN WTA — HARD/OUTDOOR | Heat rule applies. Long baseline rallies. Consistent ball-strikers over power players.',
  // Transition week events — grass warm-up = maximum inefficiency
  'tennis_atp_queens':       'QUEEN\'S CLUB (GRASS) — TRANSITION WEEK | ⚡ MAXIMUM INEFFICIENCY: Books still using clay Elo. First grass event = biggest mispricing window of the tennis calendar. Big servers at their peak value BEFORE books adjust. Back serve-dominant players aggressively. Under total games strong lean.',
  'tennis_atp_halle':        'HALLE OPEN (GRASS) — TRANSITION WEEK | ⚡ MAXIMUM INEFFICIENCY: Mirror Queen\'s Club edge. Serve-dominant Germans/Europeans at home venue with crowd edge. Books still clay-lagged. Under total games, Under breaks, Big server ML.',
};

// National-team form profile returned by /predict-soccer (built from real
// internationals by fetch_soccer_form.py). Used only as analysis context.
interface SoccerTeamForm {
  team: string; form_ppg: number; win_rate: number; gf: number; ga: number;
  over25: number; btts: number; clean_sheet: number; failed_to_score: number;
  streak: string; last5: string;
}

// WNBA form profile returned by /predict (built from real ESPN game results
// by fetch_wnba_form.py). Used only as analysis context.
interface WnbaTeamForm {
  team: string; gp: number; win_rate: number; last10: string; avg_margin: number;
  recent_margin: number; streak: string; rest_days: number | null; b2b: boolean;
  home: string; road: string;
}

// Active tennis surface (Clay|Grass|Hard) from the priority tournament key.
// Title-case so it matches the surface keys the edge_api model expects.
function tennisActiveSurface(): 'Clay' | 'Grass' | 'Hard' {
  const key = SPORT_KEYS.TENNIS?.[0] ?? '';
  if (key.includes('french')) return 'Clay';
  if (key.includes('wimbledon') || key.includes('queens') || key.includes('halle')) return 'Grass';
  return 'Hard';
}

// ── ESPN tennis scoreboard shape ────────────────────────────────────────────
// ESPN nests every match (major AND regular tour) under
// events[].groupings[].competitions[] — there is NO top-level events[].competitions.
// linescores[].winner is the authoritative "who won this set" flag (linescore
// VALUE is games won in that set, not sets won — count winner:true entries).
interface TennisLinescore { value: number; winner?: boolean; tiebreak?: number }
interface TennisCompetitor {
  athlete?: { displayName?: string; rank?: number };
  winner?: boolean;
  linescores?: TennisLinescore[];
}
interface TennisMatch {
  date: string;
  status: { type: { description: string; state: string; completed: boolean } };
  format?: { regulation?: { periods?: number } };
  competitors: TennisCompetitor[];
}
interface TennisTourEvent {
  name: string;
  groupings?: Array<{ grouping?: { slug?: string }; competitions: TennisMatch[] }>;
}

// Flattens to singles matches only — doubles/mixed pairs would poison both the
// schedule listing and the live-score lookup (the model is singles-only, see
// project memory on the doubles-vs-singles gap).
function flattenTennisSinglesMatches(events: TennisTourEvent[]): TennisMatch[] {
  const out: TennisMatch[] = [];
  for (const ev of events) {
    for (const g of ev.groupings ?? []) {
      if (!g.grouping?.slug?.includes('singles')) continue;
      out.push(...g.competitions);
    }
  }
  return out;
}

function setsWon(c: TennisCompetitor): number {
  return (c.linescores ?? []).filter(ls => ls.winner === true).length;
}

const tennisSurname = (name: string): string =>
  name.trim().toLowerCase().split(/[\s,]+/).filter(Boolean).pop() ?? '';

// Best-effort live set score for an in-progress match — used to re-price the
// tennis model off the CURRENT score instead of only the pregame number
// (scripts/tennis_live.py does the actual math). Returns null for anything
// pre-match, finished, or that ESPN doesn't have live right now; the /predict
// call falls back to a pure pregame price when this is null.
async function fetchTennisLiveSetScore(
  homeName: string, awayName: string
): Promise<{ setsWonHome: number; setsWonAway: number; bestOf: number } | null> {
  try {
    const results = await Promise.allSettled([
      fetch('https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard', { signal: AbortSignal.timeout(4000) }),
      fetch('https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard', { signal: AbortSignal.timeout(4000) }),
    ]);
    const homeSurname = tennisSurname(homeName);
    const awaySurname = tennisSurname(awayName);
    if (!homeSurname || !awaySurname) return null;

    for (const r of results) {
      if (r.status !== 'fulfilled' || !r.value.ok) continue;
      const data = await r.value.json() as { events?: TennisTourEvent[] };
      const matches = flattenTennisSinglesMatches(data.events ?? []);
      for (const m of matches) {
        if (m.status.type.state !== 'in') continue; // only live matches carry a real-time score
        const names = m.competitors.map(c => c.athlete?.displayName?.toLowerCase() ?? '');
        const homeIdx = names.findIndex(n => n.includes(homeSurname));
        const awayIdx = names.findIndex(n => n.includes(awaySurname));
        if (homeIdx === -1 || awayIdx === -1 || homeIdx === awayIdx) continue;
        const periods = m.format?.regulation?.periods;
        return {
          setsWonHome: setsWon(m.competitors[homeIdx]),
          setsWonAway: setsWon(m.competitors[awayIdx]),
          bestOf: periods === 5 ? 5 : 3,
        };
      }
    }
    return null;
  } catch {
    return null; // best-effort — pregame pricing still works without this
  }
}

async function fetchTennisContext(matchup: string): Promise<string> {
  // Identify active tournament — first key in TENNIS list is the current priority
  const activeTournamentKey = SPORT_KEYS.TENNIS?.[0] ?? '';
  const surfaceCtx = TENNIS_TOURNAMENT_CONTEXT[activeTournamentKey] ?? 'HARD COURT — standard conditions.';

  const activeSurface = activeTournamentKey.includes('french') ? 'CLAY'
    : (activeTournamentKey.includes('wimbledon') || activeTournamentKey.includes('queens') || activeTournamentKey.includes('halle')) ? 'GRASS'
    : 'HARD';

  // Determine if we are in the grass transition window (late May – mid July)
  const nowMonth = new Date().getMonth() + 1; // 1-12
  const isGrassWindow = nowMonth >= 6 && nowMonth <= 7;

  const parts: string[] = [`TENNIS CONTEXT — ${surfaceCtx}`];

  if (isGrassWindow) {
    parts.push(`
⚡ WIMBLEDON GRASS TRANSITION WINDOW ACTIVE (June–July)
────────────────────────────────────────────────────
KEY EDGES THIS WINDOW:
• Weeks 1–2 of grass: books still running clay Elo. BIGGEST mispricing window of tennis year.
• Big servers (Ace% >18, hold% >85) are UNDERVALUED by 3-8% vs clay-based lines.
• Clay grinders are OVERVALUED by 4-10% — books slow to adjust. FADE them R1-R2.
• Serve hold rate on grass ~90% (ATP) / ~85% (WTA) → lean UNDER total breaks.
• First set winner covers match 72% on grass (highest any surface).
• After Roland Garros: players who reached SF/F may carry fatigue — watch for early exits.
• Transition-specialist players (Queen's Club / Halle winners) carry strong grass Elo not priced by books.
• Net rushers and serve-volleyers peak value rounds 1-3. Books don't model these specialties.
• INJURY RISK: Slick grass courts = ankle/knee risk. Confirm no pre-match withdrawal before betting.
• R1-R2 upsets on grass run ~28% — higher than any other slam surface. Avoid heavy parlays on chalk.

MARKET PRIORITY FOR GRASS:
1. ML on grass specialists / big servers at +120 to +250 (best value)
2. Game handicap -4.5 / +4.5 (serve hold reduces break variance)
3. Under total games (fewer breaks = fewer game swings)
4. Avoid BTTS / exact set scores (high variance on grass)
5. Set betting: "Player to win in straight sets" overpriced for big servers in R1-R2

CRITICAL: Never cite clay stats for a grass match. Do NOT use clay season head-to-head if surface was different.`);
  }

  // ATP/WTA rankings from ESPN (best-effort)
  const rankingsMap: Record<string, number> = {};
  try {
    const rankRes = await fetch(
      'https://site.api.espn.com/apis/site/v2/sports/tennis/atp/rankings',
      { signal: AbortSignal.timeout(4000) }
    );
    if (rankRes.ok) {
      const rankData = await rankRes.json() as {
        rankings?: Array<{
          athletes: Array<{ athlete?: { displayName?: string }; rankChange?: number; current?: number }>;
        }>;
      };
      const rows = rankData.rankings?.[0]?.athletes ?? [];
      for (const r of rows.slice(0, 50)) {
        const name = r.athlete?.displayName;
        const rank = r.current;
        if (name && rank) rankingsMap[name.toLowerCase()] = rank;
      }
    }
  } catch { /* rankings best-effort */ }

  // Today's ATP + WTA schedule from ESPN
  const scheduleResults = await Promise.allSettled([
    fetch('https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard', { signal: AbortSignal.timeout(5000) }),
    fetch('https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard', { signal: AbortSignal.timeout(5000) }),
  ]);

  const keywords = matchup
    ? matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim())
    : [];

  for (const [idx, result] of scheduleResults.entries()) {
    if (result.status !== 'fulfilled' || !result.value.ok) continue;
    const data = await result.value.json() as { events?: TennisTourEvent[] };
    const allMatches = flattenTennisSinglesMatches(data.events ?? []);
    if (!allMatches.length) continue;

    const tour = idx === 0 ? 'ATP' : 'WTA';
    const relevant = keywords.length
      ? allMatches.filter(m =>
          m.competitors.some(c =>
            keywords.some(kw => c.athlete?.displayName?.toLowerCase().includes(kw))
          )
        )
      : allMatches.slice(0, 6);

    if (!relevant.length) continue;
    parts.push(`TODAY'S ${tour} SCHEDULE (ESPN):`);
    for (const m of relevant.slice(0, 6)) {
      const p1 = m.competitors[0];
      const p2 = m.competitors[1];
      const status = m.status.type.description;
      const time = new Date(m.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' });
      const name1 = p1?.athlete?.displayName ?? '?';
      const name2 = p2?.athlete?.displayName ?? '?';
      const liveRank1 = rankingsMap[name1.toLowerCase()];
      const rank1 = (p1?.athlete?.rank ?? liveRank1) ? `(#${p1?.athlete?.rank ?? liveRank1})` : '';
      const rank2Num = p2?.athlete?.rank ?? rankingsMap[name2.toLowerCase()];
      const rank2 = rank2Num ? `(#${rank2Num})` : '';
      const isLive = m.status.type.state === 'in';
      const scoreTag = isLive ? ` [LIVE ${setsWon(p1)}-${setsWon(p2)} sets]` : '';
      parts.push(
        `  ${name1} ${rank1} vs ${name2} ${rank2} — ${status === 'Scheduled' ? time + ' ET' : status}${scoreTag}`
      );
    }
  }

  // Surface-specific betting rules
  const surfaceRules: Record<string, string> = {
    CLAY: `SURFACE RULES (CLAY):
• Fade -300+ favorites — upsets ~22% on clay.
• Target +150 to +280 surface specialists (topspin, stamina).
• Rolling load >15 sets = HIGH FATIGUE — fade that player.
• Game handicap -4.5 > ML at -200 to -280 juice.
• Lefties/heavy topspin players overperform vs ranking.`,
    GRASS: `SURFACE RULES (GRASS):
• Big-server ML value HIGHEST rounds 1-3 (books still clay Elo).
• First set winner covers match 72% — highest any surface.
• Serve hold ~90% ATP / ~85% WTA → Under total breaks.
• Fade clay grinders R1–R2 — they WILL be overbet.
• Net rushers + serve-volleyers peak value rounds 1-3.
• Injury risk on slick grass: verify no withdrawal before bet.`,
    HARD: `SURFACE RULES (HARD):
• Overall Elo most predictive surface.
• Night sessions favor power players (ball travels faster).
• Live betting > pre-match ML — service break volatility creates momentum swings.
• Avoid set-betting after first set — tiebreaks = near coin flips.`,
  };
  parts.push(surfaceRules[activeSurface]);

  parts.push(`
DATA INTEGRITY RULE — TENNIS:
• Only cite rankings, scores, and schedules from the data blocks above.
• Do NOT hallucinate career stats, grass records, or H2H results.
• Surface switch = clay records irrelevant. Use grass-specific performance only.
• If a player's surface stats are not in the data block, state "surface data not available" — do not estimate.`);

  return parts.join('\n');
}

// ── Devig a market → fair (no-vig) probability per outcome ────────────────────
// Normalizes the book's implied probs to sum to 1. Handles 2-way (ML/spread/total)
// AND 3-way (soccer 1X2 — Win/Draw/Win). Comparing raw implied probs across books
// is biased by their different vig levels (Pinnacle ~2-3% vs DK/FD ~5%) — always
// devig first so a gap reflects a real price disagreement, not juice.
function fairMarketProbs(outcomes: Array<{ name: string; price: number }>): Map<string, number> | null {
  if (outcomes.length < 2) return null;
  const raw = outcomes.map(o => impliedProb(o.price));
  const sum = raw.reduce((a, b) => a + b, 0);
  if (sum <= 0) return null;
  return new Map(outcomes.map((o, i) => [o.name, raw[i] / sum]));
}

// ── Synthetic Sharp Signal (Pinnacle vs soft-book fair-price gap) ─────────────
// Pinnacle is the sharpest book. When its DEVIGGED fair price diverges from
// DraftKings/FanDuel, that gap reveals where the sharp money is pointing.
async function fetchSharpSignals(sport: string): Promise<string> {
  if (!ODDS_API_KEY) return "";
  const sportKeys = SPORT_KEYS[sport.toUpperCase()] || [];
  if (sportKeys.length === 0) return "";
  const signals: string[] = [];
  try {
    const url = `${ODDS_API_BASE}/sports/${sportKeys[0]}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return "";
    const events = await res.json() as OddsEvent[];
    for (const ev of events.slice(0, 6)) {
      const pinnacle = ev.bookmakers.find(b => b.key === "pinnacle");
      const dk = ev.bookmakers.find(b => b.key === "draftkings");
      if (!pinnacle || !dk) continue;
      for (const market of pinnacle.markets) {
        const dkMarket = dk.markets.find(m => m.key === market.key);
        if (!dkMarket) continue;
        const pinFair = fairMarketProbs(market.outcomes);
        const dkFair = fairMarketProbs(dkMarket.outcomes);
        if (!pinFair || !dkFair) continue;
        for (const pinOut of market.outcomes) {
          const dkOut = dkMarket.outcomes.find(o =>
            o.name === pinOut.name && (market.key !== 'spreads' || o.point === pinOut.point));
          if (!dkOut) continue;
          const pf = pinFair.get(pinOut.name), df = dkFair.get(pinOut.name);
          if (pf == null || df == null) continue;
          // Devigged fair-prob gap (percentage points) — not biased by either
          // book's juice. ≥3 pts = a real sharp/soft disagreement on the price.
          const gap = Math.round((pf - df) * 1000) / 10;
          if (Math.abs(gap) >= 3) {
            const direction = gap > 0 ? "SHARP BACKING" : "SHARP FADING";
            signals.push(`${ev.away_team} @ ${ev.home_team} | ${market.key.toUpperCase()} ${pinOut.name}: Pinnacle ${(pf * 100).toFixed(1)}% vs DK ${(df * 100).toFixed(1)}% fair → ${direction} ${pinOut.name} (${gap > 0 ? "+" : ""}${gap} pts)`);
          }
        }
      }
    }
  } catch { return ""; }
  if (signals.length === 0) return "";
  return `SYNTHETIC SHARP SIGNALS (Pinnacle vs DraftKings, devigged fair-prob gap ≥3 pts):\n${signals.join("\n")}`;
}

// ── Bet structure label — pure math from American odds ────────────────────────
// Heavy favorites = bad single value (juice destroys ROI). Good parlay legs.
// Props / moderate lines = good both ways. Plus-money dogs = take standalone.
function getBetStructure(oddsNum: number): string {
  // No odds = no bet (PASS / fake game). Never label a non-pick as a good bet.
  if (isNaN(oddsNum) || oddsNum === 0) return 'PASS';
  if (oddsNum <= -220) return 'PARLAY ONLY';
  if (oddsNum <= -165) return 'PARLAY PREFERRED';
  if (oddsNum <  200)  return 'SINGLE + PARLAY';
  return 'SINGLE';
}

// ── Anti-hallucination directive — injected into EVERY prompt ─────────────────
const ANTI_HALLUCINATION_DIRECTIVE = `
⛔ DATA INTEGRITY RULES — NON-NEGOTIABLE. VIOLATION = INVALID OUTPUT:
1. ONLY cite numbers, stats, or trends that appear VERBATIM in the DATA BLOCKS provided.
2. Do NOT generate win probabilities, confidence scores, or EV percentages — math engine handles those.
3. Do NOT generate kelly stakes — math engine handles those.
4. Do NOT cite ATS records, historical cover rates, or any percentage NOT in the data blocks.
5. Do NOT cite player stat lines (PPG, RPG, APG, etc.) unless in the PLAYER STATS / ADVANCED STATS block.
6. SOCCER: Do NOT cite xG, PPDA, or SPI — not available in any data block.
7. If no data exists to support a claim → say "no data" or omit the claim entirely.
8. Rationale must cite source: [ESPN NEWS], [INJURY REPORT], [SHARP SIGNALS], [LIVE ODDS], [SCOREBOARD], [PLAYER STATS], [ADVANCED STATS], [WEATHER], [NICHE DATA], [ESPN RECORDS].
9. All picks must come from the LIVE ODDS block. If a game is not in that block, do not pick it.
10. ESPN RECORDS block: cite W/L records, home/away splits, and recent form from the HISTORICAL DATA block as [ESPN RECORDS]. ONLY cite numbers that appear VERBATIM above — do NOT round, invent, or extrapolate.
YOUR ONLY JOB: (1) Identify the best bet from the LIVE ODDS block. (2) Explain using SOURCED DATA ONLY.
`.trim();

// ── MYTHOS-STYLE IDENTITY BLOCK (Capybara tier adapted for sports betting) ────
// Borrowed from FTGMYTHOS/mythos-router: structured IDENTITY + CORE DIRECTIVES
// forces disciplined, non-hallucinated output — same principle as SWD for files
const SHARP_IDENTITY = () => getSharpIdentity(
  MODEL_WEIGHTS.math_weight * 100,
  MODEL_WEIGHTS.sentiment_weight * 100,
  MODEL_WEIGHTS.dissonance_threshold
);

// ── Claude (Anthropic) helper with DeepSeek fallback (Mythos multi-provider) ──
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const DEEPSEEK_KEY = process.env.DEEPSEEK_API_KEY || "";

async function ask(prompt: string, model = "claude-sonnet-4-6"): Promise<string> {
  try {
    const msg = await anthropic.messages.create({
      model,
      max_tokens: 4096,
      messages: [{ role: "user", content: prompt }],
    });
    const text = msg.content[0].type === "text" ? msg.content[0].text : "";
    return text.replace(/```json|```/g, "").trim();
  } catch (err: unknown) {
    // Mythos-router style fallback: if Anthropic 429/500 → try DeepSeek V3
    const isRateLimit = err instanceof Error && (err.message.includes("529") || err.message.includes("overloaded") || err.message.includes("rate_limit"));
    if (isRateLimit && DEEPSEEK_KEY) {
      console.warn("Anthropic overloaded → falling back to DeepSeek V3");
      const res = await fetch("https://api.deepseek.com/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${DEEPSEEK_KEY}` },
        body: JSON.stringify({ model: "deepseek-chat", messages: [{ role: "user", content: prompt }], max_tokens: 4096 }),
        signal: AbortSignal.timeout(30_000),
      });
      const data = await res.json() as { choices?: Array<{ message?: { content?: string } }> };
      const text = data.choices?.[0]?.message?.content || "";
      return text.replace(/```json|```/g, "").trim();
    }
    throw err;
  }
}

// ── Date helper ───────────────────────────────────────────────────────────────
function todayStr() {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'America/New_York'
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// PROPHET — single best pick of the day
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/prophet', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 10, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const today = todayStr();
    const sport = ((req.query.sport as string) || '').toUpperCase();
    const sportFilter = sport ? `Focus ONLY on ${sport} games.` : 'Scan all sports (NBA, WNBA, MLB, NHL, SOCCER/World Cup, TENNIS, NFL — whatever is on tonight).';
    const prophetSport = sport || 'ALL';
    const isAll = prophetSport === 'ALL';
    // June 2026: World Cup is primary for ALL mode. SOCCER heuristics + context loaded first.
    const activeSport = isAll ? 'SOCCER' : prophetSport;
    const heuristics = getBettingHeuristics(isAll ? 'SOCCER' : prophetSport);
    const [liveOdds, scheduleCtx, injuryData, newsData, advancedData, sharpSignals, sportCtx, supplementalCtx, historicalCtx] = await Promise.all([
      fetchLiveOdds(activeSport),
      activeSport === 'NBA' || activeSport === 'WNBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(activeSport),
      fetchInjuries(activeSport),
      fetchESPNNews(activeSport),
      activeSport === 'NBA' || activeSport === 'WNBA' ? fetchNBALeagueSnapshot() : Promise.resolve(''),
      fetchSharpSignals(activeSport),
      activeSport === 'SOCCER'  ? fetchSoccerContext('')
        : activeSport === 'TENNIS' ? fetchTennisContext('')
        : Promise.resolve(''),
      // ALL mode: also pull NBA Finals odds + Tennis context as supplemental cross-sport data
      isAll
        ? Promise.all([fetchLiveOdds('NBA'), fetchLiveOdds('TENNIS'), fetchTennisContext('')])
            .then(r => r.filter(Boolean).join('\n\n'))
        : Promise.resolve(''),
      // Google Search: real historical stats, ATS trends, H2H records from credible sources
      fetchHistoricalContext(activeSport, ''),
    ]);
    const prompt = `
${SHARP_IDENTITY()}

You are a sharp professional sports bettor with 15 years of experience beating closing lines.
Today is ${today} (Eastern Time). ${sportFilter}

${heuristics}

${liveOdds}
${scheduleCtx ? `\n${scheduleCtx}` : ''}
${sportCtx ? `\n${sportCtx}` : ''}
${supplementalCtx ? `\nCROSS-SPORT SUPPLEMENTAL (NBA Finals + Tennis):\n${supplementalCtx}` : ''}
${advancedData ? `\n${advancedData}` : ''}
${injuryData ? `\nINJURY REPORT (ESPN — LIVE):\n${injuryData}` : ''}
${newsData ? `\nLATEST NEWS (ESPN):\n${newsData}` : ''}
${sharpSignals ? `\n${sharpSignals}` : ''}
${historicalCtx ? `\n${historicalCtx}` : ''}

IMPORTANT: Lines above are REAL from Pinnacle/DraftKings — use exact lines, do not invent.
Injuries are LIVE from ESPN — apply Next Man Up logic immediately.
Sharp signals = Pinnacle vs DK devigged fair-prob gap ≥3 pts — follow the sharp side.
News = live ESPN headlines — questionable/out tags reprice the market.
Historical data is REAL from ESPN official API — only cite numbers that appear verbatim in the ESPN RECORDS block.

${ANTI_HALLUCINATION_DIRECTIVE}

Your job: identify TODAY's single highest-conviction bet from the LIVE ODDS block above.

Internal reasoning (do not include in output):
1. Scan LIVE ODDS block — only consider games listed there
2. Check INJURY REPORT — any key player out or doubtful that moves the line?
3. Check SHARP SIGNALS — Pinnacle vs DK gap? Follow sharp direction.
4. Check NEWS block — any lineup news or questionable tags?
5. Select top pick — pick the bet where data blocks provide the clearest edge signal
6. Write logic_bullets using ONLY facts from the data blocks above

Output ONLY a raw JSON object — no markdown:
{
  "selection": "Exact bet from LIVE ODDS — e.g. Celtics -4.5 or Brunson Over 25.5 Points",
  "odds": "American odds exactly as in LIVE ODDS block — e.g. -115 or +130",
  "game_name": "Team A vs Team B — League — TIME ET",
  "recommended_unit": "1 UNIT or 2 UNITS",
  "logic_bullets": [
    "[SOURCE]: specific fact from a data block — e.g. [INJURY REPORT]: Gobert questionable",
    "[SOURCE]: second sourced fact — e.g. [SHARP SIGNALS]: Pinnacle -118 vs DK -110",
    "[SOURCE]: third sourced fact — e.g. [LIVE ODDS]: line moved from -3 to -4.5 since open"
  ],
  "correlated_insight": "One other bet from the SAME game in LIVE ODDS that correlates — or null"
}

Real player names, real team names. Every logic bullet must have a [SOURCE] tag.
`.trim();

    const prophetCacheKey = `prophet:${prophetSport}`;
    const prophetCached = getCached(prophetCacheKey);
    if (prophetCached) { res.json(prophetCached); return; }

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }

    // ── Math-computed fields (ground truth — not AI) ──────────────────────────
    let implied_prob: number | null = null;
    let payout_100: number | null = null;
    let edge_pct: number | null = null;
    let devigged_prob: number | null = null;
    let predictedProb: number | null = null;  // model win prob (0-1) — for calibration
    try {
      const oddsStr = String(parsed.odds ?? '');
      const oddsNum = parseInt(oddsStr.replace(/[^\d-]/g, ''), 10);
      if (!isNaN(oddsNum) && oddsNum !== 0) {
        implied_prob = Math.round(impliedProb(oddsNum) * 1000) / 10;        // e.g. 52.4
        // Vig removal: divide by typical 2-way overround (~4.5% at -110/-110).
        // Fair prob is LOWER than implied — book juice inflates implied prob.
        const TYPICAL_OVERROUND = 1.045;
        devigged_prob = Math.round((implied_prob / TYPICAL_OVERROUND) * 10) / 10;
        const dec = toDecimal(oddsNum);
        payout_100 = Math.round((dec - 1) * 100 * 10) / 10;                 // net profit on $100 bet
        const aiWinProb = typeof parsed.win_prob === 'number' ? parsed.win_prob as number : null;
        if (aiWinProb !== null) {
          predictedProb = aiWinProb;
          edge_pct = Math.round((aiWinProb - implied_prob / 100) * 1000) / 10;
        }
      }
    } catch { /* non-blocking */ }

    // QUALITY RULE — winning first, value second. If the market says the OTHER
    // side wins ≥55% of the time, the pick is a contrarian longshot: flag it loud.
    const UPSET_ALERT_THRESHOLD = 45; // pick's fair prob below this = other side ≥55%
    const upset_alert = devigged_prob != null && devigged_prob < UPSET_ALERT_THRESHOLD
      ? `⚠️ MARKET DISAGREES — this pick wins ~${devigged_prob}% of the time; the other side is the real favorite (~${Math.round((100 - devigged_prob) * 10) / 10}%). Quality rule: favor likely winners. Treat as longshot stake or skip.`
      : null;

    // Auto-lint — gate the pick's own price band before it ships (rule 11 enforcement).
    // Single-leg lint flags chalk (<1.50) / lottery (5.0+) the model shouldn't fire on.
    let lint: unknown = null;
    try {
      const lintOdds = parseInt(String(parsed.odds ?? '').replace(/[^\d-]/g, ''), 10);
      if (Number.isFinite(lintOdds) && Math.abs(lintOdds) >= 100) {
        lint = await lintLegs([{ decimal: toDecimal(lintOdds), selection: String(parsed.selection ?? 'pick') }]);
      }
    } catch { /* non-blocking */ }

    const result = {
      ...parsed,
      implied_prob,    // math only — never hallucinated
      devigged_prob,   // math only — never hallucinated
      payout_100,      // math only — never hallucinated
      edge_pct,        // math only — never hallucinated
      upset_alert,     // math only — fires when pick's fair win prob < 45%
      lint,            // pre-bet gate verdict on this pick's price band
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
    };
    // 60 min — slates don't reprice fast; halves repeat LLM cost without pick staleness
    setCache(prophetCacheKey, result, 60 * 60 * 1000);

    // Auto-log to the ledger — record builds itself, no cherry-picking possible.
    // Skip if the same selection is already pending today (dedupe across cache misses).
    try {
      const selection = String(parsed.selection ?? '');
      const oddsNum = parseInt(String(parsed.odds ?? '').replace(/[^\d-]/g, ''), 10);
      if (selection && Number.isFinite(oddsNum) && Math.abs(oddsNum) >= 100) {
        const ledger = await loadLedger();
        const today_ = new Date().toISOString().slice(0, 10);
        const dupe = ledger.some(p =>
          p.result === 'PENDING' && p.selection === selection && p.created_at.startsWith(today_)
        );
        if (!dupe) {
          const gameName = String(parsed.game_name ?? '');
          await addPick({
            sport: prophetSport,
            game: gameName,
            selection,
            odds: oddsNum,
            stake_units: /2\s*UNIT/i.test(String(parsed.recommended_unit ?? '')) ? 2 : 1,
            source: 'prophet',
            predicted_prob: predictedProb,  // model win prob — for calibration
            ...parseSelectionIdentity(selection, gameName),  // structured identity for CLV capture
          });
        }
      }
    } catch (e: unknown) {
      console.error('Prophet auto-log failed:', e instanceof Error ? e.message : String(e));
    }

    res.json(result);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("PROPHET_FAILURE:", msg);
    res.status(500).json({ error: "PROPHET_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// ANALYZE-UNIFIED — full swarm analysis for a specific matchup
// ─────────────────────────────────────────────────────────────────────────────
app.post('/api/analyze-unified', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const { matchup, sport } = req.body;
    if (!matchup) return res.status(400).json({ error: "MATCHUP_REQUIRED" });

    const today = todayStr();
    const league = (sport || 'NBA').toUpperCase();
    const swarmHeuristics = getBettingHeuristics(league);

    const getMatchupCtx = () => {
      if (league === 'NBA' || league === 'WNBA') return fetchNBAPlayerStats(matchup);
      if (league === 'NHL') return fetchNHLTeamStats(matchup);
      if (league === 'MLB') return fetchMLBPitcherStats(matchup);
      if (league === 'SOCCER') return fetchSoccerContext(matchup);
      if (league === 'TENNIS') return fetchTennisContext(matchup);
      return fetchESPNScoreboard(league);
    };
    const getNBAMetrics = () =>
      (league === 'NBA' || league === 'WNBA') ? fetchNBAAdvancedStats(matchup) : Promise.resolve('');

    const [swarmLiveOdds, swarmNbaCtx, swarmInjuries, swarmSharp, swarmAdvanced] = await Promise.all([
      fetchLiveOdds(league, matchup),
      getMatchupCtx(),
      fetchInjuries(league, matchup),
      fetchSharpSignals(league),
      getNBAMetrics(),
    ]);

    // ── Harvard Math Layer + Quant Model (XGBoost) ───────────────────────────
    const oddsGame = parseOddsForTeams(swarmLiveOdds);

    // Real injury input: count OUT/Doubtful players from the live ESPN report.
    // Crude but sourced — replaces the hardcoded 0 that made the math layer blind.
    const injuryOuts = (swarmInjuries.match(/\b(Out|Doubtful)\b/gi) ?? []).length;
    const injuryImpact = Math.min(20, injuryOuts * 4);

    let swarmHarvardCtx = '';
    try {
      // The Harvard engine is a 2-way win-prob stack. For soccer (3-way) a
      // home-vs-away devig ignores the draw and inflates the prior, so its edge
      // is fiction — the SOCCER MARKET BOARD owns 3-way pricing instead.
      if (league === 'SOCCER') throw new Error('soccer handled by market board, not 2-way Harvard');
      const hImp = oddsGame?.homeOdds != null ? impliedProb(oddsGame.homeOdds) : 0;
      const aImp = oddsGame?.awayOdds != null ? impliedProb(oddsGame.awayOdds) : 0;
      const dv = hImp && aImp ? devig(hImp, aImp) : null;
      if (!dv) throw new Error('no parseable 2-way odds for Harvard prior');
      const hRes = await fetch('http://127.0.0.1:8002/harvard/master', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prior_prob: dv.p1,
          market_spread: oddsGame?.spread ?? 0,
          decimal_odds: oddsGame?.homeOdds != null ? toDecimal(oddsGame.homeOdds) : 1.909,
          bankroll: 100, injury_impact: injuryImpact, rest_advantage: 0, distraction_index: 0,
          line_move_known: false, line_move_toward_team: false,
          wins_in_sample: 10, losses_in_sample: 10,
          observed_wins: 10, observed_losses: 10,
        }),
        signal: AbortSignal.timeout(4000),
      });
      if (hRes.ok) {
        const h = await hRes.json() as { stacked_final_prob: number; edge_pct: number; verdict: string; edge_significant: boolean };
        swarmHarvardCtx = `\n━━ HARVARD ENGINE: Final prob ${(h.stacked_final_prob * 100).toFixed(1)}% | Edge ${h.edge_pct > 0 ? '+' : ''}${h.edge_pct}% | ${h.verdict} | Significant: ${h.edge_significant ? 'YES' : 'NO'}`;
      }
    } catch (e: unknown) {
      // Non-blocking, but NEVER silent — a dead math layer hid for days this way
      console.error('Harvard engine unavailable:', e instanceof Error ? e.message : String(e));
    }

    // ── Quant Model — trained XGBoost margin predictor (port 8001) ──────────
    // Presented with its own error bars: cover prob recomputed with model MAE
    // folded into the variance so a stale model can't masquerade as certainty.
    let quantCtx = '';
    try {
      // SOCCER is owned by the market board (/predict-soccer) — the XGBoost margin
      // model runs on club-based ratings that are unreliable for WC national teams
      // (Haiti rated above Brazil), so feeding its goal-margin here only misleads.
      if (oddsGame && league === 'TENNIS') {
        // Tennis uses the logistic WIN-PROB model (points + surface + comparative
        // profile: H2H / form / psych / clutch), NOT the XGBoost margin path. Pass
        // the match surface so surface affinity AND surface-aware H2H engage.
        const surface = tennisActiveSurface();
        // Live/in-play: if the match is on court right now, re-price off the
        // actual set score (tennis_live.py) instead of only the pregame number.
        const liveScore = await fetchTennisLiveSetScore(oddsGame.home, oddsGame.away);
        // Feed the Kronos line-history store off odds already fetched for this
        // real pick — builds real line-movement data with zero extra API calls.
        recordTennisLineSnapshot(oddsGame.home, oddsGame.away, oddsGame.homeOdds);
        const tRes = await fetch('http://127.0.0.1:8001/predict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sport: 'TENNIS',
            home_team: oddsGame.home, away_team: oddsGame.away,
            spread: oddsGame.spread, home_odds: oddsGame.homeOdds, away_odds: oddsGame.awayOdds,
            surface,
            ...(liveScore ? {
              sets_won_home: liveScore.setsWonHome,
              sets_won_away: liveScore.setsWonAway,
              best_of: liveScore.bestOf,
            } : {}),
          }),
          signal: AbortSignal.timeout(4000),
        });
        if (tRes.ok) {
          const t = await tRes.json() as {
            home_cover_prob: number | null; away_cover_prob: number | null;
            home_true_prob: number | null; bet_signal?: string;
            pick_quality?: string; quality_note?: string;
            method?: string; surface?: string; profile?: Record<string, number>;
            live?: { sets_won_home: number; sets_won_away: number; pregame_match_prob_home: number };
          };
          if (t.bet_signal === 'NO_DATA' || t.home_cover_prob == null) {
            quantCtx = `━━ TENNIS MODEL: no ranking data for one/both players — model offers NO opinion. Rely on market devig + surface heuristics only.`;
          } else {
            const winH = (t.home_cover_prob * 100).toFixed(1);
            const winA = ((t.away_cover_prob ?? 1 - t.home_cover_prob) * 100).toFixed(1);
            const mktH = t.home_true_prob != null ? (t.home_true_prob * 100).toFixed(1) : '?';
            const edgeH = t.home_true_prob != null ? (t.home_cover_prob - t.home_true_prob) * 100 : null;
            const p = t.profile ?? {};
            const dim = (label: string, v?: number) =>
              v == null ? '' : ` ${label} ${v > 0 ? '+' : ''}${v}`;
            const profileLine = [
              dim('H2H', p.h2h), dim('form', p.form_diff), dim('psych', p.psych_diff),
              dim('clutch', p.clutch_diff), dim('streak', p.streak_diff),
            ].filter(Boolean).join(' |') || ' (no profile data for this pair)';
            const liveLine = t.live
              ? `🔴 LIVE — set score ${t.live.sets_won_home}-${t.live.sets_won_away} (${oddsGame.home}-${oddsGame.away}). ` +
                `Pregame was ${(t.live.pregame_match_prob_home * 100).toFixed(1)}% ${oddsGame.home} — the ${winH}% above is the RE-PRICED live number, use it over the pregame line.\n`
              : '';
            quantCtx =
              `━━ TENNIS WIN-PROB MODEL (${t.method ?? 'logistic'} on ${t.surface ?? surface}):\n` +
              liveLine +
              `Model: ${oddsGame.home} ${winH}% vs ${oddsGame.away} ${winA}% | Market devig: ${oddsGame.home} ${mktH}%` +
              (edgeH != null ? ` | Edge ${edgeH > 0 ? '+' : ''}${edgeH.toFixed(1)}pp ${oddsGame.home}` : '') + `\n` +
              `Comparative profile (home − away, surface-aware):${profileLine}\n` +
              `Signal: ${t.bet_signal ?? 'NO_EDGE'}. Tennis is noisy — trust the bet_signal over raw EV%.\n` +
              `Pick quality: ${t.pick_quality ?? 'n/a'} — ${t.quality_note ?? ''} (LOCK=anchor · PICK=parlay-ok · LEAN=single/small, NEVER a parlay anchor)\n` +
              `⚠️ OVERRIDE: confirmed day-of data (injury, withdrawal, conditions) beats this historical model. If a player is hurt or just withdrew, ignore the model edge.`;
          }
        }
      } else if (oddsGame && league !== 'SOCCER') {
        const qRes = await fetch('http://127.0.0.1:8001/predict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sport: league,
            home_team: oddsGame.home, away_team: oddsGame.away,
            spread: oddsGame.spread, home_odds: oddsGame.homeOdds, away_odds: oddsGame.awayOdds,
            neutral: league === 'SOCCER', // WC 2026 — neutral venues
          }),
          signal: AbortSignal.timeout(4000),
        });
        if (qRes.ok) {
          const q = await qRes.json() as {
            predicted_margin: number | null; model_edge: number | null; model_mae: number | null;
            trained_on: number; bet_signal?: string;
            pick_quality?: string; quality_note?: string;
            home_ratings?: { net_rtg?: number }; away_ratings?: { net_rtg?: number };
            profile?: { home?: WnbaTeamForm; away?: WnbaTeamForm;
              h2h?: { n: number; w: number; l: number; margin: number; last: string } } | null;
          };
          // Real WNBA form/rest/H2H block (built from ESPN results). B2B fatigue
          // is the biggest WNBA edge — surface it loudly.
          const wp = q.profile;
          const wForm = (t?: WnbaTeamForm): string | null =>
            t ? `${t.team}: ${t.win_rate ? (t.win_rate*100).toFixed(0) : '?'}% (L10 ${t.last10}), margin ${t.avg_margin >= 0 ? '+' : ''}${t.avg_margin}, ${t.streak}, ${t.b2b ? '⚠️ ON B2B (tired legs)' : `${t.rest_days ?? '?'}d rest`}, home ${t.home}/road ${t.road}` : null;
          const wnbaBlock = wp ? '\n━━ WNBA FORM & REST (real ESPN results): ' + [
            wForm(wp.home), wForm(wp.away),
            wp.h2h ? `H2H ${wp.h2h.w}-${wp.h2h.l} (avg margin ${wp.h2h.margin >= 0 ? '+' : ''}${wp.h2h.margin}, last ${wp.h2h.last})` : null,
          ].filter(Boolean).join(' | ') : '';
          if (q.bet_signal === 'NO_DATA' || q.model_edge == null || q.model_mae == null) {
            // Model honestly refuses on unknown teams (e.g. WC national squads)
            quantCtx = `━━ QUANT MODEL: no training data for these teams — model offers NO opinion. Rely on market devig + heuristics only.${wnbaBlock}`;
          } else {
            const GAME_SIGMA: Record<string, number> = { NBA: 11.5, WNBA: 9.5, NFL: 13.5, MLB: 3.0, TENNIS: 30.0, SOCCER: 2.0 };
            const sigma = GAME_SIGMA[league] ?? 11.5;
            // MAE → σ_model ≈ 1.25·MAE (normal); combine with game variance
            const sigmaTotal = Math.sqrt(sigma ** 2 + (1.25 * q.model_mae) ** 2);
            const coverProb = normalCDF(q.model_edge / sigmaTotal);
            quantCtx =
              `━━ QUANT MODEL (XGBoost margin predictor — trained on ${q.trained_on} games, MAE ${q.model_mae} pts, ratings frozen at last training):\n` +
              `Predicted margin: ${oddsGame.home} by ${q.predicted_margin} | Market spread: ${oddsGame.spread}\n` +
              `Cover prob WITH model error included: ${(coverProb * 100).toFixed(1)}% ${oddsGame.home} | NetRtg: ${q.home_ratings?.net_rtg ?? '?'} vs ${q.away_ratings?.net_rtg ?? '?'}\n` +
              `⚠️ Model edge ${q.model_edge} pts vs market. If >7 pts, treat as STALE-DATA WARNING — the market knows something the training data doesn't. Weigh market over model on big disagreements.\n` +
              `Pick quality: ${q.pick_quality ?? 'n/a'} — ${q.quality_note ?? ''} (LOCK=anchor · PICK=parlay-ok · LEAN=single/small, NEVER a parlay anchor)${wnbaBlock}`;
          }
        }
      }
    } catch (e: unknown) {
      console.error('Quant model (8001) unavailable:', e instanceof Error ? e.message : String(e));
    }

    // ── Market boards — draw-insured soccer (DC/DNB) + UFC method/rounds ──────
    // SOCCER: market-devigged 1X2 → recommends Double Chance / Draw No Bet / ML.
    //         Authoritative for WC national teams (rating model is unreliable).
    // UFC:    devig ML → routes juiced favourites to value derivatives.
    let marketsCtx = '';
    // Structured Poisson board — same numbers as the prompt text, but as DATA so
    // the Game Breakdown page can chart the model distribution (soccer only).
    let soccerPoisson: PoissonBoard | null = null;
    // Math grade on the model's primary pick (mirrors edge_api.pick_quality:
    // LOCK >=70%, PICK >=62%, LEAN below). A LEAN must be visibly flagged in the
    // UI — a 55% play presented without a warning reads like a lock and isn't.
    let soccerGrade: PickGrade | null = null;
    try {
      if (league === 'SOCCER' && oddsGame && oddsGame.drawOdds != null) {
        const sRes = await fetch('http://127.0.0.1:8001/predict-soccer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            home_team: oddsGame.home, away_team: oddsGame.away, neutral: true,
            home_odds: oddsGame.homeOdds, draw_odds: oddsGame.drawOdds, away_odds: oddsGame.awayOdds,
          }),
          signal: AbortSignal.timeout(4000),
        });
        if (sRes.ok) {
          const s = await sRes.json() as {
            markets?: {
              totals?: Record<string, { over: number; under: number }>;
              btts?: { yes: number; no: number };
              expected_total_goals?: number;
              correct_score?: { score: string; prob: number; fair_decimal_odds: number | null }[];
            };
            simulation?: {
              n_sims: number;
              top_simulated_scores?: { score: string; prob: number }[];
              simulated_1x2?: { home?: SimHitRate; draw?: SimHitRate; away?: SimHitRate };
              simulated_btts_yes?: SimHitRate;
              simulated_over_2_5?: SimHitRate;
              correlated?: Record<string, SimHitRate>;
            };
            data_fit_ratings?: {
              home?: TeamFitRating | null; away?: TeamFitRating | null;
              league?: string; note?: string;
            } | null;
            lambda_source?: string;
            upset_risk?: { level: string; non_win_prob: number; favourite_true_win: number;
              reasons: string[]; protective_action: string };
            chaos?: { grade: string; draw_score: number; favourite: string;
              side: string | null; market: string | null; value_ok: boolean | null; evidence: string[] };
            market_recommendation?: { primary_pick?: { market: string; side: string; model_prob: number };
              win_draw_lose?: { win: number; draw: number; lose: number };
              double_chance?: { fav_or_draw: number }; draw_no_bet?: { fav: number }; favorite?: string };
            profile?: {
              home?: SoccerTeamForm; away?: SoccerTeamForm;
              h2h?: { n: number; w: number; d: number; l: number; gf: number; ga: number; last: string };
            };
          };
          const mr = s.market_recommendation;
          if (mr?.primary_pick && mr.win_draw_lose) {
            const w = mr.win_draw_lose;
            // Totals/BTTS are now market-CALIBRATED (Poisson fit to the devigged
            // 1X2), so they're consistent with the sharp price — safe for SGP legs.
            const ou = s.markets?.totals?.['2.5'];
            const ouSide = ou ? (ou.over >= ou.under ? `Over 2.5 ${(ou.over*100).toFixed(0)}%` : `Under 2.5 ${(ou.under*100).toFixed(0)}%`) : 'n/a';
            const btts = s.markets?.btts;
            const bttsSide = btts ? (btts.yes >= btts.no ? `BTTS Yes ${(btts.yes*100).toFixed(0)}%` : `BTTS No ${(btts.no*100).toFixed(0)}%`) : 'n/a';
            const xg = s.markets?.expected_total_goals;
            // Correct score + Monte Carlo — grounds the "simulation" swarm section in the
            // real Poisson/Dixon-Coles matrix instead of the LLM guessing a score line.
            const allScores = s.markets?.correct_score ?? s.simulation?.top_simulated_scores ?? [];
            const topScores = allScores.slice(0, 3);
            soccerPoisson = {
              favorite: mr.favorite,
              win_draw_lose: w,
              correct_score: allScores.slice(0, 8).map(c => ({ score: c.score, prob: c.prob })),
              expected_total_goals: s.markets?.expected_total_goals,
              totals: s.markets?.totals,
              btts: s.markets?.btts,
              lambda_source: s.lambda_source,
              n_sims: s.simulation?.n_sims,
              sim_1x2: s.simulation?.simulated_1x2,
              sim_over_2_5: s.simulation?.simulated_over_2_5,
              sim_btts_yes: s.simulation?.simulated_btts_yes,
              correlated: s.simulation?.correlated,
              ratings: s.data_fit_ratings ? {
                home: s.data_fit_ratings.home, away: s.data_fit_ratings.away,
                home_team: oddsGame.home, away_team: oddsGame.away,
                league: s.data_fit_ratings.league,
              } : undefined,
            };
            const gp = mr.primary_pick.model_prob;
            soccerGrade = {
              grade: gp >= 0.70 ? 'LOCK' : gp >= 0.62 ? 'PICK' : 'LEAN',
              win_prob: gp,
              market: mr.primary_pick.market,
              side: mr.primary_pick.side,
            };
            const correctScoreLine = topScores.length
              ? `\nCorrect score (Poisson+DixonColes, n=${s.simulation?.n_sims ?? 'closed-form'}): ` +
                topScores.map(c => `${c.score} ${(c.prob*100).toFixed(0)}%`).join(' | ')
              : '';
            // Upset / public-trap flag — only surface when ELEVATED or HIGH.
            const up = s.upset_risk;
            const upsetLine = (up && up.level !== 'LOW')
              ? `\n⚠️ UPSET RISK ${up.level} — favourite wins only ${(up.favourite_true_win*100).toFixed(0)}%, does NOT win ${(up.non_win_prob*100).toFixed(0)}%. ${up.reasons.join(' ')} → ${up.protective_action}`
              : '';
            // Chaos engine read — only surface when a graded flag fires (LITE/FULL).
            const ch = s.chaos;
            const chaosLine = (ch && ch.grade !== 'NONE')
              ? `\n🌀 CHAOS ${ch.grade} — back ${ch.side} [${ch.market}], draw_score ${ch.draw_score}${ch.value_ok === true ? ' (clears value)' : ch.value_ok === false ? ' (fails value gate)' : ''}. ${(ch.evidence || []).slice(-2).join(' ')}`
              : '';
            // Real form + H2H (recency × competitiveness weighted internationals).
            const pf = s.profile;
            const teamForm = (t?: SoccerTeamForm): string | null =>
              t ? `${t.team}: ${t.form_ppg}ppg, GF ${t.gf}/GA ${t.ga}, O2.5 ${(t.over25*100).toFixed(0)}%, BTTS ${(t.btts*100).toFixed(0)}%, CS ${(t.clean_sheet*100).toFixed(0)}%, ${t.streak} [${t.last5}]` : null;
            const profLines = pf ? [
              teamForm(pf.home), teamForm(pf.away),
              pf.h2h ? `H2H ${pf.home?.team ?? 'home'} ${pf.h2h.w}-${pf.h2h.d}-${pf.h2h.l} (avg ${pf.h2h.gf}-${pf.h2h.ga}, last ${pf.h2h.last})` : null,
            ].filter(Boolean) : [];
            const profileBlock = profLines.length
              ? `\n━━ FORM & H2H (real internationals): ${profLines.join(' | ')}\n⚠️ Confirmed day-of data (injuries, lineups, rest days, weather) overrides this historical form. Group-stage rest gap (a team with fewer days since last match) = fatigue edge — check the real schedule.`
              : '';
            marketsCtx =
              `━━ SOCCER MARKET BOARD (devigged 3-way + market-calibrated Poisson — sharp, draw priced):\n` +
              `Fav ${mr.favorite}: win ${(w.win*100).toFixed(0)}% / draw ${(w.draw*100).toFixed(0)}% / lose ${(w.lose*100).toFixed(0)}%\n` +
              `Double Chance (gana o empata) ${((mr.double_chance?.fav_or_draw ?? 0)*100).toFixed(0)}% | Draw No Bet (apuesta sin empate) ${((mr.draw_no_bet?.fav ?? 0)*100).toFixed(0)}%\n` +
              `Totals/BTTS (market-calibrated${xg != null ? `, xGoals ${xg.toFixed(2)}` : ''}): ${ouSide} | ${bttsSide}` +
              correctScoreLine + `\n` +
              `>>> DRAW-INSURED PICK: ${mr.primary_pick.side} [${mr.primary_pick.market}] @ ${(mr.primary_pick.model_prob*100).toFixed(0)}%` +
              upsetLine + chaosLine + profileBlock + `\n` +
              `Rule: straight Win only when the price isn't heavy chalk (≳ -250) AND beats its devig; if "better but not dominant", insure the draw with DC/DNB when DC pays ~1.40-2.50; if the fav is HEAVY chalk (e.g. -511) the ML/DC have NO value — take the handicap (-1.5/-2.5), team total or correct score, else PASS. Build correlated SGP from calibrated legs (e.g. fav handicap + Over + BTTS that agree).`;
          }
        }
      } else if (league === 'UFC' && oddsGame) {
        const uRes = await fetch('http://127.0.0.1:8001/predict-ufc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            fighter_a: oddsGame.away, fighter_b: oddsGame.home,
            ml_a: oddsGame.awayOdds, ml_b: oddsGame.homeOdds,
          }),
          signal: AbortSignal.timeout(4000),
        });
        if (uRes.ok) {
          const u = await uRes.json() as {
            markets?: { moneyline?: Record<string, number>; distance?: { not_distance: number } };
            recommendation?: { primary_pick?: { market: string; side: string; model_prob: number; ev_pct?: number };
              method_lean?: { side: string; model_prob: number } };
            used_empirical_priors?: boolean;
          };
          const rp = u.recommendation?.primary_pick;
          if (rp) {
            const ml = u.markets?.moneyline ?? {};
            const mlStr = Object.entries(ml).map(([k, v]) => `${k} ${(v*100).toFixed(0)}%`).join(' / ');
            marketsCtx =
              `━━ UFC MARKET BOARD (devig ML${u.used_empirical_priors ? ' + empirical finish priors — FLAG as league-average, not fighter stats' : ''}):\n` +
              `Moneyline: ${mlStr} | Ends inside distance: ${((u.markets?.distance?.not_distance ?? 0)*100).toFixed(0)}%\n` +
              `>>> PICK: ${rp.side} [${rp.market}] @ ${(rp.model_prob*100).toFixed(0)}%${rp.ev_pct != null ? ` (EV ${rp.ev_pct}%)` : ''}\n` +
              `Most likely method: ${u.recommendation?.method_lean?.side} ${((u.recommendation?.method_lean?.model_prob ?? 0)*100).toFixed(0)}%`;
          }
        }
      }
    } catch (e: unknown) {
      console.error('Market board (8001) unavailable:', e instanceof Error ? e.message : String(e));
    }

    const liveOddsBlock = [
      swarmLiveOdds   ? `\nLIVE ODDS FOR THIS GAME (use these exact lines):\n${swarmLiveOdds}` : '',
      swarmNbaCtx     ? `\n${swarmNbaCtx}` : '',
      swarmAdvanced   ? `\n${swarmAdvanced}` : '',
      swarmInjuries   ? `\n${swarmInjuries}` : '',
      swarmSharp      ? `\n${swarmSharp}` : '',
      swarmHarvardCtx ? `\n${swarmHarvardCtx}` : '',
      quantCtx        ? `\n${quantCtx}` : '',
      marketsCtx      ? `\n${marketsCtx}` : '',
    ].filter(Boolean).join('\n');

    // ── Sport playbook — money discipline injected per league ────────────────
    const VALUE_DISCIPLINE = `
💰 MONEY DISCIPLINE (this is how we actually profit — non-negotiable):
- RANK every candidate by WIN PROBABILITY FIRST, then by value (edge vs price). Favor likely winners over longshots.
- 🎯 SCAN EVERY MARKET — DO NOT DEFAULT TO THE MONEYLINE. From the LIVE ODDS / MARKET BOARD, enumerate EVERY available market: moneyline (win), draw / double chance / draw-no-bet, spread / handicap (incl. alternates), totals over/under (incl. alternates), team totals, BTTS, sport-specific derivatives (UFC method/round/distance), AND the sport's niche PLAYER PROPS (the heuristics list the menu per sport). From the stats + simulation, estimate EACH market's true win probability, compare it to that market's own devigged implied price, and pick the SINGLE market with the highest win-prob that also clears the value gate. The winner is whatever TYPE wins this comparison — an Over/Under, handicap, double chance, or a player prop can absolutely beat the straight win (e.g. "Brazil ML is a coin-flip but Over 2.5 wins 64% of sims → take Over 2.5"). PROP GUARD: only float a prop when REAL player stats are in context; if the prop line isn't on the live board, mark it a "lean", never invent the number. Name why the chosen market beat the runner-up.
- A bet only has VALUE when its win probability BEATS the devigged implied price. If a market board / devig prob is shown, the pick prob must exceed the implied prob of its odds. If it does not, it is NOT a bet — say "no value, pass".
- 🚫 NO-VALUE CHALK IS NOT A PICK — the best single bet can NEVER be a no-value pick. A heavy favourite priced ≈ -250 (1.40 decimal) or shorter — e.g. -511 — lays a fortune for pennies: even at its true win %, the price returns ~no edge and one slip is a disaster. Do NOT headline it, and do NOT "insure" it with a Double Chance / DNB priced under ~1.40 (that's also no value). On heavy chalk the value lives in the DERIVATIVE the favourite wins BY — handicap (-1.5 / -2.5), team/alt total, correct score, winning margin, or UFC method/round. Take the derivative that clears the value gate; if none does, PASS.
- Prefer the SHARPEST market for the read: in soccer that means the draw-insured market when the favourite is "better but not dominant".
- 🚫 DISCIPLINED PASS: if NO market clears the value gate, set primary_single to "PASS — no value" and primary_odds to "". A skipped bad spot protects the bankroll and the record. Do NOT manufacture a pick to fill the slot. (SGP/TikTok may still describe the lean, but the headline pick is PASS.)
- 🔒 BOARD-CONSISTENCY LOCK: when a MARKET BOARD block is present (soccer/UFC), the final primary_single MUST follow its ">>> recommended pick" unless value_check cites a SPECIFIC sourced reason (injury/lineup/weather/line-move) to deviate. The board is the sharp market — do not drift to a softer narrative pick. VALUE EXCEPTION: the board sets the SIDE/read, but the VALUE GATE sets which MARKET you actually bet. If the board's pick is no-value heavy chalk (ML or DC priced shorter than ~ -250 / 1.40 dec), do NOT bet it — express the SAME side through a market with value (the favourite's handicap -1.5 / -2.5, team total, correct score), or PASS. Never headline a no-value pick just to match the board.
- 📉 LINE-VALUE / CLV: beating the CLOSING line is the long-run proof of edge. Favor the side the devigged SHARP SIGNAL + line movement agree with. If the number has already moved THROUGH your price (you'd be chasing steam past the value), the edge is gone — PASS or pivot to the derivative that still prices value. Never bet into a line that moved AGAINST your read without a sourced reason (that is the market telling you something you missed).`.trim();

    const soccerPlaybook = `
⚽ WORLD CUP MONEY PLAYBOOK (follow exactly):
- If a "SOCCER MARKET BOARD" block is present, it is the devigged sharp market with the draw PRICED. Its ">>> DRAW-INSURED PICK" is your default primary_single. Override only with a sourced reason.
- 🚨 UPSET / PUBLIC-TRAP AWARENESS: a "name" favourite the public hammers (Canada, Brazil-Morocco, Panama-Ghana) is NOT the lock it feels like — trust the market's true win %, never the narrative. If the board shows "UPSET RISK ELEVATED/HIGH": say so plainly in the report, do NOT headline the straight Win, default to Double Chance / Draw No Bet or the +value dog, and cut favourite-Win stake to 0.5u. The public being 80% on a side is a fade signal, not a confirmation.
- Draw is a real outcome — a "team to WIN" pick LOSES on a draw (the Canada lesson). But DOUBLE CHANCE / DNB are VALUE tools, not safety blankets: only worth it when the price sits in a real band (~1.40–2.50 decimal / -250 to +150) AND beats its devig — i.e. the favourite is "better but not dominant" (~ -110 to -250) and the dog can genuinely win or draw. When the favourite is HEAVY chalk (shorter than ~ -250, e.g. -511), DC pays ~1.05 = NO value → do NOT headline ML or DC; price the favourite's HANDICAP (-1.5 / -2.5), team total Over, or correct score for the value, else PASS. Straight ML is a candidate only when it isn't crushing juice AND beats its devigged price.
- Build the SGP from CORRELATED legs that tell ONE story: e.g. [Fav Double Chance] + [Under 2.5 if defensive / Over 2.5 if both must-win] + [team total or corners]. Never pair BTTS Yes with Under 2.5.
- Totals & corners are live money: cite the model/market totals lean when shown. Corners are a HEURISTIC proxy — present as "lean", not a hard stat.
- Apply ADVANCEMENT TAGS (qualified=fade, eliminated=fade, must-win=Over/BTTS, can-draw=Under/DNB).`.trim();

    const ufcPlaybook = `
🥊 UFC MONEY PLAYBOOK (follow exactly):
- If a "UFC MARKET BOARD" block is present, use its devigged ML + ">>> PICK". Heavy favourites (≥66%) are ML-juiced — route to the better-paying derivative the fighter actually wins by (does-not-go-distance / by-KO for finishers, by-decision for grinders).
- Method/round/distance numbers from empirical priors must be FLAGGED as league-average, never stated as the fighter's real stat.
- SGP from correlated legs: [Fav ML] + [Under rounds] + [Fav by KO] for a finisher; or [goes the distance] + [Over rounds] for two durable fighters. Never pair "by KO" with "goes the distance".`.trim();

    const sportPlaybook =
      league === 'SOCCER' ? `${VALUE_DISCIPLINE}\n\n${soccerPlaybook}`
      : league === 'UFC'  ? `${VALUE_DISCIPLINE}\n\n${ufcPlaybook}`
      : VALUE_DISCIPLINE;

    // Single unified prompt — all 3 perspectives + TikTok content in 1 call
    const unifiedPrompt = `
You are CAVEMAN LOCKS — a sharp, disciplined sports betting brain that also writes viral short-form scripts. Today is ${today}.
Analyze: ${matchup} (${league})
${liveOddsBlock}
${swarmHeuristics}

${sportPlaybook}

Produce THREE analytical perspectives, synthesize ONE disciplined verdict, then write TikTok content for that verdict.

${ANTI_HALLUCINATION_DIRECTIVE}

Output ONLY this raw JSON (no markdown):
{
  "quant": {
    "primary_single": "Best market by win-prob from the STATS scan across ALL types (ML / draw / DC / DNB / spread / total / team total / BTTS / derivative / player prop — not auto-ML) — description only, no odds here",
    "primary_odds": "-110",
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" }
    ],
    "omni_report": "2 sentences citing SOURCED DATA ONLY. Format: [SOURCE] fact. [SOURCE] fact."
  },
  "simulation": {
    "primary_single": "Simulate the game's score / outcome distribution, then pick the market with the highest win-prob across that distribution (totals & spreads read straight from the sim) — description only",
    "primary_odds": "-180",
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: 1 sourced fact", "espn_id": "" }
    ],
    "omni_report": "2 sentences: cite the real simulated distribution (soccer: the 'Correct score (Poisson+DixonColes)' line in the MARKET BOARD above — use those exact score lines, never invent one; other sports: the quant model's predicted margin/total) and the market it makes most probable. SOURCED DATA ONLY."
  },
  "primary_single": "FINAL best pick — the SINGLE highest win-prob +value market after scanning ALL market types (ML / draw / double chance / DNB / spread / total over-under / team total / BTTS / derivative / player prop). Pick whatever TYPE wins, not the moneyline by default. It MUST have value — a no-value heavy favourite (e.g. -511 ML, or DC on it) can NEVER be the pick; on chalk take the favourite's handicap/total/correct-score, on a live dog take its +value side, else PASS. If nothing clears the value gate, write exactly 'PASS — no value'. Must match the MARKET BOARD pick unless value_check justifies a deviation.",
  "primary_odds": "-115 (or \"\" if PASS)",
  "value_check": "State the pick's win prob vs the devigged implied prob of its odds, AND why this market beat the next-best market type. If prob does NOT beat implied → write 'NO VALUE — PASS'.",
  "sgp_blueprint": [
    { "label": "SGP Leg 1", "value": "Pick from LIVE ODDS + odds", "rationale": "[SOURCE]: sourced fact", "espn_id": "" },
    { "label": "SGP Leg 2", "value": "Correlated leg + odds", "rationale": "[SOURCE]: sourced fact", "espn_id": "" },
    { "label": "SGP Leg 3", "value": "Correlated leg + odds", "rationale": "[SOURCE]: sourced fact", "espn_id": "" }
  ],
  "omni_report": "Final verdict citing SOURCED DATA ONLY. State the pick, the sourced evidence, the value vs price, and the single biggest risk. [HIGH-RISK] if any heuristic violated.",
  "tiktok": {
    "hook": "Scroll-stopping first line, under 8 words, no emoji. Names the pick or the edge.",
    "script": "15-25 sec spoken script in short CAVEMAN voice (punchy, confident, save words). State the pick, ONE sourced reason, and WHY this market (e.g. 'team better but draw scary — we take win-or-draw'). End with a CTA to follow. SOURCED facts only — no invented stats.",
    "on_screen_text": ["3-4 short caption bars for overlay, each under 6 words"],
    "caption": "1-line post caption with the pick and 1 emoji max.",
    "hashtags": ["#CavemanLocks", "#WorldCup2026", "3-5 relevant tags total"]
  }
}
`.trim();

    const cacheKey = `swarm:${league}:${matchup.toLowerCase().replace(/\s+/g, '_')}`;
    const cached = getCached(cacheKey);
    if (cached) { res.json(cached); return; }

    const unifiedRaw = await ask(unifiedPrompt);
    const unified = parseJSON(unifiedRaw) as Record<string, unknown>;

    if (!unified || typeof unified !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }

    // ── Math-computed fields — no AI ─────────────────────────────────────────
    // implied_prob = the bet's own break-even probability from its American odds.
    // (Previously this ADDED a flat +0.02, which inflates every pick ~2-4 pts and
    //  is the wrong direction for vig — removing vig LOWERS a side's probability.)
    const impliedPct = (oddsNum: number): number | null =>
      isNaN(oddsNum) || oddsNum === 0 ? null : Math.round(impliedProb(oddsNum) * 1000) / 10;

    const computePickMath = (agent: Record<string, unknown>) => {
      const oddsStr = String(agent.primary_odds ?? '');
      const oddsNum = parseInt(oddsStr.replace(/[^-\d]/g, ''), 10);
      return {
        ...agent,
        bet_structure: getBetStructure(oddsNum),
        implied_prob: impliedPct(oddsNum),   // break-even probability — math only
      };
    };

    const quantRaw  = unified.quant      as Record<string, unknown> | undefined;
    const simRaw    = unified.simulation as Record<string, unknown> | undefined;
    const topOddsStr = String((unified.primary_odds as string | undefined) ?? '');
    const topOddsNum = parseInt(topOddsStr.replace(/[^-\d]/g, ''), 10);
    const topImp = impliedPct(topOddsNum);

    const exec = unified as SwarmAgentData;
    const payload: SwarmFinalPayload = {
      ...exec,
      bet_structure: getBetStructure(topOddsNum),
      implied_prob: topImp ?? undefined,
      poisson: soccerPoisson ?? undefined,
      pick_grade: soccerGrade ?? undefined,
      swarm_report: {
        quant:      quantRaw ? computePickMath(quantRaw) as SwarmAgentData : undefined,
        simulation: simRaw   ? computePickMath(simRaw)  as SwarmAgentData : undefined,
        audit_verdict: exec.omni_report || "CONVERGENCE_LOCKED"
      },
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
      timestamp: new Date().toLocaleTimeString()
    };

    setCache(cacheKey, payload);
    res.json(payload);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("ANALYZE_FAILURE:", msg);
    res.status(500).json({ error: "ANALYZE_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// ALPHA SHEETS — today's top props cheat sheet (with live odds context)
// ─────────────────────────────────────────────────────────────────────────────
const ALPHA_TEAM_LOGO_HINT: Record<string, string> = {
  NBA:    'NBA team abbreviation e.g. GSW, LAL, BOS',
  WNBA:   'WNBA team abbreviation e.g. LV, NY, CHI',
  NFL:    'NFL team abbreviation e.g. KC, SF, DAL',
  MLB:    'MLB team abbreviation e.g. NYY, LAD, HOU',
  SOCCER: 'Country or club shortname e.g. ARG, BRA, ENG, RMA',
  TENNIS: 'Player country code e.g. ESP, SRB, USA',
  F1:     'Constructor abbreviation e.g. RBR, FER, MER',
};

const ALPHA_PROP_HINT: Record<string, string> = {
  NBA:    'points, rebounds, assists, 3PM, steals, blocks',
  WNBA:   'points, rebounds, assists, 3PM, steals',
  NFL:    'passing yards, rushing yards, receiving yards, TDs, receptions',
  MLB:    'strikeouts, hits, total bases, RBIs, runs, home runs, walks',
  SOCCER: 'shots on target, goals, assists, cards, corners (team), BTTS',
  TENNIS: 'games won, sets won, aces, total games over/under, break points',
  F1:     'race finish position, teammate H2H, podium yes/no, fastest lap, classified finisher',
};

async function generateAlphaSheet(sport: string): Promise<AlphaSheetContainer> {
  const today = todayStr();
  const s = sport.toUpperCase();
  const cacheKey = `alpha:${s}:${today}`;
  const cached = getCached(cacheKey);
  if (cached) return cached as AlphaSheetContainer;

  // Fetch live context so AI uses real lines, not invented ones
  const [liveOdds, injuries, nicheData] = await Promise.all([
    fetchLiveOdds(s),
    fetchInjuries(s),
    s === 'SOCCER'  ? fetchSoccerContext('')
      : s === 'TENNIS' ? fetchTennisContext('')
      : Promise.resolve(''),
  ]);

  const teamLogoHint = ALPHA_TEAM_LOGO_HINT[s] || 'team abbreviation';
  const propHint = ALPHA_PROP_HINT[s] || 'player props';
  const heuristics = getShortHeuristics(s);

  const prompt = `
${SHARP_IDENTITY()}
${ANTI_HALLUCINATION_DIRECTIVE}
You are building a prop betting cheat sheet for ${s}. Today is ${today}.

LIVE ODDS (use ONLY players and lines from here — never invent):
${liveOdds || 'No live odds available right now.'}
${injuries ? `\nINJURY REPORT (LIVE — ESPN):\n${injuries}` : ''}
${nicheData ? `\n${nicheData}` : ''}

${heuristics}

Generate up to 10 prop bets from TODAY's ${s} slate.
STRICT RULES:
- Only pick players that appear in the LIVE ODDS block above
- Only use lines that appear in the LIVE ODDS block — never invent a line
- If a key player is listed as OUT in the INJURY REPORT, target their backup's Over
- rationale: 1 sentence citing ONLY data from the blocks above. Use [SOURCE] tags.
- Do NOT invent season stats, PPG, RPG, or any number not in the data blocks
- espn_id: always ""

Output ONLY raw JSON array:
[
  {
    "rank": 1,
    "team_logo": "${teamLogoHint}",
    "player_name": "Full Name from LIVE ODDS block",
    "metric_label": "PROP TYPE e.g. POINTS or SHOTS ON TARGET",
    "metric_value": "Over/Under LINE ODDS exactly as in LIVE ODDS e.g. Over 27.5 -115",
    "rationale": "[SOURCE]: sourced fact only — no invented stats",
    "espn_id": ""
  }
]
`.trim();

  const raw = await ask(prompt);
  const rawData = parseJSON(raw) as Array<Record<string, unknown>>;

  // Server-side math — never trust AI for numbers
  const data: AlphaSheetItem[] = (Array.isArray(rawData) ? rawData : []).map((item, idx) => {
    // Extract odds from metric_value e.g. "Over 27.5 -115" → -115
    const metricVal = String(item.metric_value ?? '');
    const oddsMatch = metricVal.match(/([+-]\d+)$/);
    const oddsNum = oddsMatch ? parseInt(oddsMatch[1], 10) : NaN;
    const imp = isNaN(oddsNum) ? 50 : Math.round(impliedProb(oddsNum) * 1000) / 10;
    // ai_score: derived from how far implied prob deviates from fair coin (50%)
    // Higher = more decisive market pricing = stronger signal
    const deviation = Math.abs(imp - 50);
    const ai_score = Math.min(9.5, Math.round((5 + deviation * 0.18) * 10) / 10);
    const status_color = ai_score >= 7.5 ? '#22c55e' : ai_score >= 6 ? '#eab308' : '#f97316';

    return {
      rank: typeof item.rank === 'number' ? item.rank : idx + 1,
      team_logo: String(item.team_logo ?? ''),
      player_name: String(item.player_name ?? ''),
      metric_label: String(item.metric_label ?? ''),
      metric_value: metricVal,
      rationale: String(item.rationale ?? ''),
      implied_prob: imp,
      ai_score,
      status_color,
      espn_id: '',
    };
  });

  // Rank by win probability first, signal strength second — favor likely winners over longshots
  data.sort((a, b) => b.implied_prob - a.implied_prob || b.ai_score - a.ai_score);
  const ranked = data.map((item, idx) => ({ ...item, rank: idx + 1 }));

  const titles: Record<string, string> = {
    NBA:    "NBA PROP HEATBOARD",
    WNBA:   "WNBA PROP HEATBOARD",
    NFL:    "NFL PROP SHEET",
    MLB:    "MLB PITCHER + BATTER EDGE",
    SOCCER: "SOCCER / WORLD CUP PROPS",
    TENNIS: "TENNIS EDGE SHEET",
    F1:     "F1 DRIVER PROP SHEET",
  };

  const result: AlphaSheetContainer = {
    title: titles[s] || `${s} PROP SHEET`,
    subtitle: `Caveman Locks AI Edge — ${today}`,
    data: ranked,
    timestamp: new Date().toLocaleDateString()
  };
  setCache(cacheKey, result);
  return result;
}

app.post('/api/alpha-sheets', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const { sport } = req.body;
    const data = await generateAlphaSheet(sport || 'NBA');
    res.json(data);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("ALPHA_SHEET_FAILURE:", msg);
    res.status(500).json({ error: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// PARLAYS — best picks + 4 parlay types, sport-aware
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/parlays', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const game = (req.query.game as string || '').trim();
    const today = todayStr();
    const isAllSports = sport === 'ALL';

    // For cross-sport: fetch NBA + MLB + NHL + NFL + SOCCER + WNBA odds in parallel
    // Only fetch sports currently in-season — saves Odds API credits
    const month = new Date().getMonth() + 1;
    const inSeason = (s: string) => {
      if (s === 'NBA')    return month >= 10 || month <= 6;
      if (s === 'WNBA')   return month >= 5 && month <= 9;
      if (s === 'NFL')    return month >= 9 || month <= 2;
      if (s === 'MLB')    return month >= 4 && month <= 10;
      if (s === 'NHL')    return month >= 10 || month <= 6;
      if (s === 'SOCCER') return true;
      if (s === 'TENNIS') return true;
      return false;
    };
    const crossSportKeys = ['NBA', 'WNBA', 'NFL', 'MLB', 'NHL', 'SOCCER', 'TENNIS'].filter(inSeason);
    const sgpSport = isAllSports ? 'NBA' : sport;
    const [parlayOdds, crossOdds, parlayNba, parlayInjuries, parlaySharp] = await Promise.all([
      fetchLiveOdds(sgpSport, game || undefined),
      isAllSports
        ? Promise.all(crossSportKeys.map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n'))
        : Promise.all(crossSportKeys.filter(s => s !== sport).map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n')),
      (isAllSports || sport === 'NBA' || sport === 'WNBA') ? fetchNBAScheduleToday() : fetchESPNScoreboard(sport),
      fetchInjuries(sgpSport, game || undefined),
      fetchSharpSignals(sgpSport),
    ]);

    const sgpHeuristics = getBettingHeuristics(sgpSport);
    const sgpBetCtx = getSportBetContext(sgpSport);

    const gameContext = game
      ? `SPECIFIC GAME TO AUDIT: "${game}". SGP and correlation parlay must be from this exact game. Multi-game and EV parlays can include this game as the anchor with 1-2 other real games tonight from ANY sport.`
      : isAllSports
        ? `Scan ALL sports tonight (NBA, WNBA, NFL, SOCCER/World Cup, TENNIS). Pick the single best opportunity from any sport.`
        : `Generate the best betting opportunities across TODAY's ${sport} slate.`;

    const parlayOddsBlock = `
LIVE ODDS — PRIMARY SPORT (${sgpSport}):
${parlayOdds}
${parlayNba}
${parlayInjuries ? `\n${parlayInjuries}` : ''}
${parlaySharp ? `\n${parlaySharp}` : ''}

LIVE ODDS — CROSS-SPORT (for multi-parlay & EV stack legs, mix freely):
${crossOdds}
`;

    const prompt = `
You are a sharp professional sports bettor. Today is ${today}.

${sgpHeuristics}
${parlayOddsBlock}
${gameContext}

Apply all heuristics above to every leg. Use the INJURY REPORT — if a key player is OUT or DOUBTFUL, apply Next Man Up logic (backup's props are often highest EV). Use the SHARP SIGNALS — follow the Pinnacle-vs-DK gap where sharp money is detected. Run the SHARP CHECK. Flag [HIGH-RISK] legs. Apply the JUICE FILTER (reject if cumulative vig >15%). For SGP: run CORRELATION STRESS TEST on every leg pair.

📊 PARLAY DISCIPLINE (data-backed — see heuristic rule 11, OBEY): the user's settled results prove 2–3-leg tickets win (+83% ROI) and 4+ leg stacks bleed (7+ = total loss). Build 2–3 legs, HARD CAP 4, NEVER 5+. Every leg priced decimal 1.50–5.0 (American −200 to +400) — drop heavy chalk (<1.50) and lottery (5.0+) legs.

CRITICAL RULES FOR EACH PARLAY TYPE:
- best_pick: Best single bet from ANY sport available tonight (leg priced 1.50–5.0)
- sgp (Same-Game Parlay): 2–3 legs, ALL from ONE single game in ${sgpSport}. Apply ${sgpBetCtx}
- multi_parlay: 2–3 best cross-sport legs from DIFFERENT games (mix NBA, WNBA, MLB, NFL, SOCCER). Quality over quantity — 2 strong legs beat 4 weak ones
- ev_parlay: 2–3 legs, ONLY legs with >4% EV individually, each priced 1.50–5.0. Any sport
- correlation_parlay: 2–3 legs that POSITIVELY correlate — team score high + player Over props, or same-game correlated outcomes. Use ${sgpSport} for strongest correlation

⛔ DO NOT output ev, win_prob, or any invented percentage. Math engine computes those server-side.
⛔ All picks must be from the LIVE ODDS blocks above. Never invent lines.
⛔ "why" fields must cite sourced data. Use [SOURCE] tags.
⛔ MUTUAL EXCLUSIVITY CHECK: every leg pair in a parlay must be able to win TOGETHER in a realistic outcome. NEVER combine a team's spread with the OPPOSING team's moneyline (e.g., Spurs +2 + Knicks ML only both cash if Knicks win by exactly 1 — that is a middle, not a parlay). If two legs conflict, drop the weaker one.

Output ONLY a raw JSON object with this exact structure:
{
  "best_pick": {
    "selection": "Exact pick from LIVE ODDS block",
    "odds": "-115",
    "why": "[SOURCE] 1 sentence, sourced data only, caveman short",
    "units": "2 UNITS",
    "game": "Team A vs Team B — TIME ET"
  },
  "sgp": {
    "game": "${game || `Best ${sgpSport} game on slate`} — TIME ET",
    "legs": [
      { "pick": "Player X Over 24.5 Points from LIVE ODDS", "odds": "-115", "why": "[SOURCE] caveman why" },
      { "pick": "Player X Over 5.5 Assists from LIVE ODDS", "odds": "-110", "why": "[SOURCE] caveman why" },
      { "pick": "Team A -3.5 from LIVE ODDS", "odds": "-110", "why": "[SOURCE] caveman why" }
    ],
    "combined_odds": "+285",
    "why": "1 sentence: why these legs correlate in same game"
  },
  "multi_parlay": {
    "legs": [
      { "game": "NBA: Team A vs Team B — TIME ET", "pick": "Team A ML from LIVE ODDS", "odds": "-130", "why": "[SOURCE] caveman why" },
      { "game": "MLB: Team C vs Team D — TIME ET", "pick": "Team C F5 -1.5 from LIVE ODDS", "odds": "+110", "why": "[SOURCE] caveman why" },
      { "game": "NFL/SOCCER: Game — TIME ET", "pick": "Pick from LIVE ODDS", "odds": "-110", "why": "[SOURCE] caveman why" }
    ],
    "combined_odds": "+480",
    "why": "1 sentence: why these cross-sport picks stack well tonight"
  },
  "ev_parlay": {
    "legs": [
      { "game": "SPORT: Game 1 — TIME ET", "pick": "Pick with market edge from LIVE ODDS", "odds": "+140", "why": "[SHARP SIGNALS] caveman why" },
      { "game": "SPORT: Game 2 — TIME ET", "pick": "Pick from LIVE ODDS", "odds": "-105", "why": "[SOURCE] caveman why" },
      { "game": "SPORT: Game 3 — TIME ET", "pick": "Pick from LIVE ODDS", "odds": "-108", "why": "[SOURCE] caveman why" }
    ],
    "combined_odds": "+380",
    "why": "Best line value picks across ALL sports tonight, from LIVE ODDS only"
  },
  "correlation_parlay": {
    "legs": [
      { "game": "${game || `${sgpSport} target game`} — TIME ET", "pick": "Team scores high / wins from LIVE ODDS", "odds": "-120", "why": "[SOURCE] fast pace" },
      { "game": "Same game", "pick": "Star player Over points from LIVE ODDS", "odds": "-115", "why": "[SOURCE] caveman why" },
      { "game": "Same or linked game", "pick": "Correlated total/prop from LIVE ODDS", "odds": "-110", "why": "[SOURCE] legs move together" }
    ],
    "combined_odds": "+320",
    "why": "1 sentence: how these legs correlate positively"
  }
}

Rules:
- SGP legs must ALL be from 1 game in ${sgpSport}${game ? `\n- Game audit mode: anchor all picks to "${game}"` : ''}
- multi_parlay and ev_parlay: CROSS-SPORT is allowed and encouraged — pick the sharpest legs from NBA, MLB, NFL, SOCCER
- Real players, real teams/athletes, real lines from the live odds above
- "why" fields: caveman short — max 12 words, cite specific numbers/stats
- combined_odds: realistic parlay math
- No filler. No markdown. Raw JSON only.
`.trim();

    const parlayCacheKey = `parlays:${sport}:${game || 'slate'}`;
    const parlayCached = getCached(parlayCacheKey);
    if (parlayCached) { res.json(parlayCached); return; }

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Omit<ParlaysPayload, 'sport' | 'hash' | 'timestamp'>;
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }

    // Server-side math for best_pick
    const bp = parsed?.best_pick;
    const bpOddsNum = bp ? parseInt(String(bp.odds ?? '').replace(/[^-\d]/g, ''), 10) : NaN;
    // Parlay combined odds — SERVER math, never AI arithmetic. LLMs get this
    // wrong (saw +105 quoted on legs that multiply to ~+356). Independent-legs
    // product; books price correlated SGPs below this, so it's the ceiling.
    const decToAmerican = (dec: number): string => {
      const b = dec - 1;
      const am = b >= 1 ? Math.round(b * 100) : -Math.round(100 / b);
      return am > 0 ? `+${am}` : `${am}`;
    };
    const withMathCombined = <T extends { legs?: Array<{ odds?: string }>; combined_odds?: string }>(block: T | undefined): T | undefined => {
      if (!block || !Array.isArray(block.legs) || block.legs.length === 0) return block;
      const nums = block.legs.map(l => parseInt(String(l.odds ?? '').replace(/[^-\d]/g, ''), 10));
      if (!nums.every(n => Number.isFinite(n) && Math.abs(n) >= 100)) return block; // can't verify → leave AI value
      const dec = nums.reduce((p, n) => p * toDecimal(n), 1);
      return { ...block, combined_odds: decToAmerican(dec) };
    };

    const bpImplied = Math.round(impliedProb(bpOddsNum) * 1000) / 10;
    const bpDevigged = Math.round((bpImplied / 1.045) * 10) / 10;
    const enrichedBestPick = bp && !isNaN(bpOddsNum) ? {
      ...bp,
      implied_prob: bpImplied,
      bet_structure: getBetStructure(bpOddsNum),
      // Quality rule: winning > value — flag picks the market says lose ≥55% of the time
      upset_alert: bpDevigged < 45
        ? `⚠️ MARKET DISAGREES — this pick wins ~${bpDevigged}% of the time; the other side is the real favorite. Longshot stake or skip.`
        : null,
    } : bp;

    const payload: ParlaysPayload = {
      ...parsed,
      best_pick: enrichedBestPick as ParlaysPayload['best_pick'],
      sgp: withMathCombined(parsed.sgp) as ParlaysPayload['sgp'],
      multi_parlay: withMathCombined(parsed.multi_parlay) as ParlaysPayload['multi_parlay'],
      ev_parlay: withMathCombined(parsed.ev_parlay) as ParlaysPayload['ev_parlay'],
      correlation_parlay: withMathCombined(parsed.correlation_parlay) as ParlaysPayload['correlation_parlay'],
      sport,
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
      timestamp: new Date().toLocaleTimeString()
    };

    // 60 min — same slate, same parlay; rebuilds within the hour are free
    setCache(parlayCacheKey, payload, 60 * 60 * 1000);

    // Auto-log best_pick — same self-building record as the prophet
    try {
      const bpSel = String(bp?.selection ?? '');
      const bpGame = String(bp?.game ?? '');
      if (bpSel && Number.isFinite(bpOddsNum) && Math.abs(bpOddsNum) >= 100 &&
          !(await hasPendingDuplicate(bpSel, bpGame))) {
        await addPick({
          sport,
          game: bpGame,
          selection: bpSel,
          odds: bpOddsNum,
          stake_units: /2\s*UNIT/i.test(String(bp?.units ?? '')) ? 2 : 1,
          source: 'parlays',
          ...parseSelectionIdentity(bpSel, bpGame),  // structured identity for CLV capture
        });
      }
    } catch (e: unknown) {
      console.error('Parlays auto-log failed:', e instanceof Error ? e.message : String(e));
    }

    res.json(payload);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("PARLAYS_FAILURE:", msg);
    res.status(500).json({ error: "PARLAYS_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// QUANTUM MISSION — free-form sports betting research agent
// ─────────────────────────────────────────────────────────────────────────────
app.post('/api/quantum-mission', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const { goal, sport: qSport } = req.body;
    if (!goal) return res.status(400).json({ error: "GOAL_REQUIRED" });

    const quantumCacheKey = `quantum:${(qSport || 'all').toLowerCase()}:${goal.toLowerCase().slice(0, 60).replace(/\s+/g, '_')}`;
    const quantumCached = getCached(quantumCacheKey);
    if (quantumCached) { res.json(quantumCached); return; }

    const today = todayStr();
    const quantSport = (qSport || 'NBA').toUpperCase();
    const quantumHeuristics = getShortHeuristics(quantSport);
    const prompt = `
${SHARP_IDENTITY()}

You are a sports betting research agent. Today is ${today}.
Mission goal: "${goal}"

${quantumHeuristics}

Apply the above heuristics during your research. Look for CLV, derivative markets, injury impact, and contrarian signals. Run the SHARP CHECK before your final verdict.

Execute this mission step by step. Simulate 3-4 tool calls as part of your research, then give a final verdict.

Output ONLY this raw JSON:
{
  "goal": "${goal.replace(/"/g, "'")}",
  "logs": [
    {
      "tool": "MARKET_SCAN",
      "output": "One paragraph: what markets/games you found relevant to this goal. Be specific with real teams/players/lines.",
      "success": true,
      "timestamp": "${new Date().toISOString()}"
    },
    {
      "tool": "LINE_ANALYSIS",
      "output": "One paragraph: line value analysis. Where is the market mispriced? Cite specific numbers.",
      "success": true,
      "timestamp": "${new Date(Date.now() + 800).toISOString()}"
    },
    {
      "tool": "EV_CALC",
      "output": "One paragraph: EV calculation on the best find. True prob vs implied prob. Kelly fraction.",
      "success": true,
      "timestamp": "${new Date(Date.now() + 1600).toISOString()}"
    },
    {
      "tool": "SHARP_CHECK",
      "output": "One paragraph: sharp money check. Any steam? RLM? Public fading opportunity?",
      "success": true,
      "timestamp": "${new Date(Date.now() + 2400).toISOString()}"
    }
  ],
  "final_verdict": "2-3 sentence final verdict. State the exact bet, the edge, and confidence. Be direct.",
  "hash": "Σ_${Math.random().toString(36).substring(7).toUpperCase()}"
}

Be specific. Real data. No filler.
`.trim();

    const raw = await ask(prompt);
    const parsed = parseJSON(raw);
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }
    setCache(quantumCacheKey, parsed);
    res.json(parsed);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("QUANTUM_FAILURE:", msg);
    res.status(500).json({ error: "QUANTUM_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// FULL BREAKDOWN — one call returns: pick of day, parlay of day, SGP, spread/ML/total, top props
// Two AI calls fired in parallel: game-specific + daily cross-sport edge
// ─────────────────────────────────────────────────────────────────────────────
app.post('/api/full-breakdown', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });
  try {
    const { matchup, sport } = req.body;
    if (!matchup) return res.status(400).json({ error: "MATCHUP_REQUIRED" });
    const today = todayStr();
    const league = (sport || 'NBA').toUpperCase();
    const month = new Date().getMonth() + 1;
    const inSeason = (s: string) => {
      if (s === 'NBA')    return month >= 10 || month <= 6;
      if (s === 'WNBA')   return month >= 5 && month <= 9;
      if (s === 'NFL')    return month >= 9 || month <= 2;
      if (s === 'MLB')    return month >= 4 && month <= 10;
      if (s === 'NHL')    return month >= 10 || month <= 6;
      if (s === 'SOCCER') return true;
      if (s === 'TENNIS') return true;
      return false;
    };
    const crossSports = ['NBA', 'WNBA', 'NFL', 'MLB', 'NHL', 'SOCCER', 'TENNIS'].filter(inSeason);

    // Fetch all data in parallel — real stats, news, odds, injuries, sharp signals, historical
    const [oddsCtx, injuryCtx, playerStatsCtx, advancedCtx, teamStatsCtx, nicheCtx, newsCtx, pitcherCtx, weatherCtx, sharpCtx, crossOdds, historicalCtx] = await Promise.all([
      fetchLiveOdds(league, matchup),
      fetchInjuries(league, matchup),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBAPlayerStats(matchup)
        : Promise.resolve(''),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBAAdvancedStats(matchup)
        : Promise.resolve(''),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBATeamStats(matchup)
        : Promise.resolve(''),
      // Sport-specific niche stats
      league === 'SOCCER'  ? fetchSoccerContext(matchup)
        : league === 'TENNIS' ? fetchTennisContext(matchup)
        : league === 'F1'     ? Promise.resolve(getF1CircuitContext(matchup))
        : Promise.resolve(''),
      fetchESPNNews(league, matchup),
      league === 'MLB' ? fetchMLBPitcherStats(matchup) : Promise.resolve(''),
      fetchWeather(matchup, league),
      fetchSharpSignals(league),
      Promise.all(crossSports.filter(s => s !== league).map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n')),
      // Google Search: real historical stats + trends from credible sources (covers, b-ref, espn)
      fetchHistoricalContext(league, matchup),
    ]);

    const heuristics = getBettingHeuristics(league);

    // ── Harvard Math Layer ─────────────────────────────────────────────────────
    let harvardCtx = '';
    try {
      const fbOddsGame = parseOddsForTeams(oddsCtx);
      const hImp = fbOddsGame?.homeOdds != null ? impliedProb(fbOddsGame.homeOdds) : 0;
      const aImp = fbOddsGame?.awayOdds != null ? impliedProb(fbOddsGame.awayOdds) : 0;
      const dv = hImp && aImp ? devig(hImp, aImp) : null;
      const hRes = await fetch('http://127.0.0.1:8002/harvard/master', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prior_prob: dv ? dv.p1 : 0.5,
          market_spread: fbOddsGame?.spread ?? 0,
          decimal_odds: fbOddsGame?.homeOdds != null ? toDecimal(fbOddsGame.homeOdds) : 1.909,
          bankroll: 100, injury_impact: 0, rest_advantage: 0, distraction_index: 0,
          line_move_toward_team: false, wins_in_sample: 10, losses_in_sample: 10,
          observed_wins: 10, observed_losses: 10,
        }),
        signal: AbortSignal.timeout(4000),
      });
      if (hRes.ok) {
        const h = await hRes.json() as {
          stacked_final_prob: number; edge_pct: number; verdict: string;
          kelly_sizing_usd: number; edge_significant: boolean;
          course_outputs: { stat110x_prob: number; ph125_prob: number; cs109x_prob: number };
          feature_importance: Array<{ feature: string; direction: string }>;
        };
        harvardCtx = [
          `\n━━ HARVARD PROBABILITY ENGINE ━━`,
          `• STAT110x (Bayesian):    ${(h.course_outputs.stat110x_prob * 100).toFixed(1)}%`,
          `• PH125.4x (Frequentist): ${(h.course_outputs.ph125_prob * 100).toFixed(1)}%`,
          `• CS109xa (Logistic ML):  ${(h.course_outputs.cs109x_prob * 100).toFixed(1)}%`,
          `• Stacked Final: ${(h.stacked_final_prob * 100).toFixed(1)}% | Edge: ${h.edge_pct > 0 ? '+' : ''}${h.edge_pct}%`,
          `• Edge significant (p<0.05): ${h.edge_significant ? 'YES' : 'NO'} | Kelly $${h.kelly_sizing_usd} per $100`,
          `• Top driver: ${h.feature_importance?.[0]?.feature ?? 'sharp_prob'} (${h.feature_importance?.[0]?.direction ?? 'boosting'})`,
          `• Verdict: ${h.verdict}`,
        ].join('\n');
      }
    } catch (e: unknown) {
      // Non-blocking, but NEVER silent — a dead math layer hid for days this way
      console.error('Harvard engine unavailable:', e instanceof Error ? e.message : String(e));
    }

    const gamePrompt = `
${SHARP_IDENTITY()}

You are a sharp sports betting analyst. Today is ${today}.
Game: ${matchup} (${league})

${heuristics}

LIVE ODDS FOR THIS GAME (USE THESE EXACT LINES — do not invent odds):
${oddsCtx || "No live odds found — note this clearly in your output, do not fabricate lines."}

INJURY REPORT (ONLY reference players listed here — do NOT invent injuries):
${injuryCtx || "No injury data available from ESPN right now. Do NOT fabricate any injuries."}

${harvardCtx ? `${harvardCtx}\n` : ''}${advancedCtx ? `${advancedCtx}\n` : ''}
${nicheCtx ? `SPORT-SPECIFIC NICHE DATA (cite these exact numbers, do NOT invent):\n${nicheCtx}\n` : ''}
${playerStatsCtx ? `REAL PLAYER STATS — BallDontLie API (cite these exact numbers, do NOT invent):\n${playerStatsCtx}\n` : ''}
${teamStatsCtx ? `REAL TEAM STATS — ESPN API (cite these exact numbers, do NOT invent):\n${teamStatsCtx}\n` : ''}
${pitcherCtx ? `REAL PITCHER STATS — MLB Official API (cite these exact numbers, do NOT invent):\n${pitcherCtx}\n` : ''}
${weatherCtx ? `WEATHER DATA — wttr.in real-time:\n${weatherCtx}\n` : ''}
${newsCtx ? `LATEST NEWS — ESPN live:\n${newsCtx}\n` : ''}
${historicalCtx ? `${historicalCtx}\n` : ''}
📐 MATH ENGINE — use these formulas when computing EV and Kelly in your rationale:
- Implied prob already devigged: see "→ Implied(devigged)" lines in LIVE ODDS above.
- EV = (your_win_prob × (decimal_odds − 1)) − (1 − your_win_prob)
  decimal_odds: americanOdds ≥ 0 → odds/100+1 | americanOdds < 0 → 100/|odds|+1
- Half-Kelly units = max(0, (b×p − (1−p)) / b / 2)  where b = decimal_odds − 1, p = win_prob
- NBA model total/margin: see "Model Expected Total" and "Model Win Prob" above.
- Edge = your win_prob − devigged market probability. Positive edge = bet has value.
- Cite: "Model: 54.3% | Market(devigged): 51.8% | Edge: +2.5% | EV: +3.1% | Half-Kelly: 0.6u"
⚠️ If model stats block is present, your win_prob MUST align with the model within ±15%. Do not wildly deviate without explaining why.
SHARP SIGNALS (Pinnacle vs DK line gap — directional signal only):
${sharpCtx || "No significant line gap detected."}

⚠️ HONESTY RULES — NON-NEGOTIABLE:
- win_prob: your calibrated estimate based on available data. Do NOT output >0.82 — real sharp bettors rarely see edge that clean.
- EV: label as "est." — we have no true probability model. Only output EV if you can ground it in the real stats/odds above.
- If a stat block is missing (no player stats, no pitcher data), say so in game_summary. Do NOT invent replacement numbers.
- rationale must cite at least one real number from the data blocks above or from the live odds. No narrative-only rationale accepted.

⚠️ ANTI-HALLUCINATION RULES — MUST FOLLOW:
1. PLAYER STATS: If REAL PLAYER STATS block is present, cite exact numbers (PPG, L5 form). Never round or invent.
   ADVANCED STATS: If NBA ADVANCED STATS block is present, cite OffRtg/DefRtg/NetRtg/Pace. Use "Model Expected Total" to anchor total pick. Use "Model Win Prob" to anchor spread/ML win_prob.
2. PITCHER STATS: If REAL PITCHER STATS block is present, cite pitcher's ERA, K/9, WHIP directly. Never say "2.80 ERA" if the block shows "3.84 ERA".
3. WEATHER: If WEATHER block shows wind ≥15mph, it MUST affect your total pick and any passing props. Do not ignore it.
4. INJURIES: Only cite players from the INJURY REPORT. Empty report = say "no injury data" — never invent.
5. ODDS: Use exact lines from LIVE ODDS. If block is empty, label estimates as "est."
6. PROPS: Set prop lines relative to the REAL averages provided. Player averaging 24.6PPG → prop near 24.5, not invented 28.5.
7. NEWS: Lineup changes, questionable tags in news → reprice that market immediately before picking.
8. NICHE DATA: If SPORT-SPECIFIC NICHE DATA block is present:
   - NHL: cite exact SV%, GAA, PPG from the block. If SV% <.900 = vulnerable goalie — flag it.
   - SOCCER: cite exact W/D/L, GF, GA, GD from standings. Use PPG to assess form.
   - F1: cite circuit type and qualifying weight. If qualifying weight ≥80%, the pole sitter is primary pick.
   - TENNIS: cite the surface annotation from LIVE ODDS header (Clay/Grass/Hard). Surface MUST appear in rationale.
9. SURFACE (TENNIS): The LIVE ODDS block starts with a surface annotation (🏟️ line). The surface type is NON-NEGOTIABLE context. Do NOT pick a flat-hitter on clay or ignore a big server's grass advantage.

🔍 ALT LINE HUNTING — VERY IMPORTANT:
The LIVE ODDS block may contain alternate_spreads and alternate_totals alongside standard lines.
For EACH market (spread, total): scan ALL listed lines (standard + alternate) and pick the one with the best true value.
- If the standard spread is Lakers +5.5 but you believe the true margin is +9, then Lakers +8.5 alt spread at real odds is far better value — pick the alt.
- If an alt line exists and gives meaningfully more cushion OR better odds edge, use it and set "is_alt": true.
- If the standard line is already the best value, leave "is_alt" as false and omit "alt_note".
- Only use alt lines that appear in the LIVE ODDS block — never fabricate alternate lines.

Analyze this specific game. Apply heuristics above to every pick.
For the SGP: pick 3 correlated legs from THIS game only. Legs must positively correlate.

⛔ DO NOT output win_prob, ev, niche_stat, confidence_score, or kelly_stake — math engine handles those.
⛔ rationale MUST cite source using [SOURCE] tags from the data blocks.

Output ONLY raw JSON — no markdown:
{
  "game": "${matchup}",
  "game_summary": "2-3 sentences: key injuries ([INJURY REPORT]), sharp signals ([SHARP SIGNALS]), biggest edge",
  "spread_pick": { "pick": "Team -X.X or alt line from LIVE ODDS", "odds": "-110", "rationale": "[SOURCE] 2 sharp sentences citing real data", "is_alt": false },
  "ml_pick": { "pick": "Team ML from LIVE ODDS", "odds": "-180", "rationale": "[SOURCE] 2 sharp sentences", "is_alt": false },
  "total_pick": { "pick": "Over/Under X.X from LIVE ODDS", "odds": "-108", "rationale": "[SOURCE] 2 sharp sentences", "is_alt": false },
  "top_props": [
    { "player": "Real player in LIVE ODDS block", "market": "Points", "pick": "Over 26.5", "odds": "-115", "rationale": "[SOURCE] 1-2 sentences from data blocks only" },
    { "player": "Real player in LIVE ODDS block", "market": "Rebounds", "pick": "Over 8.5", "odds": "-110", "rationale": "[SOURCE] 1-2 sentences" },
    { "player": "Real player in LIVE ODDS block", "market": "Assists", "pick": "Over 6.5", "odds": "-115", "rationale": "[SOURCE] 1-2 sentences" },
    { "player": "Real player in LIVE ODDS block", "market": "Points", "pick": "Over 21.5", "odds": "-110", "rationale": "[SOURCE] 1-2 sentences" },
    { "player": "Real player in LIVE ODDS block", "market": "Threes", "pick": "Over 2.5", "odds": "-115", "rationale": "[SOURCE] 1-2 sentences" }
  ],
  "sgp": {
    "legs": [
      { "pick": "Team covers or wins from LIVE ODDS", "odds": "-130", "why": "caveman reason max 10 words" },
      { "pick": "Real player Over X stat from LIVE ODDS", "odds": "-115", "why": "caveman reason" },
      { "pick": "Correlated total or prop from LIVE ODDS", "odds": "-110", "why": "caveman reason" }
    ],
    "combined_odds": "+280",
    "why": "1 sentence: why these legs from THIS game correlate"
  }
}`.trim();

    const dailyPrompt = `
You are a sharp professional sports bettor. Today is ${today}.

CROSS-SPORT ODDS TONIGHT (ONLY use games/lines listed below — do NOT invent games):
${crossOdds || "No cross-sport odds available right now."}

⚠️ STRICT RULE: Only pick from REAL games in the ODDS block above. If odds block is empty, return empty legs arrays. Do NOT fabricate game results, player props, or lines.

Task 1 — PICK OF THE DAY: Find the single best bet from the ODDS BLOCK above. Must be from a real listed game.

Task 2 — PARLAY OF THE DAY: Build the best 3-leg cross-sport parlay. Each leg must be from a DIFFERENT game in the odds block above.

⛔ DO NOT output ev, win_prob, or any invented percentage.
Each pick must be from the ODDS BLOCK above. If no odds available, return null for both fields.

Output ONLY raw JSON — no markdown:
{
  "pick_of_day": {
    "selection": "Exact pick from ODDS BLOCK e.g. LeBron James Over 25.5 Points",
    "odds": "-115",
    "why": "[SOURCE] 1 sentence, specific sourced data only, caveman short",
    "units": "2U",
    "game": "Team A vs Team B",
    "sport": "NBA"
  },
  "parlay_of_day": {
    "legs": [
      { "pick": "Team A ML from ODDS BLOCK", "odds": "-130", "why": "[SOURCE] caveman why", "game": "NBA: Game 1" },
      { "pick": "Team B -1.5 F5 from ODDS BLOCK", "odds": "+110", "why": "[SOURCE] caveman why", "game": "MLB: Game 2" },
      { "pick": "Player Over X from ODDS BLOCK", "odds": "-115", "why": "[SOURCE] caveman why", "game": "SOCCER: Game 3" }
    ],
    "combined_odds": "+480",
    "why": "1 sentence: why these cross-sport picks stack tonight"
  }
}`.trim();

    const cacheKey = `fullbreakdown:${league}:${matchup.toLowerCase().replace(/\s+/g, '_')}`;
    const cached = getCached(cacheKey);
    if (cached) return res.json(cached);

    const [gameRaw, dailyRaw] = await Promise.all([
      ask(gamePrompt),
      ask(dailyPrompt),
    ]);

    let game: Record<string, unknown>;
    try {
      const g = parseJSON(gameRaw);
      if (!g || typeof g !== 'object' || Array.isArray(g)) throw new Error("not an object");
      game = g as Record<string, unknown>;
    } catch {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid game data. Try again." });
    }

    let daily: Record<string, unknown> = {};
    try {
      const d = parseJSON(dailyRaw);
      if (d && typeof d === 'object' && !Array.isArray(d)) daily = d as Record<string, unknown>;
    } catch { /* daily picks are optional — continue without them */ }

    // Server-side math — compute implied_prob + bet_structure for every pick
    const enrichPick = (pick: Record<string, unknown> | null | undefined) => {
      if (!pick || typeof pick !== 'object') return pick;
      const oddsStr = String(pick.odds ?? '');
      const oddsNum = parseInt(oddsStr.replace(/[^-\d]/g, ''), 10);
      if (isNaN(oddsNum) || oddsNum === 0) return pick;
      return {
        ...pick,
        implied_prob: Math.round(impliedProb(oddsNum) * 1000) / 10,
        bet_structure: getBetStructure(oddsNum),
      };
    };

    const enrichedGame = { ...game };
    if (enrichedGame.spread_pick) enrichedGame.spread_pick = enrichPick(enrichedGame.spread_pick as Record<string, unknown>);
    if (enrichedGame.ml_pick) enrichedGame.ml_pick = enrichPick(enrichedGame.ml_pick as Record<string, unknown>);
    if (enrichedGame.total_pick) enrichedGame.total_pick = enrichPick(enrichedGame.total_pick as Record<string, unknown>);
    if (Array.isArray(enrichedGame.top_props)) {
      enrichedGame.top_props = (enrichedGame.top_props as Array<Record<string, unknown>>).map(enrichPick);
    }

    const payload = {
      ...enrichedGame,
      pick_of_day: enrichPick(daily.pick_of_day as Record<string, unknown>),
      parlay_of_day: daily.parlay_of_day,
      hash: "FB_" + Math.random().toString(36).substring(7).toUpperCase(),
    };
    setCache(cacheKey, payload, 20 * 60 * 1000);
    res.json(payload);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("FULL_BREAKDOWN_FAILURE:", msg);
    res.status(500).json({ error: "FULL_BREAKDOWN_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SHARP MONEY — AI steam moves, RLM, best EV plays for a sport/game
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/sharp-money', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const game = (req.query.game as string || '').trim();
    const today = todayStr();
    const gameCtx = game ? `Focus on: "${game}". ` : `Cover tonight's top ${sport} games. `;
    const betCtx = getSportBetContext(sport);

    const sharpCacheKey = `sharp:${sport}:${game || 'slate'}`;
    const sharpCached = getCached(sharpCacheKey);
    if (sharpCached) { res.json(sharpCached); return; }

    // Use short heuristics for sharp-money — saves ~1600 tokens per call (Fix #3)
    const sharpHeuristics = getShortHeuristics(sport);
    const [sharpOdds, sharpNba, sharpInjuries, sharpSignals] = await Promise.all([
      fetchLiveOdds(sport, game || undefined),
      sport === 'NBA' || sport === 'WNBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(sport),
      fetchInjuries(sport, game || undefined),
      fetchSharpSignals(sport),
    ]);
    const sharpOddsBlock = [
      `\nLIVE ODDS (Pinnacle/DraftKings — use for CLV and line movement):\n${sharpOdds}`,
      sharpNba || '',
      sharpInjuries ? `\n${sharpInjuries}` : '',
      sharpSignals ? `\n${sharpSignals}` : '',
    ].filter(Boolean).join('\n');

    const prompt = `
${SHARP_IDENTITY()}

You are a sharp money tracking analyst. Today is ${today}. Sport: ${sport}.
${gameCtx}${betCtx}
${sharpOddsBlock}
${sharpHeuristics}

Using the above heuristics, identify real sharp action. Specifically look for:
- CLV opportunities (lines better than opening)
- RLM (line moves against public — CONTRARIAN_SIGNAL)
- Steam moves (sharp syndicate action causing fast line movement)
- Derivative market value (softer lines in 1H/1Q/team totals/F5)
- Injury context that moves EV but market hasn't fully adjusted

⛔ DO NOT output ev percentages — math engine computes those. Do NOT invent line moves; only cite lines in LIVE ODDS.
Output ONLY this raw JSON:
{
  "sport": "${sport}",
  "steam_moves": [
    {
      "game": "Team A vs Team B — TIME ET",
      "bet": "Exact bet from LIVE ODDS e.g. Celtics -4.5",
      "opening_line": "e.g. -3",
      "current_line": "e.g. -4.5",
      "move": "e.g. 1.5 points",
      "direction": "STEAM",
      "why": "[LIVE ODDS] Sharp hammered this side. Line moved fast with low public %"
    }
  ],
  "rlm": [
    {
      "game": "Team C vs Team D — TIME ET",
      "bet": "Exact bet from LIVE ODDS",
      "opening_line": "opening",
      "current_line": "current",
      "move": "moved description",
      "direction": "RLM",
      "why": "[LIVE ODDS] Public majority on Team C but line moved to Team D — sharps on opposite side"
    }
  ],
  "best_ev_plays": [
    {
      "game": "Game — TIME ET",
      "bet": "Best value pick from LIVE ODDS",
      "odds": "-110",
      "why": "[SOURCE] Specific sourced reason why this line has value"
    },
    {
      "game": "Game — TIME ET",
      "bet": "Second best from LIVE ODDS",
      "odds": "+130",
      "why": "[SOURCE] Specific sourced reason"
    },
    {
      "game": "Game — TIME ET",
      "bet": "Third best from LIVE ODDS",
      "odds": "-105",
      "why": "[SOURCE] Specific sourced reason"
    }
  ],
  "hash": "Σ_${Math.random().toString(36).substring(7).toUpperCase()}",
  "timestamp": "${new Date().toLocaleTimeString()}"
}

Rules:
- ${sport} ONLY. Real games tonight.
- steam_moves: 2-3 entries. Lines that moved sharply.
- rlm: 1-2 entries. Public on one side, line moves opposite.
- best_ev_plays: exactly 3. Best +EV bets on the slate.
- No filler. Raw JSON only.
`.trim();

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }
    const sharpResult = { ...parsed, sport, timestamp: new Date().toLocaleTimeString() };
    setCache(sharpCacheKey, sharpResult);
    res.json(sharpResult);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("SHARP_MONEY_FAILURE:", msg);
    res.status(500).json({ error: "SHARP_MONEY_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SHARP SCANNER — alias for /api/sharp-money (matches frontend route)
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/sharp-scanner', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const cacheKey = `sharp:${sport}:slate`;
    const cached = getCached(cacheKey);
    if (cached) { res.json(cached); return; }

    const betCtx = getSportBetContext(sport);
    const sharpHeuristics = getShortHeuristics(sport);
    const today = todayStr();
    const [odds, schedule, injuries, signals] = await Promise.all([
      fetchLiveOdds(sport),
      sport === 'NBA' || sport === 'WNBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(sport),
      fetchInjuries(sport),
      fetchSharpSignals(sport),
    ]);
    const ctx = [
      `\nLIVE ODDS:\n${odds}`,
      schedule || '',
      injuries ? `\n${injuries}` : '',
      signals ? `\n${signals}` : '',
    ].filter(Boolean).join('\n');

    const seed = Math.random().toString(36).substring(7).toUpperCase();
    const ts = new Date().toLocaleTimeString();
    const prompt = `
${SHARP_IDENTITY()}
You are a sharp money tracking analyst. Today is ${today}. Sport: ${sport}.
${betCtx}
${ctx}
${sharpHeuristics}

Output ONLY raw JSON:
{
  "sport": "${sport}",
  "steam_moves": [{"game":"...","bet":"...","opening_line":"...","current_line":"...","move":"...","direction":"STEAM","why":"...","ev":"..."}],
  "rlm": [{"game":"...","bet":"...","opening_line":"...","current_line":"...","move":"...","direction":"RLM","why":"...","ev":"..."}],
  "best_ev_plays": [{"game":"...","bet":"...","odds":"...","ev":"...","why":"..."}],
  "hash": "Σ_${seed}",
  "timestamp": "${ts}"
}

Rules: ${sport} ONLY. Real games tonight. steam_moves 2-3. rlm 1-2. best_ev_plays exactly 3. Raw JSON only.
CRITICAL — "ev" fields: NEVER compute or invent a number. Only quote an implied-probability gap that appears verbatim in the data blocks above (e.g. "Pinnacle 54.2% vs DK 49.8%"). If no gap is shown in the data, write "N/A".
`.trim();

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED" });
    }
    const result = { ...parsed, sport, timestamp: ts };
    setCache(cacheKey, result);
    res.json(result);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    res.status(500).json({ error: "SHARP_SCANNER_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// LINE GAPS — pure math, no AI. Pinnacle implied prob vs DK/FD.
// When Pinnacle prices a side higher than soft books, sharp money is on that side.
// Best play: bet the sharp side at the soft book (better price, sharp direction).
// ─────────────────────────────────────────────────────────────────────────────
interface LineGap {
  game: string;
  market: string;
  outcome: string;
  pinnacle_odds: number;
  book: string;
  book_odds: number;
  pinnacle_implied: number;  // fair (devigged) win prob %, Pinnacle
  book_implied: number;      // fair (devigged) win prob %, soft book
  gap_pct: number;           // pinnacle_implied − book_implied in fair-prob pts (positive = sharp on this side)
  best_line: number;         // odds to bet (at soft book if gap > 0)
  best_book: string;
  signal: string;
  commence_time: string;
}

app.get('/api/line-gaps', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 10, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });
  if (!ODDS_API_KEY) return res.status(503).json({ error: "ODDS_API_NOT_CONFIGURED" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const cacheKey = `linegaps:${sport}`;
    const cached = getCached(cacheKey);
    if (cached) { res.json(cached); return; }

    const sportKeys = SPORT_KEYS[sport] || SPORT_KEYS.NBA;
    if (!sportKeys.length) return res.json({ gaps: [], scanned: 0 });

    const gaps: LineGap[] = [];
    const comparedGames = new Set<string>();  // games where Pinnacle + a soft book both priced ≥1 shared market
    let scanned = 0;
    let bestGap = 0;                            // largest fair-prob gap found, even below the 3pt bar

    // Scan EVERY league key for the sport (was just sportKeys[0] — that missed
    // Wimbledon/US Open for tennis, every non-WC league for soccer, etc.).
    for (const key of sportKeys) {
      const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
      const r = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (!r.ok) continue;                      // out-of-season key → skip, don't abort the scan
      const events = await r.json() as OddsEvent[];
      if (!Array.isArray(events)) continue;
      scanned += events.length;

      for (const ev of events.slice(0, 15)) {
        const pinnacle = ev.bookmakers.find(b => b.key === 'pinnacle');
        if (!pinnacle) continue;
        const softBooks = ev.bookmakers.filter(b => ['draftkings', 'fanduel'].includes(b.key));
        if (!softBooks.length) continue;

        for (const market of pinnacle.markets) {
          // Devig Pinnacle's two-way market to FAIR (no-vig) probabilities.
          const pinFair = fairMarketProbs(market.outcomes);
          if (!pinFair) continue;

          for (const pinOut of market.outcomes) {
            const pinFairProb = pinFair.get(pinOut.name);
            if (pinFairProb == null) continue;

            for (const soft of softBooks) {
              const sm = soft.markets.find(m => m.key === market.key);
              if (!sm) continue;
              // For spreads, only compare the SAME handicap — a price gap across
              // different points (-6.5 vs -7) is a line difference, not a price edge.
              const so = sm.outcomes.find(o =>
                o.name === pinOut.name && (market.key !== 'spreads' || o.point === pinOut.point));
              if (!so) continue;
              const softFair = fairMarketProbs(sm.outcomes);
              if (!softFair) continue;
              const softFairProb = softFair.get(pinOut.name);
              if (softFairProb == null) continue;

              // Gap in FAIR probability points. Comparing raw implied probs was
              // biased: Pinnacle runs ~2-3% vig vs DK/FD ~5%, so the soft book's
              // extra juice inflated every side and the old gap almost never cleared
              // +3. Devigging both books first makes the gap a real disagreement.
              const gap = Math.round((pinFairProb - softFairProb) * 1000) / 10;
              comparedGames.add(`${ev.away_team} @ ${ev.home_team}`);
              if (gap > bestGap) bestGap = gap;
              if (gap >= 3) {
                gaps.push({
                  game:             `${ev.away_team} @ ${ev.home_team}`,
                  market:           market.key,
                  outcome:          pinOut.name,
                  pinnacle_odds:    pinOut.price,
                  book:             soft.title,
                  book_odds:        so.price,
                  pinnacle_implied: Math.round(pinFairProb * 1000) / 10,
                  book_implied:     Math.round(softFairProb * 1000) / 10,
                  gap_pct:          gap,
                  // Bet the sharp side at the soft book (better price, sharp direction)
                  best_line:        so.price,
                  best_book:        soft.title,
                  signal:           gap >= 6 ? 'STRONG_SHARP' : 'SOFT_SHARP',
                  commence_time:    ev.commence_time,
                });
              }
            }
          }
        }
      }
    }

    gaps.sort((a, b) => b.gap_pct - a.gap_pct);
    const result = {
      gaps: gaps.slice(0, 12),
      scanned,                                   // events fetched across all league keys
      compared: comparedGames.size,              // events actually priced by Pinnacle AND a soft book
      best_gap: Math.round(bestGap * 10) / 10,   // tightest = largest fair-prob gap found
      sport,
      computed_at: new Date().toISOString(),
    };
    setCache(cacheKey, result);
    res.json(result);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    res.status(500).json({ error: "LINE_GAPS_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// ARBITRAGE SCANNER — cross-book market discrepancy detection
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/arbitrage', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });
  if (!ODDS_API_KEY) return res.status(503).json({ error: "ODDS_API_NOT_CONFIGURED" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const cacheKey = `arb:${sport}`;
    const cached = getCached(cacheKey);
    if (cached) { res.json(cached); return; }

    const sportKeys = SPORT_KEYS[sport] || SPORT_KEYS.NBA;
    if (sportKeys.length === 0) { res.json({ opportunities: [], scanned: 0 }); return; }

    const opportunities: ArbitrageOpportunity[] = [];
    let scanned = 0;

    for (const key of sportKeys) {
      const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h&bookmakers=pinnacle,draftkings,fanduel,betmgm,caesars&dateFormat=iso&oddsFormat=american`;
      const arbRes = await fetch(url, { signal: AbortSignal.timeout(6000) });
      if (!arbRes.ok) continue;

      const events = await arbRes.json() as OddsEvent[];
      if (!Array.isArray(events)) continue;
      scanned += events.length;

      opportunities.push(...ArbitrageService.findOpportunities(events));
    }

    const result = { opportunities, scanned };
    setCache(cacheKey, result);
    res.json(result);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    res.status(500).json({ error: "ARBITRAGE_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// IMAGE PROXY — ESPN headshots for html2canvas (ESPN domains only)
// ─────────────────────────────────────────────────────────────────────────────
const ALLOWED_HOSTS = ['a.espncdn.com', 'cdn.nba.com', 'img.mlbstatic.com'];

app.get('/api/proxy-image', async (req: express.Request, res: express.Response) => {
  try {
    const raw = req.query.url as string;
    if (!raw) return res.status(400).send('url required');

    let parsed: URL;
    try { parsed = new URL(decodeURIComponent(raw)); }
    catch { return res.status(400).send('invalid url'); }

    if (!ALLOWED_HOSTS.includes(parsed.hostname)) {
      return res.status(403).send('host not allowed');
    }

    const response = await fetch(parsed.toString(), { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`upstream ${response.status}`);

    const buf = Buffer.from(await response.arrayBuffer());
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Content-Type', response.headers.get('content-type') || 'image/png');
    res.set('Cache-Control', 'public, max-age=86400');
    res.send(buf);
  } catch (e) {
    res.status(500).send('proxy error');
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SERVE BUILT FRONTEND in production
// ─────────────────────────────────────────────────────────────────────────────
// ── Kronos Line Movement ──────────────────────────────────────────────────────
// POST /api/line-movement
// Body: { history: LineRecord[], steps?: number, n_samples?: number }
// Returns: { direction, mean, std, confidence } | { error, note }
const KRONOS_ADAPTER = path.resolve(process.cwd(), 'scripts/kronos_adapter.py');
const KRONOS_CWD     = path.resolve(process.cwd(), 'scripts/kronos');

interface KronosLineRecord { open: number; high: number; low: number; close: number; volume: number; amount: number }

function runKronosAdapter(
  history: KronosLineRecord[], steps: number, n_samples: number
): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    const input = JSON.stringify({ history, steps, n_samples });
    const py    = spawn('python3', [KRONOS_ADAPTER, '--json'], { cwd: KRONOS_CWD });

    let stdout = '';
    let stderr = '';
    py.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
    py.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });
    py.stdin.write(input);
    py.stdin.end();

    const timer = setTimeout(() => { py.kill(); resolve({ error: 'Kronos timeout' }); }, 90_000);

    py.on('close', () => {
      clearTimeout(timer);
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch {
        resolve({ error: 'Kronos parse failed', detail: stderr.slice(0, 300) });
      }
    });
  });
}

app.post('/api/line-movement', async (req: express.Request, res: express.Response) => {
  const { history, steps = 3, n_samples = 30 } = req.body as {
    history: KronosLineRecord[];
    steps?: number;
    n_samples?: number;
  };

  if (!Array.isArray(history) || history.length < 5) {
    res.status(400).json({ error: 'history array required (min 5 records)' });
    return;
  }

  res.json(await runKronosAdapter(history, steps, n_samples));
});

// ── Tennis line-history accumulation ────────────────────────────────────────
// Kronos needs a real time series of the LINE to forecast movement — this app
// had no persisted odds history anywhere (see project memory: "closing_odds
// never populated"). Rather than adding NEW polling calls to build one (which
// would burn Odds API quota outside real usage), this piggybacks on odds the
// app already fetches for real tennis predictions: every /predict call for a
// TENNIS matchup appends the observed price as one point. History accumulates
// organically over real usage, never fabricated, and no extra API calls.
const TENNIS_LINE_HISTORY_PATH = path.resolve(__dirname, 'data/tennis_line_history.json');
const TENNIS_LINE_HISTORY_MAX  = 512;      // Kronos max context
const TENNIS_LINE_HISTORY_MIN  = 5;        // adapter's own floor
const TENNIS_SNAPSHOT_COOLDOWN_MS = 60_000; // don't double-record within a minute

function tennisMatchKey(home: string, away: string): string {
  return `${home.trim().toLowerCase()}|${away.trim().toLowerCase()}`;
}

function loadTennisLineHistory(): Record<string, Array<KronosLineRecord & { ts: number }>> {
  try {
    return JSON.parse(readFileSync(TENNIS_LINE_HISTORY_PATH, 'utf8'));
  } catch {
    return {};
  }
}

function recordTennisLineSnapshot(home: string, away: string, americanOdds: number): void {
  try {
    const store = loadTennisLineHistory();
    const key = tennisMatchKey(home, away);
    const series = store[key] ?? [];
    const now = Date.now();
    const last = series[series.length - 1];
    if (last && now - last.ts < TENNIS_SNAPSHOT_COOLDOWN_MS) return; // too soon, skip

    // Each observation is a single point-in-time price, not a range — recorded
    // as a zero-range bar (open=high=low=close). volume=1 per real observation,
    // amount=0 (no handle data — never invented).
    series.push({ ts: now, open: americanOdds, high: americanOdds, low: americanOdds,
                   close: americanOdds, volume: 1, amount: 0 });
    store[key] = series.slice(-TENNIS_LINE_HISTORY_MAX);
    writeFileSync(TENNIS_LINE_HISTORY_PATH, JSON.stringify(store));
  } catch (e) {
    console.error('recordTennisLineSnapshot failed (non-blocking):', e instanceof Error ? e.message : String(e));
  }
}

// GET /api/tennis-line-movement?home=X&away=Y — Kronos forecast off the
// REAL accumulated history for this matchup. Returns INSUFFICIENT_HISTORY
// (with a count) instead of ever calling Kronos on fabricated data.
app.get('/api/tennis-line-movement', async (req: express.Request, res: express.Response) => {
  const home = String(req.query.home ?? '');
  const away = String(req.query.away ?? '');
  if (!home || !away) {
    res.status(400).json({ error: 'home and away query params required' });
    return;
  }
  const store = loadTennisLineHistory();
  const series = store[tennisMatchKey(home, away)] ?? [];
  if (series.length < TENNIS_LINE_HISTORY_MIN) {
    res.json({ status: 'INSUFFICIENT_HISTORY', n: series.length, need: TENNIS_LINE_HISTORY_MIN,
               note: 'history accumulates from real /predict calls for this matchup — not enough observations yet' });
    return;
  }
  const history = series.map(({ ts: _ts, ...rec }) => rec);
  res.json({ status: 'OK', n: series.length, ...(await runKronosAdapter(history, 3, 30)) });
});

// ─────────────────────────────────────────────────────────────────────────────
// UPSET RADAR — pure math surprise detector. No AI, no hallucination possible.
// Pinnacle devigged dog probability = real upset chance; if a soft book pays
// more than fair for that dog, EV is positive. Sorted by EV, then probability.
// ─────────────────────────────────────────────────────────────────────────────
interface UpsetCandidate {
  sport: string;
  game: string;
  commence_time: string;
  underdog: string;
  favorite: string;
  upset_prob_pct: number;   // devigged from Pinnacle — the real chance of the surprise
  fair_odds: number;        // American odds the dog SHOULD pay at that prob
  best_odds: number;        // best dog price found across books
  best_book: string;
  ev_pct: number;           // EV per $100 at best price, using Pinnacle fair prob
}

function probToAmerican(p: number): number {
  if (p >= 0.5) return Math.round((p / (1 - p)) * -100);
  return Math.round(((1 - p) / p) * 100);
}

app.get('/api/upset-radar', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 10, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const sportParam = ((req.query.sport as string) || 'ALL').toUpperCase();
    const cacheKey = `upset-radar:${sportParam}`;
    const cached = getCached(cacheKey);
    if (cached) { res.json(cached); return; }

    const activeKeys = await getActiveSportKeys();
    const sports = sportParam === 'ALL'
      ? ['SOCCER', 'NBA', 'WNBA', 'MLB', 'NHL', 'TENNIS']
      : [sportParam];

    const candidates: UpsetCandidate[] = [];
    let scanned = 0;

    for (const sport of sports) {
      const keys = (SPORT_KEYS[sport] ?? []).filter(k => !activeKeys || activeKeys.has(k));
      const key = sport === 'TENNIS' && activeKeys
        ? [...activeKeys].find(k => k.startsWith('tennis_') && !k.includes('winner'))
        : keys[0];
      if (!key) continue;

      try {
        const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h&bookmakers=pinnacle,draftkings,fanduel,betmgm,caesars&oddsFormat=american`;
        const r = await fetch(url, { signal: AbortSignal.timeout(6000) });
        if (!r.ok) { console.error(`Upset radar ${sport} HTTP ${r.status}`); continue; }
        const events = await r.json() as OddsEvent[];

        for (const ev of events) {
          scanned++;
          const pinnacle = ev.bookmakers.find(b => b.key === 'pinnacle');
          const pinH2h = pinnacle?.markets.find(m => m.key === 'h2h');
          if (!pinH2h || pinH2h.outcomes.length < 2 || pinH2h.outcomes.length > 3) continue;

          // Devig across ALL outcomes (handles soccer 3-way with draw)
          const implieds = pinH2h.outcomes.map(o => ({ name: o.name, raw: impliedProb(o.price) }));
          const overround = implieds.reduce((s, o) => s + o.raw, 0);
          const teams = implieds
            .map(o => ({ name: o.name, prob: o.raw / overround }))
            .filter(o => o.name.toLowerCase() !== 'draw')
            .sort((a, b) => a.prob - b.prob);
          if (teams.length !== 2) continue;
          const dog = { name: teams[0].name, prob: teams[0].prob, favName: teams[1].name };
          // Live-dog floor: 20% in 2-way; 12% in 3-way (draw absorbs probability in soccer)
          const liveDogFloor = pinH2h.outcomes.length === 3 ? 0.12 : 0.20;
          if (dog.prob < liveDogFloor) continue;

          // Best dog price across all books
          let bestOdds = -Infinity;
          let bestBook = '';
          for (const book of ev.bookmakers) {
            const m = book.markets.find(mk => mk.key === 'h2h');
            const out = m?.outcomes.find(o => o.name === dog.name);
            if (out && toDecimal(out.price) > toDecimal(bestOdds === -Infinity ? -10000 : bestOdds)) {
              bestOdds = out.price;
              bestBook = book.key;
            }
          }
          if (bestOdds === -Infinity) continue;

          const dec = toDecimal(bestOdds);
          const evPct = (dog.prob * (dec - 1) - (1 - dog.prob)) * 100;

          candidates.push({
            sport,
            game: `${ev.away_team} @ ${ev.home_team}`,
            commence_time: ev.commence_time,
            underdog: dog.name,
            favorite: dog.favName,
            upset_prob_pct: Math.round(dog.prob * 1000) / 10,
            fair_odds: probToAmerican(dog.prob),
            best_odds: bestOdds,
            best_book: bestBook,
            ev_pct: Math.round(evPct * 100) / 100,
          });
        }
      } catch (e: unknown) {
        console.error(`Upset radar ${sport}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }

    const sorted = [...candidates].sort((a, b) => b.ev_pct - a.ev_pct || b.upset_prob_pct - a.upset_prob_pct);
    const payload = {
      success: true,
      upsets: sorted.slice(0, 20),
      scanned,
      computed_at: new Date().toISOString(),
      note: 'Pure market math — Pinnacle devigged probability vs best available price. Positive EV = soft book overpaying the dog.',
    };
    setCache(cacheKey, payload, 10 * 60 * 1000);
    res.json(payload);
  } catch (e: unknown) {
    res.status(500).json({ error: 'UPSET_RADAR_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// PICK LEDGER — proven track record (log → settle → stats with CLV)
// ─────────────────────────────────────────────────────────────────────────────
app.post('/api/ledger/pick', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 30, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const { sport, game, selection, odds, stake_units, source, predicted_prob, market_key, outcome, point } = req.body ?? {};
    const oddsNum = Number(odds);
    if (!sport || !game || !selection || !Number.isFinite(oddsNum) || oddsNum === 0 || (oddsNum > -100 && oddsNum < 100)) {
      return res.status(400).json({ error: 'INVALID_PICK', message: 'sport, game, selection and valid American odds required' });
    }
    // Use caller-supplied identity if present, else derive it from the selection for CLV capture.
    const ident = (market_key && outcome)
      ? { market_key, outcome, point: point != null ? Number(point) : null }
      : parseSelectionIdentity(String(selection), String(game));
    const predProb = predicted_prob != null && Number.isFinite(Number(predicted_prob)) ? Number(predicted_prob) : null;
    const pick = await addPick({ sport, game, selection, odds: oddsNum, stake_units: Number(stake_units) || 1, source, predicted_prob: predProb, ...ident });
    res.json({ success: true, pick });
  } catch (e: unknown) {
    res.status(500).json({ error: 'LEDGER_WRITE_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

app.post('/api/ledger/settle', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 30, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const { id, result, closing_odds } = req.body ?? {};
    if (!id || !['W', 'L', 'P'].includes(result)) {
      return res.status(400).json({ error: 'INVALID_SETTLE', message: 'id and result (W/L/P) required' });
    }
    const closing = closing_odds != null && Number.isFinite(Number(closing_odds)) ? Number(closing_odds) : undefined;
    const pick = await settlePick(id, result, closing);
    if (pick === 'NOT_FOUND') return res.status(404).json({ error: 'PICK_NOT_FOUND' });
    if (pick === 'ALREADY_SETTLED') {
      return res.status(409).json({ error: 'ALREADY_SETTLED', message: 'Settled picks are immutable — the record cannot be rewritten.' });
    }
    res.json({ success: true, pick });
  } catch (e: unknown) {
    res.status(500).json({ error: 'LEDGER_WRITE_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

app.get('/api/ledger/stats', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 30, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const ledger = await loadLedger();
    res.json({ success: true, stats: computeStats(ledger) });
  } catch (e: unknown) {
    res.status(500).json({ error: 'LEDGER_READ_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

app.get('/api/ledger/picks', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 30, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const ledger = await loadLedger();
    res.json({ success: true, picks: [...ledger].reverse().slice(0, 100) });
  } catch (e: unknown) {
    res.status(500).json({ error: 'LEDGER_READ_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

// ── CLV capture — stamp the closing line on pending picks just before kickoff ──
// Reads the structured identity stored on each pick and re-finds the exact line.
// Only ML/spread picks with a clean identity are captured; AH/props stay manual.
async function fetchRawEvents(sportKey: string): Promise<OddsEvent[]> {
  const url = `${ODDS_API_BASE}/sports/${sportKey}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
  const r = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!r.ok) return [];
  const events = await r.json();
  return Array.isArray(events) ? events as OddsEvent[] : [];
}

async function runClvCapture(): Promise<{ stamped: number; checked: number }> {
  if (!ODDS_API_KEY) return { stamped: 0, checked: 0 };
  const ledger = await loadLedger();
  const pending = pendingNeedingClose(ledger);
  if (!pending.length) return { stamped: 0, checked: 0 };

  let stamped = 0;
  // Fetch each relevant sport's league keys once, match every pending pick against it.
  for (const sport of [...new Set(pending.map(p => p.sport))]) {
    const events: OddsEvent[] = [];
    for (const key of (SPORT_KEYS[sport] || [])) events.push(...await fetchRawEvents(key));
    if (!events.length) continue;

    for (const pick of pending.filter(p => p.sport === sport)) {
      const hit = findClose(pick, events as unknown as CaptureEvent[]);
      if (!hit || !inCaptureWindow(hit.commence_time)) continue;  // only stamp the true pre-kickoff close
      const r = await stampClosingOdds(pick.id, hit.price);
      if (typeof r !== 'string') stamped++;
    }
  }
  return { stamped, checked: pending.length };
}

// Manual trigger (the auto-cron is opt-in via ENABLE_CLV_CAPTURE so dev never hits the API).
app.post('/api/ledger/capture-clv', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  if (!ODDS_API_KEY) return res.status(503).json({ error: 'ODDS_API_NOT_CONFIGURED' });
  try {
    const result = await runClvCapture();
    res.json({ success: true, ...result });
  } catch (e: unknown) {
    res.status(500).json({ error: 'CLV_CAPTURE_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// PYTHON REPORT BRIDGE — spawn a script, feed optional stdin, parse its --json.
// Shared by the slip linter (pre-bet gate) and the ledger CLV/calibration report.
// Pure local compute — no external API, safe in dev/test.
// ─────────────────────────────────────────────────────────────────────────────
const SLIP_LINTER   = path.resolve(process.cwd(), 'scripts/slip_linter.py');
const LEDGER_REPORT = path.resolve(process.cwd(), 'scripts/ledger_report.py');

function spawnPythonJson(script: string, args: string[], stdin: string | null, timeoutMs = 8_000): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const py = spawn('python3', [script, ...args]);
    let out = '';
    let err = '';
    py.stdout.on('data', (c: Buffer) => { out += c.toString(); });
    py.stderr.on('data', (c: Buffer) => { err += c.toString(); });
    if (stdin != null) py.stdin.write(stdin);
    py.stdin.end();
    const timer = setTimeout(() => { py.kill(); reject(new Error('PY_TIMEOUT')); }, timeoutMs);
    py.on('close', () => {
      clearTimeout(timer);
      try { resolve(JSON.parse(out.trim())); }
      catch { reject(new Error(err.slice(0, 300) || 'PY_PARSE_FAILED')); }
    });
  });
}

interface LintLeg { decimal: number; selection?: string }
// Run the slip linter on a set of legs — verdict object, or null on failure (non-blocking).
async function lintLegs(legs: LintLeg[]): Promise<unknown | null> {
  try { return await spawnPythonJson(SLIP_LINTER, ['--json'], JSON.stringify({ legs })); }
  catch { return null; }
}

// SLIP LINTER — pre-bet gate. Scores a proposed ticket against the user's OWN
// settled record (data/slips_raw.txt): ACCEPT / TRIM / REJECT with real ROI cited.
app.post('/api/lint-slip', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 60, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  const { legs } = req.body as { legs?: LintLeg[] };
  if (!Array.isArray(legs) || legs.length === 0) {
    return res.status(400).json({ error: 'NEED_LEGS', message: 'body: { legs: [{ decimal, selection }] }' });
  }
  if (legs.some(l => typeof l?.decimal !== 'number' || !(l.decimal > 1))) {
    return res.status(400).json({ error: 'BAD_DECIMAL', message: 'each leg needs decimal odds > 1' });
  }
  const data = await lintLegs(legs);
  if (data == null) return res.status(500).json({ error: 'LINTER_FAILED' });
  res.json({ success: true, data });
});

interface LintSlip { legs: (LintLeg & { match?: string })[] }
// PORTFOLIO LINTER — lints the whole day's card at once. Catches the two leaks a
// single-slip lint can't see: the same leg cloned across slips (one soft leg dies,
// every ticket dies — the Jodar leak) and 3+ correlated sub-markets of one match
// stacked in one slip (the Suiza-Argelia leak).
app.post('/api/lint-portfolio', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 60, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  const { slips } = req.body as { slips?: LintSlip[] };
  if (!Array.isArray(slips) || slips.length === 0 || slips.some(s => !Array.isArray(s?.legs) || s.legs.length === 0)) {
    return res.status(400).json({ error: 'NEED_SLIPS', message: 'body: { slips: [{ legs: [{ decimal, selection, match? }] }] }' });
  }
  if (slips.some(s => s.legs.some(l => typeof l?.decimal !== 'number' || !(l.decimal > 1)))) {
    return res.status(400).json({ error: 'BAD_DECIMAL', message: 'each leg needs decimal odds > 1' });
  }
  try {
    const data = await spawnPythonJson(SLIP_LINTER, ['--json'], JSON.stringify({ slips }));
    res.json({ success: true, data });
  } catch {
    res.status(500).json({ error: 'LINTER_FAILED' });
  }
});

// LEDGER REPORT — CLV grading + model calibration over the booked picks. Reads
// data/pick_ledger.json only; no Odds API call, safe in dev/test.
app.get('/api/ledger/report', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 30, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  try {
    const data = await spawnPythonJson(LEDGER_REPORT, ['--json'], null);
    res.json({ success: true, data });
  } catch (e: unknown) {
    res.status(500).json({ error: 'REPORT_FAILED', message: e instanceof Error ? e.message : String(e) });
  }
});

// Full board — every priceable market + fair odds (fire if book >= fair).
// Proxies the edge_api /full-board endpoint so the front-end Game Breakdown can
// render all markets. No external API: pure model math off the supplied 1X2.
app.post('/api/full-board', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 20, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  const { home_team, away_team, home_odds, draw_odds, away_odds } = req.body ?? {};
  if (home_odds == null || draw_odds == null || away_odds == null) {
    return res.status(400).json({ error: 'NEED_1X2_DECIMAL_ODDS' });
  }
  try {
    const r = await fetch('http://127.0.0.1:8001/full-board', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ home_team, away_team, home_odds, draw_odds, away_odds }),
      signal: AbortSignal.timeout(4000),
    });
    if (!r.ok) return res.status(502).json({ error: 'EDGE_API_ERROR', status: r.status });
    res.json({ success: true, data: await r.json() });
  } catch (e: unknown) {
    res.status(503).json({ error: 'EDGE_API_UNAVAILABLE', message: e instanceof Error ? e.message : String(e) });
  }
});

// ── Tennis rankings auto-refresh — ATP/WTA ranks move weekly (publish every Monday).
// Pulls the OFFICIAL ATP+WTA ranks via ESPN (free, 0 Odds-API quota) into
// all_ratings.json and stamps data/ratings_meta.json so stale ranks can be flagged.
const TENNIS_RANKS_FETCH = path.resolve(process.cwd(), 'scripts/fetch_tennis_ratings.py');

function refreshTennisRanks(): Promise<{ ok: boolean; out: string }> {
  return new Promise((resolve) => {
    const py = spawn('python3', [TENNIS_RANKS_FETCH]);
    let out = '';
    py.stdout.on('data', (c: Buffer) => { out += c.toString(); });
    py.stderr.on('data', (c: Buffer) => { out += c.toString(); });
    const timer = setTimeout(() => { py.kill(); resolve({ ok: false, out: 'timeout' }); }, 30_000);
    py.on('close', (code) => { clearTimeout(timer); resolve({ ok: code === 0, out: out.slice(-400) }); });
  });
}

// Manual trigger — the weekly cron handles the routine refresh.
app.post('/api/refresh-rankings', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 3, 60_000)) return res.status(429).json({ error: 'RATE_LIMIT' });
  const r = await refreshTennisRanks();
  if (!r.ok) return res.status(502).json({ error: 'REFRESH_FAILED', detail: r.out });
  res.json({ success: true, detail: r.out });
});

const distPath = path.resolve(process.cwd(), 'dist');
app.use(express.static(distPath));
app.get('/{*splat}', (_req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

// Auto-CLV capture — OFF by default so dev/test never call the Odds API (CLAUDE.md).
// Set ENABLE_CLV_CAPTURE=true in production to stamp closing lines every 15 min.
if (process.env.ENABLE_CLV_CAPTURE === 'true') {
  cron.schedule('*/15 * * * *', () => {
    runClvCapture()
      .then(r => { if (r.stamped) console.info(`[CLV] stamped ${r.stamped}/${r.checked} closing lines`); })
      .catch(e => console.error('[CLV] capture failed:', e instanceof Error ? e.message : String(e)));
  });
  console.info('[CLV] auto-capture enabled — every 15 min');
}

// Tennis ranks auto-refresh — ATP/WTA rankings publish every Monday. ESPN is free
// (0 Odds-API quota), so this runs by default; set DISABLE_RANK_REFRESH=true to skip.
if (process.env.DISABLE_RANK_REFRESH !== 'true') {
  cron.schedule('0 6 * * 1', () => {   // Mondays 06:00 — just after ranks publish
    refreshTennisRanks()
      .then(r => console.info(`[RANKS] weekly tennis refresh ${r.ok ? 'ok' : 'FAILED'}`))
      .catch(e => console.error('[RANKS] refresh failed:', e instanceof Error ? e.message : String(e)));
  });
  console.info('[RANKS] weekly tennis rank refresh scheduled — Mondays 06:00');
}

app.listen(port, '0.0.0.0', () => {
  console.info(`CTE LOCKS Engine live → http://localhost:${port}`);
});
