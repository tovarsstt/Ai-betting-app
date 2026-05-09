import express from 'express';
// @ts-expect-error - no types
import cors from 'cors';
import dotenv from 'dotenv';
import Anthropic from '@anthropic-ai/sdk';
import path from 'path';
import { fileURLToPath } from 'url';
import { readFileSync } from 'fs';
import { spawn, ChildProcess } from 'child_process';
import { router } from './src/services/modelRouter.js';
import { memory } from './src/lib/persistentMemory.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '.env'), override: true });

// ── Model weights — loaded from data/model_weights.json ──────────────────────
interface ModelWeights {
  math_weight: number;
  sentiment_weight: number;
  dissonance_threshold: number;
  sport_confidence: Record<string, number>;
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

// ── Edge Model API — spawned as child process ─────────────────────────────────
let _edgeProc: ChildProcess | null = null;
function startEdgeApi() {
  const script = path.resolve(__dirname, 'scripts/edge_api.py');
  _edgeProc = spawn('python3', [script], { stdio: ['ignore', 'pipe', 'pipe'] });
  _edgeProc.stdout?.on('data', (d: Buffer) => process.stdout.write('[EdgeAPI] ' + d));
  _edgeProc.stderr?.on('data', (d: Buffer) => {
    const msg = d.toString();
    if (!msg.includes('DeprecationWarning') && !msg.includes('on_event')) process.stderr.write('[EdgeAPI] ' + msg);
  });
  _edgeProc.on('exit', (code: number | null) => {
    if (code !== 0 && code !== null) setTimeout(startEdgeApi, 5000);
  });
}
startEdgeApi();
process.on('exit', () => _edgeProc?.kill());

// ── fetchEdgeModel — calls edge API, returns formatted quant context block ────
interface EdgeResult {
  sport: string; predicted_margin: number; spread: number; model_edge: number;
  home_cover_prob: number; away_cover_prob: number;
  home_ev_pct: number; away_ev_pct: number;
  home_kelly_usd: number; away_kelly_usd: number;
  home_true_prob: number; away_true_prob: number;
  vig_pct: number; bet_signal: string; edge_strength: string;
  home_ratings: Record<string, number>; away_ratings: Record<string, number>;
  model_mae: number; trained_on: number; model_loaded: boolean;
  lambda_home?: number; lambda_away?: number; method?: string;
}

async function fetchEdgeModel(
  sport: string, homeTeam: string, awayTeam: string,
  spread: number, homeOdds: number, awayOdds: number,
  bankroll = 1000
): Promise<string> {
  try {
    const r = await fetch('http://127.0.0.1:8001/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sport, home_team: homeTeam, away_team: awayTeam,
                             spread, home_odds: homeOdds, away_odds: awayOdds, bankroll }),
      signal: AbortSignal.timeout(4000),
    });
    if (!r.ok) return '';
    const d = await r.json() as EdgeResult;
    const conf = (MODEL_WEIGHTS.sport_confidence as Record<string, { trained_games: number; reliable: boolean }>)?.[sport.toUpperCase()];
    const confStr = conf?.reliable ? `${conf.trained_games.toLocaleString()} games trained` : 'LOW CONFIDENCE';
    const maeStr = sport === 'MLB' ? `±${d.model_mae} runs` : sport === 'Soccer' ? `±${d.model_mae} goals` : `±${d.model_mae} pts`;
    const poissonLine = d.lambda_home != null
      ? `• Poisson λ: HOME ${d.lambda_home} goals / AWAY ${d.lambda_away} goals expected\n`
      : '';
    const ratingsLine = sport.toUpperCase() === 'NBA' || sport.toUpperCase() === 'WNBA'
      ? `• Home: OffRtg ${d.home_ratings.off_rtg?.toFixed(1)} DefRtg ${d.home_ratings.def_rtg?.toFixed(1)} NetRtg ${d.home_ratings.net_rtg?.toFixed(1)} | Away: OffRtg ${d.away_ratings.off_rtg?.toFixed(1)} DefRtg ${d.away_ratings.def_rtg?.toFixed(1)} NetRtg ${d.away_ratings.net_rtg?.toFixed(1)}\n`
      : sport.toUpperCase() === 'MLB'
      ? `• Home: RS/G ${d.home_ratings.rs?.toFixed(2)} RA/G ${d.home_ratings.ra?.toFixed(2)} | Away: RS/G ${d.away_ratings.rs?.toFixed(2)} RA/G ${d.away_ratings.ra?.toFixed(2)}\n`
      : sport.toUpperCase() === 'NFL'
      ? `• Home: PPG ${d.home_ratings.ppg} PAG ${d.home_ratings.pag} NET ${d.home_ratings.net} | Away: PPG ${d.away_ratings.ppg} PAG ${d.away_ratings.pag} NET ${d.away_ratings.net}\n`
      : `• Home ratings: ${JSON.stringify(d.home_ratings)} | Away ratings: ${JSON.stringify(d.away_ratings)}\n`;
    return [
      `\n━━ QUANTITATIVE MODEL (${sport.toUpperCase()} — ${confStr}) ━━`,
      `• Predicted margin: ${homeTeam} ${d.predicted_margin > 0 ? '+' : ''}${d.predicted_margin} vs spread ${d.spread > 0 ? '+' : ''}${d.spread} → MODEL EDGE ${d.model_edge > 0 ? '+' : ''}${d.model_edge} pts`,
      poissonLine.trim() ? poissonLine.trimEnd() : null,
      `• Cover probability: HOME ${(d.home_cover_prob * 100).toFixed(1)}% / AWAY ${(d.away_cover_prob * 100).toFixed(1)}%`,
      `• Devigged true prob: HOME ${(d.home_true_prob * 100).toFixed(1)}% / AWAY ${(d.away_true_prob * 100).toFixed(1)}% (book vig: ${d.vig_pct}%)`,
      `• Model EV: HOME ${d.home_ev_pct > 0 ? '+' : ''}${d.home_ev_pct}% / AWAY ${d.away_ev_pct > 0 ? '+' : ''}${d.away_ev_pct}%`,
      `• Half-Kelly bet: HOME $${d.home_kelly_usd} / AWAY $${d.away_kelly_usd} (of $${bankroll})`,
      ratingsLine.trimEnd(),
      `• Model uncertainty: ${maeStr} | Signal: ${d.bet_signal} [${d.edge_strength}]`,
      `⚡ INSTRUCTION: ${d.edge_strength === 'STRONG' || d.edge_strength === 'MODERATE' ? `Model says ${d.bet_signal} with ${d.edge_strength} edge — HEAVILY weight this. Math weight = ${MODEL_WEIGHTS.math_weight * 100}%.` : `Model edge is ${d.edge_strength} — use as secondary input only.`}`,
    ].filter(Boolean).join('\n');
  } catch {
    return '';
  }
}

// ── parseOddsForTeams — extract home/away + spread from live odds text ────────
function parseOddsForTeams(oddsText: string): { home: string; away: string; spread: number; homeOdds: number; awayOdds: number } | null {
  try {
    // Live odds format: "Away @ Home — HH:MM ET"
    const atMatch = oddsText.match(/([A-Z][a-zA-Z\s]+?)\s+@\s+([A-Z][a-zA-Z\s]+?)\s+[—–-]/);
    if (!atMatch) return null;
    const away = atMatch[1].trim();
    const home = atMatch[2].trim();
    // Name-based extractor — Odds API returns outcomes alphabetically, so index is unreliable.
    // Match team name keywords to find their specific odds/spread in the line.
    const extractByName = (teamName: string, line: string, pattern: string): string | null => {
      const words = teamName.split(' ');
      for (let i = words.length - 1; i >= 0; i--) {
        const kw = words[i].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (kw.length < 3) continue;
        const re = new RegExp(kw + '[^|]*?' + pattern, 'i');
        const m = line.match(re);
        if (m) return m[1];
      }
      return null;
    };
    // Extract spread (home team perspective) from "Spread: Team A -X.X (...) | Team B +X.X (...)"
    const spreadLine = oddsText.match(/Spread:[^\n]*/)?.[0] ?? '';
    const homeSpreadStr = spreadLine ? extractByName(home, spreadLine, '([+-]\\d+\\.?\\d*)\\s*\\(') : null;
    // Fallback: second spread value in the line
    const allSpreads = [...spreadLine.matchAll(/([+-]\d+\.?\d*)\s*\(/g)].map(m => parseFloat(m[1]));
    const spread = homeSpreadStr ? parseFloat(homeSpreadStr) : (allSpreads[1] ?? allSpreads[0] ?? 0);
    // Extract ML odds by team name
    const mlSection = oddsText.match(/Moneyline:[^\n]*/);
    const oddsMatches = mlSection
      ? [...mlSection[0].matchAll(/([+-]\d{2,4})/g)].map(m => parseInt(m[1]))
      : [];
    const homeOdds = mlSection ? (parseInt(extractByName(home, mlSection[0], '([+-]\\d{2,4})') ?? '') || oddsMatches[1] ?? -110) : -110;
    const awayOdds = mlSection ? (parseInt(extractByName(away, mlSection[0], '([+-]\\d{2,4})') ?? '') || oddsMatches[0] ?? -110) : -110;
    return { home, away, spread, homeOdds, awayOdds };
  } catch { return null; }
}

const app = express();
const port = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json({ limit: '1mb' }));

// ── Pure betting math utilities ──────────────────────────────────────────────

// American odds → raw implied probability (vig included)
function impliedProb(americanOdds: number): number {
  if (americanOdds < 0) return (-americanOdds) / (-americanOdds + 100);
  return 100 / (americanOdds + 100);
}

// Remove bookmaker vig from a 2-way market → fair (true) probabilities
function devig(p1Raw: number, p2Raw: number): { p1: number; p2: number; vig: number } {
  const sum = p1Raw + p2Raw;
  return { p1: p1Raw / sum, p2: p2Raw / sum, vig: (sum - 1) * 100 };
}

// American odds → decimal odds
function toDecimal(americanOdds: number): number {
  return americanOdds >= 0 ? americanOdds / 100 + 1 : 100 / (-americanOdds) + 1;
}

// Half-Kelly fraction — how much of bankroll to bet (capped 0–25% for ruin prevention)
// p = true win probability, americanOdds = line being bet
function halfKelly(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  if (b <= 0 || p <= 0 || p >= 1) return 0;
  const fullKelly = (b * p - (1 - p)) / b;
  return Math.max(0, Math.min(fullKelly / 2, 0.25));
}

// Expected Value as decimal (positive = +EV)
function ev(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  return p * b - (1 - p);
}

// Standard normal CDF — Hart approximation, accurate to 5 decimal places
function normalCDF(z: number): number {
  if (z < -8) return 0;
  if (z >  8) return 1;
  const p = 0.2316419;
  const b = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
  const t   = 1 / (1 + p * Math.abs(z));
  const y   = ((((b[4]*t + b[3])*t + b[2])*t + b[1])*t + b[0]) * t;
  const pdf = Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  return z >= 0 ? 1 - pdf * y : pdf * y;
}

// Point margin → win probability via normal distribution
// sigma: std-dev of final margin (NBA ~11.5, NFL ~13.5, MLB ~3.0 runs)
function marginToWinProb(margin: number, sigma = 11.5): number {
  return normalCDF(margin / sigma);
}

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

// ── Persistent Memory Wrapper (AgentMemory Integration) ────────────────────────
function getCached(key: string): any {
  const now = Date.now();
  const entry = memory.get(key);
  if (entry && entry.expires > now) return entry.data;
  if (entry) memory.delete(key);
  return null;
}

function setCache(key: string, data: any, ttlMs = 15 * 60 * 1000) {
  memory.set(key, { data, expires: Date.now() + ttlMs });
}

// ── SkillLoader (Agent-Skills Integration) ────────────────────────────────────
function getBettingHeuristics(sport: string): string {
  try {
    const coreH = readFileSync(path.resolve(__dirname, 'skills/betting/cte_core_skill.md'), 'utf8');
    const globalH = readFileSync(path.resolve(__dirname, 'skills/betting/global_heuristics.md'), 'utf8');
    const sportPath = path.resolve(__dirname, `skills/betting/${sport.toLowerCase()}_skill.md`);
    const sportH = existsSync(sportPath) ? readFileSync(sportPath, 'utf8') : '';
    return `${coreH}\n\n${globalH}\n\n${sportH}`;
  } catch (err) {
    console.error(`[SkillLoader] Failed to load heuristics for ${sport}:`, err);
    return "CTE LOCKS: Find the edge. No fluff.";
  }
}

// ── Sport-specific bet type context ───────────────────────────────────────────
function getSportBetContext(sport: string): string {
  const ctx: Record<string, string> = {
    NBA: 'Bet types: spreads, moneyline, player props (points, rebounds, assists, steals, blocks, 3-pointers made). Niche: quarter lines, halftime lines, team totals.',
    WNBA: 'Bet types: spreads, moneyline, player props (points, rebounds, assists, steals). Niche: q1/q2 team totals (books set stale), morning CLV props, pace-up team Overs, B2B road fades. Books are 2-3 seasons behind in WNBA modeling — systematic mispricing.',
    MLB: 'Bet types: moneyline, player props (strikeouts, hits, home runs, total bases). F5 (first 5 innings) ML and total. Niche: NRFI, umpire-adjusted lines.',
    NFL: 'Bet types: moneyline, spreads, player props (passing yards, rushing yards, TDs, receptions), game totals. Key numbers: 3, 7, 10.',
    NHL: 'Bet types: puck line (-1.5/+1.5), moneyline, game total (O/U goals), period lines. Player props: shots on goal, goals, assists.',
    SOCCER: 'Bet types: moneyline (1X2), Asian handicap, goals over/under, corners over/under, shots on target over/under. BTTS. Niche: exact score, cards.',
    TENNIS: 'Bet types: moneyline (match winner). Game handicap (+3.5/-3.5). Niche: surface-specific form, post-title hangover fades.',
    UFC: 'Bet types: moneyline, method of victory (KO/TKO, Submission, Decision), ITD (inside the distance). Niche: reach/age advantage flags.',
    F1: 'Bet types: race winner (moneyline), pole position. H2H: driver vs driver, teammate matchup. Niche: DNF props on street circuits.',
  };
  return ctx[sport] || ctx.NBA;
}

// ── Short heuristics (~400 tokens) for simple endpoints — Fix #3 ─────────────
function getShortHeuristics(sport: string): string {
  const base = `SHARP RULES: (1) EV over narrative — find mispriced probability, not just winners. (2) Injury first — missing star = reprice the line. (3) Pinnacle gap ≥8pts = sharp money signal, follow it. (4) Juice filter — skip if vig >15%. (5) Caveman output — cite numbers, no fluff.`;
  const sportNote: Record<string, string> = {
    NBA:    "NBA: blowout risk on spreads >10. B2B = fade star props. SGP: team total + assists not points.",
    WNBA:   "WNBA: books 2-3 yrs behind on modeling = systematic soft lines. Pace exploit: Atlanta/Dallas/Indiana vs slow teams → Over. Star removal = prop explosion (thin rosters). B2B commercial travel → fade road team props. Morning CLV window huge — grab early props.",
    MLB:    "MLB: F5 over full game on aces. Park+weather matters. NRFI sharp single, not parlay leg.",
    NFL:    "NFL: key numbers 3/7/10. Fade QB props with wind >15mph. Never pair QB yards + RB yards in SGP.",
    SOCCER: "Soccer: Asian handicap over 1X2. Fade fraudulent winners (high xG loss teams).",
    TENNIS: "Tennis: surface win% > overall rank. Game handicap > ML on favorites.",
    UFC:    "UFC: wrestler vs striker → wrestler ML or decision. Reach +4in = striking advantage.",
    NHL:    "NHL: starting goalie is single biggest variable. B2B → under.",
  };
  return `${base}\n${sportNote[sport.toUpperCase()] || ""}`;
}

// ── Types ─────────────────────────────────────────────────────────────────────
export interface SGPLeg {
  label: string;
  value: string;
  rationale: string;
  espn_id: string;
}

export interface SwarmAgentData {
  primary_single: string;
  value_gap: string;
  sgp_blueprint: SGPLeg[];
  multi_parlay_anchor: string;
  omni_report: string;
  confidence_score: number;
}

export interface SwarmFinalPayload extends SwarmAgentData {
  swarm_report: {
    quant: SwarmAgentData;
    simulation: SwarmAgentData;
    audit_verdict: string;
  };
  hash: string;
  timestamp: string;
}

export interface AlphaSheetItem {
  rank: number;
  team_logo: string;
  player_name: string;
  metric_label: string;
  metric_value: string;
  season_stat: string;
  ai_score: number;
  status_color: string;
  espn_id: string;
}

export interface AlphaSheetContainer {
  title: string;
  subtitle: string;
  data: AlphaSheetItem[];
  timestamp: string;
}

// ── Parser ────────────────────────────────────────────────────────────────────
const parseJSON = (raw: string): unknown => {
  const clean = raw.replace(/```json|```/g, "").trim();
  try { return JSON.parse(clean); } catch { /* fall through */ }
  const match = clean.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
  if (match) { try { return JSON.parse(match[0]); } catch { /* fall through */ } }
  throw new Error("JSON_PARSE_FAILED");
};

// ── Live Odds API ─────────────────────────────────────────────────────────────
const ODDS_API_KEY = process.env.ODDS_API_KEY || "";
const ODDS_API_BASE = "https://api.the-odds-api.com/v4";

const SPORT_KEYS: Record<string, string[]> = {
  NBA:    ["basketball_nba"],
  WNBA:   ["basketball_wnba"],
  MLB:    ["baseball_mlb"],
  NFL:    ["americanfootball_nfl"],
  SOCCER: ["soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league", "soccer_spain_la_liga", "soccer_brazil_campeonato", "soccer_mexico_ligamx"],
  TENNIS: ["tennis_atp_french_open", "tennis_wta_french_open", "tennis_atp_wimbledon", "tennis_wta_wimbledon", "tennis_atp_us_open", "tennis_wta_us_open", "tennis_atp_italian_open", "tennis_wta_italian_open"],
  F1:     [], // not on Odds API
};

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

// Cache active tennis keys so we don't hit the sports list API on every odds call
let _activeTennisKeys: string[] | null = null;
let _activeTennisExpiry = 0;
async function getActiveTennisKeys(): Promise<string[]> {
  if (_activeTennisKeys && Date.now() < _activeTennisExpiry) return _activeTennisKeys;
  try {
    const r = await fetch(`${ODDS_API_BASE}/sports?apiKey=${ODDS_API_KEY}`, { signal: AbortSignal.timeout(5000) });
    if (!r.ok) return SPORT_KEYS.TENNIS;
    const all = await r.json() as Array<{ key: string; active: boolean }>;
    const active = all.filter(s => s.key.startsWith('tennis_') && s.active).map(s => s.key);
    _activeTennisKeys = active.length ? active : SPORT_KEYS.TENNIS;
    _activeTennisExpiry = Date.now() + 6 * 60 * 60 * 1000; // 6hr cache
    return _activeTennisKeys;
  } catch { return SPORT_KEYS.TENNIS; }
}

// ── Raw odds cache — ONE API call per sport key per 10 min, shared by all callers ─
const _rawOddsCache = new Map<string, { events: OddsEvent[]; expires: number }>();

async function fetchRawOdds(sportKey: string): Promise<OddsEvent[]> {
  const cached = _rawOddsCache.get(sportKey);
  if (cached && Date.now() < cached.expires) return cached.events;
  try {
    const url = `${ODDS_API_BASE}/sports/${sportKey}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (res.status === 422) return [];
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({})) as { error_code?: string };
      if (errBody?.error_code === 'OUT_OF_USAGE_CREDITS') {
        console.warn('[OddsAPI] Quota exhausted');
        _rawOddsCache.set(sportKey, { events: [], expires: Date.now() + 60 * 60 * 1000 }); // block 1hr
      }
      return [];
    }
    const events = await res.json() as OddsEvent[];
    if (!Array.isArray(events)) return [];
    _rawOddsCache.set(sportKey, { events, expires: Date.now() + 10 * 60 * 1000 }); // 10 min
    return events;
  } catch { return []; }
}

async function fetchLiveOdds(sport: string, gameQuery?: string): Promise<string> {
  if (!ODDS_API_KEY) return "Odds API key not configured.";
  let sportKeys = SPORT_KEYS[sport] || SPORT_KEYS.NBA;
  // For tennis, always use dynamically discovered active tournaments
  if (sport.toUpperCase() === 'TENNIS') sportKeys = await getActiveTennisKeys();
  if (sportKeys.length === 0) return `No odds API coverage for ${sport}.`;

  // Tennis: surface type from sport_key — critical betting variable (Rule 9: surface MUST appear in odds block)
  const TENNIS_SURFACE: Record<string, string> = {
    'tennis_atp_french_open':         '🏟️ ROLAND GARROS — Surface: CLAY (slowest, topspin-dominant, baseline grinders excel, big servers fade)',
    'tennis_wta_french_open':         '🏟️ ROLAND GARROS — Surface: CLAY (slowest, topspin-dominant, physical endurance key)',
    'tennis_atp_wimbledon':           '🏟️ WIMBLEDON — Surface: GRASS (fastest, serve+volley, big servers/net players dominate, clay specialists fade)',
    'tennis_wta_wimbledon':           '🏟️ WIMBLEDON — Surface: GRASS (fastest, serve dominant, low bounce, aggressive baseliners)',
    'tennis_atp_us_open':             '🏟️ US OPEN — Surface: HARD/OUTDOOR (medium-fast, night sessions faster ball under lights, loud crowd)',
    'tennis_wta_us_open':             '🏟️ US OPEN — Surface: HARD/OUTDOOR (medium-fast, night session crowd/momentum factor)',
    'tennis_atp_italian_open':        '🏟️ ITALIAN OPEN (Rome) — Surface: CLAY (Roland Garros warmup, baseline grinders excel, big servers fade)',
    'tennis_wta_italian_open':        '🏟️ ITALIAN OPEN (Rome) — Surface: CLAY (pre-RG clay form, topspin/endurance dominant)',
    'tennis_atp_australian_open':     '🏟️ AUSTRALIAN OPEN — Surface: HARD/OUTDOOR (medium-fast, hot Melbourne conditions, big servers thrive, long rallies common)',
    'tennis_wta_australian_open':     '🏟️ AUSTRALIAN OPEN — Surface: HARD/OUTDOOR (medium-fast, heat policy in effect, physically demanding)',
    'tennis_atp_madrid_open':         '🏟️ MADRID OPEN — Surface: CLAY/ALTITUDE (altitude 650m makes ball fly faster than typical clay, slight server advantage vs other clay)',
    'tennis_wta_madrid_open':         '🏟️ MADRID OPEN — Surface: CLAY/ALTITUDE (altitude 650m, ball flies faster, defender slightly less advantaged than standard clay)',
    'tennis_atp_barcelona':           '🏟️ BARCELONA OPEN — Surface: CLAY (slow, high bounce, topspin specialists excel)',
    'tennis_atp_monte_carlo':         '🏟️ MONTE-CARLO — Surface: CLAY (slowest clay in the calendar, defensive baseliners dominate, upsets common)',
    'tennis_atp_montecarlo':          '🏟️ MONTE-CARLO — Surface: CLAY (slowest clay in the calendar, defensive baseliners dominate, upsets common)',
    'tennis_atp_hamburg':             '🏟️ HAMBURG OPEN — Surface: CLAY (outdoor clay, heavy conditions, grinders rewarded)',
    'tennis_wta_hamburg':             '🏟️ HAMBURG OPEN — Surface: CLAY',
    'tennis_atp_halle':               '🏟️ HALLE OPEN — Surface: GRASS (Wimbledon warmup, big servers dominate, net-rusher friendly)',
    'tennis_atp_queens_club':         '🏟️ QUEENS CLUB — Surface: GRASS (Wimbledon warmup, serve-dominant, fast courts)',
    'tennis_wta_eastbourne':          '🏟️ EASTBOURNE — Surface: GRASS (Wimbledon warmup, fast and low-bouncing)',
    'tennis_wta_birmingham':          '🏟️ BIRMINGHAM — Surface: GRASS (Wimbledon warmup)',
    'tennis_atp_miami_open':          '🏟️ MIAMI OPEN — Surface: HARD/OUTDOOR (medium-fast, humid Florida conditions, baseline rallies)',
    'tennis_wta_miami_open':          '🏟️ MIAMI OPEN — Surface: HARD/OUTDOOR (medium-fast, high humidity, consistent ball behavior)',
    'tennis_atp_indian_wells_masters':'🏟️ INDIAN WELLS — Surface: HARD/OUTDOOR (fast, dry desert air, ball stays low, big hitters favored)',
    'tennis_wta_indian_wells_masters':'🏟️ INDIAN WELLS — Surface: HARD/OUTDOOR (fast, desert conditions, flat ball trajectory)',
    'tennis_atp_cincinnati':          '🏟️ CINCINNATI OPEN — Surface: HARD/OUTDOOR (medium-fast, Wimbledon tuneup for US Open, balanced play)',
    'tennis_wta_cincinnati':          '🏟️ CINCINNATI OPEN — Surface: HARD/OUTDOOR (medium-fast, pre-US-Open form guide)',
    'tennis_atp_canada_masters':      '🏟️ CANADIAN OPEN — Surface: HARD/OUTDOOR (medium-fast, alternates Montreal/Toronto, physical conditions)',
    'tennis_wta_canada_masters':      '🏟️ CANADIAN OPEN — Surface: HARD/OUTDOOR',
    'tennis_atp_dubai':               '🏟️ DUBAI DUTY FREE — Surface: HARD/OUTDOOR (fast, low humidity, serve advantage, Middle East desert conditions)',
    'tennis_atp_doha':                '🏟️ QATAR OPEN (Doha) — Surface: HARD/OUTDOOR (fast, indoor-like conditions, low bounce)',
    'tennis_atp_rotterdam':           '🏟️ ROTTERDAM — Surface: HARD/INDOOR (fast indoor, big servers dominate, short points)',
    'tennis_atp_marseille':           '🏟️ MARSEILLE — Surface: HARD/INDOOR (fast, big serve advantage)',
    'tennis_atp_vienna':              '🏟️ VIENNA — Surface: HARD/INDOOR (medium-fast indoor, baseline favored)',
    'tennis_atp_paris_masters':       '🏟️ PARIS MASTERS — Surface: HARD/INDOOR (fast, big servers thrive, year-end fatigue factor)',
    'tennis_wta_paris':               '🏟️ PARIS — Surface: HARD/INDOOR (fast indoor, aggressive baseliners favored)',
    'tennis_atp_stockholm':           '🏟️ STOCKHOLM — Surface: HARD/INDOOR',
    'tennis_atp_gijon':               '🏟️ GIJON — Surface: HARD/INDOOR',
    'tennis_atp_lyon':                '🏟️ LYON — Surface: CLAY (pre-Roland Garros clay)',
    'tennis_wta_lyon':                '🏟️ LYON — Surface: CLAY',
    'tennis_atp_geneva':              '🏟️ GENEVA — Surface: CLAY (pre-Roland Garros clay, high altitude, heavy ball)',
    'tennis_wta_geneva':              '🏟️ GENEVA — Surface: CLAY',
    'tennis_atp_estoril':             '🏟️ ESTORIL — Surface: CLAY',
    'tennis_atp_munich':              '🏟️ MUNICH — Surface: CLAY',
    'tennis_atp_bucharest':           '🏟️ BUCHAREST — Surface: CLAY',
    'tennis_atp_marrakech':           '🏟️ MARRAKECH — Surface: CLAY (very slow, physical grinders rewarded)',
    'tennis_atp_gstaad':              '🏟️ GSTAAD — Surface: CLAY (high altitude clay, heavy conditions)',
    'tennis_atp_umag':                '🏟️ UMAG — Surface: CLAY',
    'tennis_atp_kitzbuhel':           '🏟️ KITZBUHEL — Surface: CLAY',
  };
  // Fallback: derive surface from sport key pattern if not in map
  const getTennisSurface = (key: string): string => {
    if (TENNIS_SURFACE[key]) return TENNIS_SURFACE[key];
    const k = key.toLowerCase();
    const name = key.replace(/^tennis_(atp|wta)_/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    if (/french|roland|madrid|barcelona|monte.?carlo|clay|rome|italian|hamburg|lyon|geneva|estoril|munich|bucharest|marrakech|gstaad|umag|kitzbuhel|houston|bogota/.test(k))
      return `🏟️ ${name} — Surface: CLAY (topspin-dominant, baseline grinders excel, big servers fade)`;
    if (/wimbledon|queens|halle|eastbourne|birmingham|grass/.test(k))
      return `🏟️ ${name} — Surface: GRASS (fastest, serve+volley, big servers dominate)`;
    if (/indoor|rotterdam|marseille|vienna|paris|stockholm|sofia|gijon|montpellier/.test(k))
      return `🏟️ ${name} — Surface: HARD/INDOOR (fast, big servers favored, short points)`;
    return `🏟️ ${name} — Surface: HARD/OUTDOOR (medium-fast, balanced baseline/serve play)`;
  };

  const results: string[] = [];

  for (const key of sportKeys) {
    try {
      const events = await fetchRawOdds(key);
      if (!events.length) continue;

      // Inject tennis surface header before listing events for this tournament
      if (sport.toUpperCase() === 'TENNIS') results.push(getTennisSurface(key));

      // Filter by game query if provided
      const filtered = gameQuery
        ? events.filter(e =>
            e.home_team.toLowerCase().includes(gameQuery.toLowerCase()) ||
            e.away_team.toLowerCase().includes(gameQuery.toLowerCase()) ||
            gameQuery.toLowerCase().split(/\s+vs?\s+/i).some(t =>
              e.home_team.toLowerCase().includes(t.trim()) ||
              e.away_team.toLowerCase().includes(t.trim())
            )
          )
        : events.slice(0, 8); // max 8 games to keep prompt lean

      for (const ev of filtered) {
        const gameTime = new Date(ev.commence_time).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' });
        const pinnacle = ev.bookmakers.find(b => b.key === 'pinnacle') || ev.bookmakers[0];
        if (!pinnacle) continue;

        const lines: string[] = [`${ev.away_team} @ ${ev.home_team} — ${gameTime} ET`];

        for (const market of pinnacle.markets) {
          if (market.key === 'h2h') {
            const [o1, o2] = market.outcomes;
            const ml = market.outcomes.map(o => `${o.name} ML ${o.price > 0 ? '+' : ''}${o.price}`).join(' | ');
            lines.push(`  Moneyline: ${ml}`);
            // Implied probability + devig math embedded inline
            if (o1 && o2) {
              const p1r = impliedProb(o1.price), p2r = impliedProb(o2.price);
              const dv  = devig(p1r, p2r);
              lines.push(`  → Implied(devigged): ${o1.name} ${(dv.p1*100).toFixed(1)}% | ${o2.name} ${(dv.p2*100).toFixed(1)}% | Book vig: ${dv.vig.toFixed(1)}%`);
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
          }
        }
        results.push(lines.join('\n'));
      }
    } catch { /* skip failed sport key */ }
  }

  if (results.length === 0) return `No live odds available for ${sport} right now.`;
  return `LIVE ODDS (Pinnacle/DraftKings) — ${sport}:\n${results.join('\n\n')}`;
}

// ── NBA Player Stats — ESPN box score (free, no key needed) ──────────────────
// Uses ESPN game summary box score. Works for games in-progress AND final.
// For pre-game (Scheduled) → returns "" → hard gate in alpha sheet returns [].

type ESPNEvent = {
  id: string; name: string;
  status: { type: { description: string; completed: boolean } };
  competitions: Array<{ competitors: Array<{ homeAway: string; team: { displayName: string; abbreviation: string } }> }>;
};

async function fetchNBAEventsToday(league: 'nba' | 'wnba' = 'nba'): Promise<ESPNEvent[]> {
  try {
    const res = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/basketball/${league}/scoreboard`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return [];
    const data = await res.json() as { events?: ESPNEvent[] };
    return data.events ?? [];
  } catch { return []; }
}

// Real player stats from ESPN box score for a specific matchup
async function fetchNBAPlayerStats(matchup: string, league: 'nba' | 'wnba' = 'nba'): Promise<string> {
  try {
    const events = await fetchNBAEventsToday(league);
    const keywords = matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim());

    const event = events.find(e =>
      e.competitions[0]?.competitors.some(c =>
        keywords.some(kw =>
          c.team.displayName.toLowerCase().includes(kw) ||
          c.team.abbreviation.toLowerCase().includes(kw)
        )
      )
    );
    if (!event) return "";

    const status = event.status.type.description;
    // Only return stats if the game has real box score data (In Progress or Final)
    if (status === 'Scheduled') return "";

    const sumRes = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=${event.id}`,
      { signal: AbortSignal.timeout(6000) }
    );
    if (!sumRes.ok) return "";
    const sumData = await sumRes.json() as {
      boxscore?: {
        players?: Array<{
          team: { displayName: string };
          statistics: Array<{
            names: string[];
            athletes: Array<{ athlete: { displayName: string }; stats: string[]; starter?: boolean }>;
          }>;
        }>;
      };
    };

    const playersSection = sumData.boxscore?.players;
    if (!playersSection?.length) return "";

    const blocks: string[] = [];
    for (const teamData of playersSection) {
      const statGroup = teamData.statistics[0];
      if (!statGroup) continue;
      const h = statGroup.names;
      const ptsI = h.indexOf('PTS');
      const rebI = h.indexOf('REB');
      const astI = h.indexOf('AST');
      const minI = h.indexOf('MIN');
      const stlI = h.indexOf('STL');
      const blkI = h.indexOf('BLK');
      const fgI  = h.indexOf('FG');

      const athletes = statGroup.athletes.filter(a => {
        const min = parseFloat(a.stats[minI] ?? '0');
        return min >= 5;
      });
      athletes.sort((a, b) => parseInt(b.stats[ptsI] ?? '0') - parseInt(a.stats[ptsI] ?? '0'));

      const lines = [`${teamData.team.displayName.toUpperCase()} (${status}):`];
      for (const ath of athletes.slice(0, 7)) {
        const pts = ath.stats[ptsI] ?? '0';
        const reb = ath.stats[rebI] ?? '0';
        const ast = ath.stats[astI] ?? '0';
        const stl = stlI >= 0 ? (ath.stats[stlI] ?? '0') : '0';
        const blk = blkI >= 0 ? (ath.stats[blkI] ?? '0') : '0';
        const fg  = fgI  >= 0 ? (ath.stats[fgI]  ?? '') : '';
        const min = ath.stats[minI] ?? '?';
        lines.push(
          `  ${ath.athlete.displayName}: ${pts}pts ${reb}reb ${ast}ast ${stl}stl ${blk}blk` +
          `${fg ? ` ${fg}FG` : ''} (${min}min)`
        );
      }
      if (lines.length > 1) blocks.push(lines.join('\n'));
    }

    if (!blocks.length) return "";
    return `${league.toUpperCase()} PLAYER STATS (ESPN box score — ${status}):\n${blocks.join('\n\n')}`;
  } catch { return ""; }
}

async function fetchNBAScheduleToday(league: 'nba' | 'wnba' = 'nba'): Promise<string> {
  try {
    const events = await fetchNBAEventsToday(league);
    if (!events.length) return "";
    const label = league.toUpperCase();
    return `${label} TODAY: ${events.map(e => {
      const comps = e.competitions[0]?.competitors ?? [];
      const away = comps.find(c => c.homeAway === 'away')?.team.displayName ?? '?';
      const home = comps.find(c => c.homeAway === 'home')?.team.displayName ?? '?';
      return `${away} @ ${home} (${e.status.type.description})`;
    }).join(' | ')}`;
  } catch { return ""; }
}

// ── ESPN Playoff Series Score (NBA playoffs — series record + last game result) ─
async function fetchNBASeriesContext(matchup: string): Promise<string> {
  try {
    const res = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=${new Date(Date.now()-30*86400000).toISOString().slice(0,10).replace(/-/g,'')}-${new Date().toISOString().slice(0,10).replace(/-/g,'')}`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!res.ok) return "";
    const data = await res.json() as {
      events?: Array<{
        name: string;
        competitions?: Array<{
          series?: { type?: string; title?: string };
          competitors: Array<{ team: { displayName: string }; score: string; winner?: boolean }>;
          status?: { type?: { completed?: boolean } };
        }>;
      }>;
    };
    const keywords = matchup.toLowerCase().split(/\s+vs?\.?\s+/i).map(t => t.trim());
    const relevant = (data.events ?? []).filter(ev =>
      keywords.some(kw => ev.name.toLowerCase().includes(kw))
    );
    if (!relevant.length) return "";
    const results: string[] = ["NBA PLAYOFF SERIES CONTEXT (ESPN):"];
    for (const ev of relevant.slice(-5)) {
      const comp = ev.competitions?.[0];
      if (!comp?.status?.type?.completed) continue;
      const [h, a] = comp.competitors;
      if (!h || !a) continue;
      const winner = comp.competitors.find(c => c.winner);
      results.push(`  ${a.team.displayName} ${a.score} @ ${h.team.displayName} ${h.score}${winner ? ` — ${winner.team.displayName} WIN` : ''}`);
    }
    return results.length > 1 ? results.join('\n') : "";
  } catch { return ""; }
}

// ── ESPN Injury Feed (free, no key required) ──────────────────────────────────
const ESPN_INJURY_ROUTES: Record<string, string> = {
  NBA:    "basketball/nba",
  WNBA:   "basketball/wnba",
  NFL:    "football/nfl",
  MLB:    "baseball/mlb",
  NHL:    "hockey/nhl",
  SOCCER: "soccer/usa.1",
  UFC:    "mma/ufc",
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
  MLB:    'baseball/mlb',
  NFL:    'football/nfl',
  NHL:    'hockey/nhl',
  WNBA:   'basketball/wnba',
  SOCCER: 'soccer/usa.1',
  TENNIS: 'tennis/atp',
  UFC:    'mma/ufc',
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
// League avg OffRtg/DefRtg balance at ~114.5 for 2025-26 (update each season).
const NBA_LEAGUE_AVG_RTG = 114.5;

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

const ESPN_WNBA_TEAM_IDS: Record<string, number> = {
  "atlanta dream": 1, "dream": 1,
  "chicago sky": 2, "sky": 2,
  "connecticut sun": 3, "sun": 3,
  "dallas wings": 4, "wings": 4,
  "indiana fever": 5, "fever": 5,
  "las vegas aces": 6, "aces": 6,
  "los angeles sparks": 7, "sparks": 7,
  "minnesota lynx": 8, "lynx": 8,
  "new york liberty": 9, "liberty": 9,
  "phoenix mercury": 10, "mercury": 10,
  "seattle storm": 11, "storm": 11,
  "washington mystics": 12, "mystics": 12,
};

async function fetchNBATeamStats(matchup: string, league: 'nba' | 'wnba' = 'nba'): Promise<string> {
  if (!matchup) return "";
  const lower = matchup.toLowerCase();
  const idMap = league === 'wnba' ? ESPN_WNBA_TEAM_IDS : ESPN_NBA_TEAM_IDS;
  const STAT_KEYS = ['avgPoints','fieldGoalPct','threePointPct','avgRebounds','avgAssists','avgTurnovers','avgBlocks','avgSteals'];
  const STAT_LABELS: Record<string,string> = {
    avgPoints:'PPG', fieldGoalPct:'FG%', threePointPct:'3P%',
    avgRebounds:'REB', avgAssists:'AST', avgTurnovers:'TO',
    avgBlocks:'BLK', avgSteals:'STL',
  };

  const extractTeamId = (part: string): number | null => {
    for (const [key, id] of Object.entries(idMap)) {
      if (part.includes(key)) return id;
    }
    return null;
  };

  // Try to split matchup into two team names
  const parts = lower.split(/\s+(?:vs\.?|@|-)\s+/);
  const ids = parts.map(extractTeamId).filter((id): id is number => id !== null);
  if (ids.length === 0) return "";

  const leagueLabel = league.toUpperCase();
  const lines: string[] = [`${leagueLabel} TEAM STATS (ESPN — real numbers, cite these):`];
  await Promise.all(ids.slice(0, 2).map(async (teamId) => {
    try {
      const res = await fetch(
        `https://site.api.espn.com/apis/site/v2/sports/basketball/${league}/teams/${teamId}/statistics`,
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
          const logs = (ld.stats?.[0]?.splits ?? []).slice(-3).reverse();
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

// ── MLB Batter Stats (MLB Stats API — free, no key) ──────────────────────────
// Returns top 5 hitters per team by OPS for today's game matchup
const MLB_TEAM_IDS: Record<string, number> = {
  'arizona diamondbacks':109,'arizona':109,'diamondbacks':109,'d-backs':109,
  'atlanta braves':144,'atlanta':144,'braves':144,
  'baltimore orioles':110,'baltimore':110,'orioles':110,
  'boston red sox':111,'boston':111,'red sox':111,
  'chicago cubs':112,'cubs':112,
  'chicago white sox':145,'white sox':145,
  'cincinnati reds':113,'cincinnati':113,'reds':113,
  'cleveland guardians':114,'cleveland':114,'guardians':114,
  'colorado rockies':115,'colorado':115,'rockies':115,
  'detroit tigers':116,'detroit':116,'tigers':116,
  'houston astros':117,'houston':117,'astros':117,
  'kansas city royals':118,'kansas city':118,'royals':118,
  'los angeles angels':108,'angels':108,'la angels':108,
  'los angeles dodgers':119,'dodgers':119,'la dodgers':119,
  'miami marlins':146,'miami':146,'marlins':146,
  'milwaukee brewers':158,'milwaukee':158,'brewers':158,
  'minnesota twins':142,'minnesota':142,'twins':142,
  'new york mets':121,'mets':121,
  'new york yankees':147,'yankees':147,
  'oakland athletics':133,'athletics':133,'a\'s':133,
  'philadelphia phillies':143,'philadelphia':143,'phillies':143,
  'pittsburgh pirates':134,'pittsburgh':134,'pirates':134,
  'san diego padres':135,'san diego':135,'padres':135,
  'san francisco giants':137,'san francisco':137,'giants':137,
  'seattle mariners':136,'seattle':136,'mariners':136,
  'st. louis cardinals':138,'st louis':138,'cardinals':138,
  'tampa bay rays':139,'tampa bay':139,'rays':139,
  'texas rangers':140,'texas':140,'rangers':140,
  'toronto blue jays':141,'toronto':141,'blue jays':141,
  'washington nationals':120,'washington':120,'nationals':120,
};

function resolveMLBTeamId(name: string): number | null {
  const k = name.toLowerCase().trim();
  if (MLB_TEAM_IDS[k]) return MLB_TEAM_IDS[k];
  for (const [alias, id] of Object.entries(MLB_TEAM_IDS)) {
    if (k.includes(alias) || alias.includes(k)) return id;
  }
  return null;
}

async function fetchMLBBatterStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const parts = matchup.split(/\s+(?:vs\.?|@|-)\s+/i).map(p => p.trim()).filter(Boolean);
  if (parts.length < 2) return "";

  const season = new Date().getFullYear();

  const fetchTeamBatters = async (teamName: string): Promise<string> => {
    const id = resolveMLBTeamId(teamName);
    if (!id) return "";
    try {
      const res = await fetch(
        `https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&season=${season}&teamId=${id}&sportId=1&gameType=R&limit=40`,
        { signal: AbortSignal.timeout(6000) }
      );
      if (!res.ok) return "";
      const data = await res.json() as {
        stats: Array<{ splits: Array<{ player?: { fullName: string }; stat: { atBats?: number; avg?: string; homeRuns?: number; rbi?: number; ops?: string; strikeOuts?: number } }> }>
      };
      const splits = data.stats?.[0]?.splits ?? [];
      const hitters = splits
        .filter(s => s.player && (s.stat.atBats ?? 0) >= 50)
        .map(s => ({
          name: s.player!.fullName,
          ab: s.stat.atBats ?? 0,
          avg: s.stat.avg ?? '.000',
          hr: s.stat.homeRuns ?? 0,
          rbi: s.stat.rbi ?? 0,
          ops: parseFloat(s.stat.ops ?? '0'),
          k: s.stat.strikeOuts ?? 0,
        }))
        .sort((a, b) => b.ops - a.ops)
        .slice(0, 5);
      if (!hitters.length) return "";
      const rows = hitters.map(h =>
        `    ${h.name}: .${h.avg.replace('.','').padEnd(3,'0')} AVG | ${h.hr}HR | ${h.rbi}RBI | ${h.ops.toFixed(3)} OPS | ${h.k}K`
      );
      return `  ${teamName.toUpperCase()} TOP BATS:\n${rows.join('\n')}`;
    } catch { return ""; }
  };

  const results = await Promise.all(parts.map(fetchTeamBatters));
  const valid = results.filter(Boolean);
  if (!valid.length) return "";
  return `MLB BATTER STATS — Top 5 by OPS (MLB API — real data, cite exactly):\n${valid.join('\n')}`;
}

// ── Weather via wttr.in (completely free, no auth) ────────────────────────────
// Only called for outdoor sports: MLB, NFL. Indoor (NBA/NHL) = skip.
const STADIUM_CITIES_MLB: Record<string, string> = {
  'yankees': 'New York', 'mets': 'New York', 'red sox': 'Boston',
  'cubs': 'Chicago', 'white sox': 'Chicago', 'dodgers': 'Los Angeles',
  'angels': 'Anaheim', 'giants': 'San Francisco', 'athletics': 'West Sacramento',
  'padres': 'San Diego', 'rockies': 'Denver', 'diamondbacks': 'Phoenix',
  'cardinals': 'St. Louis', 'brewers': 'Milwaukee', 'reds': 'Cincinnati',
  'pirates': 'Pittsburgh', 'phillies': 'Philadelphia', 'braves': 'Cumberland',
  'marlins': 'Miami', 'nationals': 'Washington', 'orioles': 'Baltimore',
  'blue jays': 'Toronto', 'rays': 'St. Petersburg', 'tigers': 'Detroit',
  'guardians': 'Cleveland', 'royals': 'Kansas City', 'twins': 'Minneapolis',
  'astros': 'Houston', 'rangers': 'Arlington', 'mariners': 'Seattle',
};
const STADIUM_CITIES_NFL: Record<string, string> = {
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

// MLB teams with domed or retractable-roof stadiums — weather irrelevant
const MLB_DOME_TEAMS = new Set(['rays','blue jays','astros','marlins','mariners','diamondbacks','brewers']);

async function fetchWeather(matchup: string, sport: string): Promise<string> {
  const s = sport.toUpperCase();
  if (!['MLB', 'NFL'].includes(s)) return ""; // NBA/NHL/Tennis are indoor

  // Extract home team (right side of "vs")
  const parts = matchup.toLowerCase().split(/\s+vs?\.?\s+/i);
  const homeStr = (parts[parts.length - 1] ?? parts[0]).trim();

  // Skip weather for domed/retractable MLB stadiums
  if (s === 'MLB' && [...MLB_DOME_TEAMS].some(t => homeStr.includes(t))) return "";

  const cityMap = s === 'MLB' ? STADIUM_CITIES_MLB : STADIUM_CITIES_NFL;
  let city = '';
  for (const [kw, c] of Object.entries(cityMap)) {
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

// ── Soccer context — ESPN standings (W/D/L, GF, GA, GD, PPG) ─────────────────
// Tries EPL, La Liga, MLS, Champions League in parallel; returns matched teams.
const SOCCER_LEAGUE_ROUTES: Record<string, string> = {
  EPL: 'eng.1', 'LA LIGA': 'esp.1', MLS: 'usa.1', UCL: 'uefa.champions',
  BUNDESLIGA: 'ger.1', 'SERIE A': 'ita.1', 'LIGUE 1': 'fra.1',
};

async function fetchSoccerContext(matchup: string): Promise<string> {
  if (!matchup) return "";
  const parts = matchup.toLowerCase().split(/\s+(?:vs\.?|@|-)\s+/).map(p => p.trim());
  if (parts.length < 2) return "";

  type StandingsEntry = { name: string; w: number; d: number; l: number; gf: number; ga: number; pts: number; gp: number };

  const fetchLeague = async (route: string): Promise<StandingsEntry[]> => {
    try {
      const res = await fetch(
        `https://site.api.espn.com/apis/v2/sports/soccer/${route}/standings`,
        { signal: AbortSignal.timeout(5000) }
      );
      if (!res.ok) return [];
      const data = await res.json() as {
        children?: Array<{ standings?: { entries?: Array<{ team: { displayName: string }; stats: Array<{ name: string; value: number }> }> } }>;
      };
      const results: StandingsEntry[] = [];
      for (const group of data.children ?? []) {
        for (const entry of group.standings?.entries ?? []) {
          const st: Record<string, number> = {};
          for (const s of entry.stats) st[s.name] = s.value;
          results.push({
            name: entry.team.displayName.toLowerCase(),
            w: st['wins'] ?? 0, d: st['ties'] ?? 0, l: st['losses'] ?? 0,
            gf: st['pointsFor'] ?? 0, ga: st['pointsAgainst'] ?? 0,
            pts: st['points'] ?? 0, gp: st['gamesPlayed'] ?? 1,
          });
        }
      }
      return results;
    } catch { return []; }
  };

  // Fetch all leagues in parallel, flatten
  const allEntries = (await Promise.all(Object.values(SOCCER_LEAGUE_ROUTES).map(fetchLeague))).flat();
  if (allEntries.length === 0) return "";

  const findTeam = (query: string): StandingsEntry | undefined =>
    allEntries.find(e => e.name.includes(query) || query.split(' ').some(w => w.length > 3 && e.name.includes(w)));

  const teams = parts.map(findTeam).filter((t): t is StandingsEntry => t !== undefined);
  if (teams.length === 0) return "";

  const lines = ["SOCCER STANDINGS (ESPN — real data, cite exactly):"];
  for (const t of teams) {
    const ppg = t.gp > 0 ? (t.pts / t.gp).toFixed(2) : '?';
    const gd  = t.gf - t.ga;
    lines.push(`  ${t.name.toUpperCase()}: ${t.w}W-${t.d}D-${t.l}L | GF:${t.gf} GA:${t.ga} GD:${gd >= 0 ? '+' : ''}${gd} | PPG:${ppg}`);
  }
  // Add recent form: last 5 results — fetch teams list once, then schedules in parallel
  try {
    const teamsRes = await fetch(
      `https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams`,
      { signal: AbortSignal.timeout(4000) }
    );
    if (teamsRes.ok) {
      const rd = await teamsRes.json() as { sports?: Array<{ leagues?: Array<{ teams?: Array<{ team: { displayName: string; id: string } }> }> }> };
      const allTeams = (rd.sports?.[0]?.leagues ?? []).flatMap(l => l.teams ?? []);
      await Promise.all(teams.map(async t => {
        // Score each ESPN team by how many words from t.name it contains — pick best match
        const tWords = t.name.split(' ').filter(w => w.length > 2);
        const score = (dn: string) => tWords.filter(w => dn.toLowerCase().includes(w)).length;
        const ranked = allTeams
          .map(e => ({ e, s: score(e.team.displayName) }))
          .filter(x => x.s > 0)
          .sort((a, b) => b.s - a.s);
        const match = ranked[0]?.e;
        if (!match) return;
        const schedRes = await fetch(
          `https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/${match.team.id}/schedule`,
          { signal: AbortSignal.timeout(4000) }
        ).catch(() => null);
        if (!schedRes?.ok) return;
        const sd = await schedRes.json() as { events?: Array<{ competitions?: Array<{ competitors: Array<{ team: { displayName: string }; score: string; winner: boolean }> }> }> };
        const results: string[] = [];
        for (const ev of (sd.events ?? []).slice(-5)) {
          const comp = ev.competitions?.[0];
          if (!comp) continue;
          const [h, a] = comp.competitors;
          if (!h || !a) continue;
          const won = comp.competitors.find(c =>
            tWords.some(w => c.team.displayName.toLowerCase().includes(w))
          )?.winner;
          results.push(`${won === true ? 'W' : won === false ? 'L' : 'D'} ${h.score}-${a.score}`);
        }
        if (results.length) lines.push(`  ${t.name.toUpperCase()} LAST 5: ${results.join(' ')}`);
      }));
    }
  } catch { /* form is bonus data, ignore errors */ }

  return lines.join('\n');
}

// ── Tennis context — ATP rankings + recent results via ESPN ──────────────────
async function fetchTennisContext(matchup: string): Promise<string> {
  if (!matchup) return "";
  const parts = matchup.split(/\s+(?:vs\.?|-)\s+/i).map(p => p.trim());
  if (parts.length < 2) return "";
  const lines = ["TENNIS PLAYER CONTEXT (ESPN):"];
  try {
    const rankRes = await fetch(
      'https://site.api.espn.com/apis/site/v2/sports/tennis/atp/rankings?limit=200',
      { signal: AbortSignal.timeout(5000) }
    );
    if (rankRes.ok) {
      const rd = await rankRes.json() as { rankings?: Array<{ athlete: { displayName: string }; rankFrom: number; current: number }> };
      for (const name of parts) {
        const found = (rd.rankings ?? []).find(r => r.athlete.displayName.toLowerCase().includes(name.toLowerCase()));
        if (found) lines.push(`  ${found.athlete.displayName}: ATP Rank #${found.current} (was #${found.rankFrom})`);
      }
    }
    // WTA fallback for women's tennis
    if (lines.length < 3) {
      const wtaRes = await fetch(
        'https://site.api.espn.com/apis/site/v2/sports/tennis/wta/rankings?limit=200',
        { signal: AbortSignal.timeout(5000) }
      );
      if (wtaRes.ok) {
        const wd = await wtaRes.json() as { rankings?: Array<{ athlete: { displayName: string }; current: number }> };
        for (const name of parts) {
          const found = (wd.rankings ?? []).find(r => r.athlete.displayName.toLowerCase().includes(name.toLowerCase()));
          if (found) lines.push(`  ${found.athlete.displayName}: WTA Rank #${found.current}`);
        }
      }
    }
  } catch { /* bonus data */ }
  if (lines.length === 1) return "";
  return lines.join('\n');
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
  zandvoort:    { name:'Circuit Zandvoort',              type:'Technical', qualifyingWeight:0.88, overtaking:'Extreme',  dnfRate:'~8%',  safetyCar:'Moderate',     notes:'Banking turns + no DRS zones make overtaking nearly impossible. Qualifying result extremely predictive. Behaves like a street circuit.' },
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

// ── F1 Live Context (Jolpica/Ergast — free, no key) ──────────────────────────
async function fetchF1LiveContext(matchup: string): Promise<string> {
  try {
    const [driversRes, constructorsRes, qualRes] = await Promise.all([
      fetch('https://api.jolpi.ca/ergast/f1/current/driverStandings.json', { signal: AbortSignal.timeout(5000) }),
      fetch(`https://api.jolpi.ca/ergast/f1/${new Date().getFullYear()}/constructorStandings.json`, { signal: AbortSignal.timeout(5000) }),
      fetch('https://api.jolpi.ca/ergast/f1/current/last/qualifying.json', { signal: AbortSignal.timeout(5000) }),
    ]);

    const lines: string[] = ['F1 LIVE STANDINGS (Jolpica/Ergast — real data, cite exactly):'];

    if (driversRes.ok) {
      const d = await driversRes.json() as { MRData: { StandingsTable: { StandingsLists: Array<{ DriverStandings: Array<{ position: string; points: string; wins: string; Driver: { familyName: string; givenName: string }; Constructors: Array<{ name: string }> }> }> } } };
      const standings = d.MRData.StandingsTable.StandingsLists[0]?.DriverStandings ?? [];
      lines.push('  Driver Championship (Top 8):');
      for (const s of standings.slice(0, 8)) {
        lines.push(`    P${s.position}: ${s.Driver.givenName} ${s.Driver.familyName} (${s.Constructors[0]?.name ?? '?'}) — ${s.points}pts, ${s.wins}W`);
      }
    }

    if (constructorsRes.ok) {
      const d = await constructorsRes.json() as { MRData: { StandingsTable: { StandingsLists: Array<{ ConstructorStandings: Array<{ position: string; points: string; wins: string; Constructor: { name: string } }> }> } } };
      const standings = d.MRData.StandingsTable.StandingsLists[0]?.ConstructorStandings ?? [];
      lines.push('  Constructor Championship (Top 5):');
      for (const s of standings.slice(0, 5)) {
        lines.push(`    P${s.position}: ${s.Constructor.name} — ${s.points}pts, ${s.wins}W`);
      }
    }

    if (qualRes.ok) {
      const d = await qualRes.json() as { MRData: { RaceTable: { Races: Array<{ raceName: string; QualifyingResults: Array<{ position: string; Driver: { familyName: string; givenName: string }; Constructor: { name: string }; Q3?: string; Q2?: string; Q1?: string }> }> } } };
      const race = d.MRData.RaceTable.Races[0];
      if (race) {
        lines.push(`  Last Qualifying: ${race.raceName}`);
        for (const q of race.QualifyingResults.slice(0, 5)) {
          const best = q.Q3 ?? q.Q2 ?? q.Q1 ?? '?';
          lines.push(`    P${q.position}: ${q.Driver.givenName} ${q.Driver.familyName} (${q.Constructor.name}) ${best}`);
        }
      }
    }

    const circuitCtx = getF1CircuitContext(matchup);
    if (circuitCtx) lines.push('', circuitCtx);

    return lines.join('\n');
  } catch { return getF1CircuitContext(matchup); }
}

// ── UFC Fighter Stats (ufcstats.com — free scrape) ────────────────────────────
async function fetchUFCFighterStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const parts = matchup.split(/\s+(?:vs\.?|@|-)\s+/i).map(p => p.trim()).filter(Boolean);
  if (parts.length < 2) return "";

  const scrapeStats = async (name: string): Promise<string | null> => {
    try {
      const encoded = encodeURIComponent(name.trim().toLowerCase().replace(/\s+/g, '+'));
      const res = await fetch(
        `http://ufcstats.com/statistics/fighters?search=${encoded}&action=search`,
        { signal: AbortSignal.timeout(6000), headers: { 'User-Agent': 'Mozilla/5.0' } }
      );
      if (!res.ok) return null;
      const html = await res.text();
      const rowMatch = html.match(/<tr class="b-statistics__table-row"[^>]*>\s*([\s\S]*?)<\/tr>/);
      if (!rowMatch) return null;
      const cells = [...rowMatch[1].matchAll(/<td[^>]*>\s*<a[^>]*>([^<]*)<\/a>\s*<\/td>|<td[^>]*>\s*([^<\s][^<]*?)\s*<\/td>/g)]
        .map(m => (m[1] ?? m[2] ?? '').trim())
        .filter(Boolean);
      if (cells.length < 6) return null;
      const stanceIdx = cells.findIndex(c => /^(Orthodox|Southpaw|Switch|Open)/i.test(c));
      if (stanceIdx < 0) return null;
      const height = cells[stanceIdx - 3] ?? '?';
      const weight = cells[stanceIdx - 2] ?? '?';
      const reach  = cells[stanceIdx - 1] ?? '?';
      const stance = cells[stanceIdx];
      const wins   = cells[stanceIdx + 1] ?? '?';
      const losses = cells[stanceIdx + 2] ?? '?';
      const draws  = cells[stanceIdx + 3] ?? '0';
      return `${name.toUpperCase()}: ${wins}W-${losses}L-${draws}D | ${height} ${weight} | Reach:${reach} | ${stance}`;
    } catch { return null; }
  };

  const results = await Promise.all(parts.map(scrapeStats));
  const valid = results.filter(Boolean) as string[];
  if (valid.length === 0) return "";

  return ['UFC FIGHTER STATS (ufcstats.com — real data, cite exactly):', ...valid.map(r => `  ${r}`)].join('\n');
}

// ── NFL Team Stats (ESPN — free, no key) ─────────────────────────────────────
const NFL_TEAM_IDS: Record<string, number> = {
  'arizona cardinals':22,'atlanta falcons':1,'baltimore ravens':33,'buffalo bills':2,
  'carolina panthers':29,'chicago bears':3,'cincinnati bengals':4,'cleveland browns':5,
  'dallas cowboys':6,'denver broncos':7,'detroit lions':8,'green bay packers':9,
  'houston texans':34,'indianapolis colts':11,'jacksonville jaguars':30,'kansas city chiefs':12,
  'las vegas raiders':13,'los angeles chargers':24,'los angeles rams':14,'miami dolphins':15,
  'minnesota vikings':16,'new england patriots':17,'new orleans saints':18,'new york giants':19,
  'new york jets':20,'philadelphia eagles':21,'pittsburgh steelers':23,'san francisco 49ers':25,
  'seattle seahawks':26,'tampa bay buccaneers':27,'tennessee titans':10,'washington commanders':28,
  'cardinals':22,'falcons':1,'ravens':33,'bills':2,'panthers':29,'bears':3,'bengals':4,
  'browns':5,'cowboys':6,'broncos':7,'lions':8,'packers':9,'texans':34,'colts':11,
  'jaguars':30,'jags':30,'chiefs':12,'raiders':13,'chargers':24,'rams':14,'dolphins':15,
  'vikings':16,'patriots':17,'saints':18,'giants':19,'jets':20,'eagles':21,'steelers':23,
  '49ers':25,'niners':25,'seahawks':26,'buccaneers':27,'bucs':27,'titans':10,'commanders':28,
};

function resolveNFLTeamId(name: string): number | null {
  const k = name.toLowerCase().trim();
  if (NFL_TEAM_IDS[k]) return NFL_TEAM_IDS[k];
  for (const [alias, id] of Object.entries(NFL_TEAM_IDS)) {
    if (k.includes(alias) || alias.includes(k)) return id;
  }
  return null;
}

async function fetchNFLTeamStats(matchup: string): Promise<string> {
  if (!matchup) return "";
  const parts = matchup.split(/\s+(?:vs\.?|@|-)\s+/i).map(p => p.trim()).filter(Boolean);
  if (parts.length < 2) return "";

  const fetchTeam = async (name: string): Promise<string | null> => {
    const id = resolveNFLTeamId(name);
    if (!id) return null;
    try {
      const res = await fetch(
        `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/${id}/statistics`,
        { signal: AbortSignal.timeout(5000) }
      );
      if (!res.ok) return null;
      const data = await res.json() as { results: { categories: Array<{ name: string; stats: Array<{ name: string; value: number; displayValue: string }> }> } };
      const cats: Record<string, Record<string, string>> = {};
      for (const cat of data.results?.categories ?? []) {
        cats[cat.name] = {};
        for (const s of cat.stats) cats[cat.name][s.name] = s.displayValue;
      }
      const pts    = cats['scoring']?.['totalPoints'] ?? '?';
      const ptsPa  = cats['scoring']?.['totalPointsAgainst'] ?? '?';
      const compPct = cats['passing']?.['completionPct'] ?? '?';
      const passYpg = cats['passing']?.['yardsPerGame'] ?? '?';
      const rushYpg = cats['rushing']?.['yardsPerGame'] ?? '?';
      return `${name.toUpperCase()}: PTS:${pts} PA:${ptsPa} | Pass:${passYpg}ypg (${compPct}%) | Rush:${rushYpg}ypg`;
    } catch { return null; }
  };

  const results = await Promise.all(parts.map(fetchTeam));
  const valid = results.filter(Boolean) as string[];
  if (valid.length === 0) return "";

  return ['NFL TEAM STATS (ESPN — real data, cite exactly):', ...valid.map(r => `  ${r}`)].join('\n');
}

// ── Synthetic Sharp Signal (Pinnacle vs soft-book line gap) ───────────────────
// Pinnacle is the sharpest book. When Pinnacle line diverges from DraftKings/FanDuel,
// that gap reveals where the sharp money is pointing.
async function fetchSharpSignals(sport: string): Promise<string> {
  if (!ODDS_API_KEY) return "";
  const sportKeys = SPORT_KEYS[sport.toUpperCase()] || [];
  if (sportKeys.length === 0) return "";
  const signals: string[] = [];
  try {
    const events = await fetchRawOdds(sportKeys[0]);
    for (const ev of events.slice(0, 6)) {
      const pinnacle = ev.bookmakers.find(b => b.key === "pinnacle");
      const dk = ev.bookmakers.find(b => b.key === "draftkings");
      if (!pinnacle || !dk) continue;
      for (const market of pinnacle.markets) {
        const dkMarket = dk.markets.find(m => m.key === market.key);
        if (!dkMarket) continue;
        for (const pinOut of market.outcomes) {
          const dkOut = dkMarket.outcomes.find(o => o.name === pinOut.name);
          if (!dkOut) continue;
          const diff = pinOut.price - dkOut.price;
          // If Pinnacle is >8 pts BETTER than DK on one side = sharp action on that side
          if (Math.abs(diff) >= 8) {
            const direction = diff > 0 ? "SHARP BACKING" : "SHARP FADING";
            signals.push(`${ev.away_team} @ ${ev.home_team} | ${market.key.toUpperCase()} ${pinOut.name}: Pinnacle ${pinOut.price > 0 ? "+" : ""}${pinOut.price} vs DK ${dkOut.price > 0 ? "+" : ""}${dkOut.price} → ${direction} ${pinOut.name} (${diff > 0 ? "+" : ""}${diff} pts gap)`);
          }
        }
      }
    }
  } catch { return ""; }
  if (signals.length === 0) return "";
  return `SYNTHETIC SHARP SIGNALS (Pinnacle vs DraftKings gap ≥8pts):\n${signals.join("\n")}`;
}

// ── MYTHOS-STYLE IDENTITY BLOCK (Capybara tier adapted for sports betting) ────
// Borrowed from FTGMYTHOS/mythos-router: structured IDENTITY + CORE DIRECTIVES
// forces disciplined, non-hallucinated output — same principle as SWD for files
function getSharpIdentity(): string {
  const mw = MODEL_WEIGHTS.math_weight * 100;
  const sw = MODEL_WEIGHTS.sentiment_weight * 100;
  const dt = MODEL_WEIGHTS.dissonance_threshold;
  return `## IDENTITY
Tier: SHARP (CTE LOCKS Engine — Specialized in Sports Betting & EV Analysis)
Protocol: Strict Odds Discipline (SOD)
Constraint: NEVER invent odds, lines, or player stats. If not in LIVE ODDS block → UNKNOWN.

## CORE DIRECTIVES
1. STRICT ODDS DISCIPLINE: Only use lines from the LIVE ODDS block. Never hallucinate prices.
2. INJURY FIRST: If a key player is OUT/DOUBTFUL in the INJURY REPORT, reprice the line mentally before picking.
3. SHARP SIGNALS: Pinnacle vs DK gap ≥8pts = real sharp money. Follow it.
4. EV BEFORE NARRATIVE: If a bet feels right but EV is negative → FADE IT.
5. CAVEMAN OUTPUT: "why" fields max 12 words. Cite numbers. No fluff.
6. RAW JSON ONLY: Never wrap in markdown. No commentary outside the JSON.
7. SIGNAL WEIGHTING: Weight MATHEMATICAL/STATISTICAL signals at ${mw}% and narrative/sentiment at ${sw}%. Math wins every tie.
8. DISSONANCE FLAG: If your margin model and market line disagree by >${dt} pts → label [HIGH-EDGE] and explain.`;
}
const SHARP_IDENTITY = getSharpIdentity;

// ── Claude (Anthropic) helper with DeepSeek fallback (Mythos multi-provider) ──
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const DEEPSEEK_KEY = process.env.DEEPSEEK_API_KEY || "";

async function ask(prompt: string, model = "claude-3-5-sonnet-20241022"): Promise<string> {
  return await router.ask(prompt, { model });
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
    const sportFilter = sport ? `Focus ONLY on ${sport} games.` : 'Scan all sports (NBA, MLB, tennis, soccer, UFC — whatever is on tonight).';
    const prophetSport = sport || 'ALL';
    const heuristics = getBettingHeuristics(prophetSport === 'ALL' ? 'NBA' : prophetSport);
    const activeSport = prophetSport === 'ALL' ? 'NBA' : prophetSport;
    const [liveOdds, scheduleCtx, injuryData, newsData, pitcherData, advancedData, sharpSignals] = await Promise.all([
      fetchLiveOdds(activeSport),
      activeSport === 'NBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(activeSport),
      fetchInjuries(activeSport),
      fetchESPNNews(activeSport),
      activeSport === 'MLB' ? fetchMLBPitcherStats('') : Promise.resolve(''),
      activeSport === 'NBA' ? fetchNBALeagueSnapshot() : Promise.resolve(''),
      fetchSharpSignals(activeSport),
    ]);

    // ── Pull model predictions for each game in the odds block ──────────────
    const parsedGame = parseOddsForTeams(liveOdds);
    const modelCtx = parsedGame
      ? await fetchEdgeModel(activeSport, parsedGame.home, parsedGame.away,
          parsedGame.spread, parsedGame.homeOdds, parsedGame.awayOdds)
      : '';

    const prompt = `
${SHARP_IDENTITY()}

You are a sharp professional sports bettor. Today is ${today} (Eastern Time). ${sportFilter}
Math weight: ${MODEL_WEIGHTS.math_weight * 100}% | Sentiment weight: ${MODEL_WEIGHTS.sentiment_weight * 100}%

${heuristics}

${liveOdds}
${scheduleCtx ? `\n${scheduleCtx}` : ''}
${advancedData ? `\n${advancedData}` : ''}
${injuryData ? `\nINJURY REPORT (ESPN — LIVE):\n${injuryData}` : ''}
${pitcherData ? `\nREAL PITCHER STATS (MLB API — cite exact numbers):\n${pitcherData}` : ''}
${newsData ? `\nLATEST NEWS (ESPN):\n${newsData}` : ''}
${sharpSignals ? `\n${sharpSignals}` : ''}
${modelCtx ? `\n${modelCtx}` : ''}

RANKING RULES — pick the bet with the highest combination of:
1. POSITIVE EV (model EV% > 0 beats any narrative)
2. Cover probability > 54% from the model
3. Edge strength: STRONG > MODERATE > WEAK > NO_EDGE
4. Sharp signal confirmation (Pinnacle vs DK gap ≥ 8pts)
5. Injury-adjusted — if key player out, apply Next Man Up

IMPORTANT: Lines are REAL Pinnacle/DraftKings. Model predictions above are XGBoost trained on real historical games.
If model says HOME_COVER [STRONG] → that is your primary anchor. Override only if injury changes everything.
⚠️ Never output win_prob > 0.82. EV in output: cite exact model number.

Output ONLY raw JSON:
{
  "selection": "e.g. Celtics -4.5 or Over 224.5",
  "odds": "e.g. -115",
  "game_name": "Team A vs Team B — League — Tonight TIME ET",
  "value_gap": "+X.X% EV (model)",
  "win_prob": 0.57,
  "recommended_unit": "1 UNIT or 2 UNITS",
  "logic_bullets": [
    "Model: predicted margin +X.X vs spread Y — edge +Z.X pts [STRONG/MODERATE]",
    "Stat or situational edge with exact numbers",
    "Sharp signal or injury context"
  ],
  "correlated_insight": "SGP or same-game parlay suggestion if this bet wins"
}
`.trim();

    const prophetCacheKey = `prophet:${prophetSport}`;
    const prophetCached = getCached(prophetCacheKey);
    if (prophetCached) { res.json(prophetCached); return; }

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object') {
      return res.status(500).json({ error: "PARSE_FAILED", message: "AI returned invalid data. Try again." });
    }
    const result = { ...parsed, hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase() };
    setCache(prophetCacheKey, result);
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

    const [swarmLiveOdds, swarmNbaCtx, swarmInjuries, swarmSharp] = await Promise.all([
      fetchLiveOdds(league, matchup),
      league === 'NBA' || league === 'WNBA' ? fetchNBAPlayerStats(matchup, league === 'WNBA' ? 'wnba' : 'nba') : fetchESPNScoreboard(league),
      fetchInjuries(league, matchup),
      fetchSharpSignals(league),
    ]);

    // Parse teams — prefer odds string (Away @ Home) for correct home/away assignment
    const oddsGame  = parseOddsForTeams(swarmLiveOdds);
    const teamsMatch = matchup.match(/^(.+?)\s*(?:vs\.?|-)\s*(.+)$/i);
    const homeTeam = oddsGame?.home ?? (teamsMatch ? teamsMatch[2].trim() : matchup);
    const awayTeam  = oddsGame?.away ?? (teamsMatch ? teamsMatch[1].trim() : '');
    const modelCtx  = awayTeam
      ? await fetchEdgeModel(league, homeTeam, awayTeam,
          oddsGame?.spread ?? 0, oddsGame?.homeOdds ?? -110, oddsGame?.awayOdds ?? -110)
      : '';

    const liveOddsBlock = [
      swarmLiveOdds ? `\nLIVE ODDS (use exact lines):\n${swarmLiveOdds}` : '',
      swarmNbaCtx   ? `\n${swarmNbaCtx}` : '',
      swarmInjuries ? `\n${swarmInjuries}` : '',
      swarmSharp    ? `\n${swarmSharp}` : '',
      modelCtx      ? `\n${modelCtx}` : '',
    ].filter(Boolean).join('\n');

    const unifiedPrompt = `
${SHARP_IDENTITY()}
You are a sharp sports betting analyst. Today is ${today}.
Analyze: ${matchup} (${league})

${liveOddsBlock}
${swarmHeuristics}

RANKING PRIORITY: 1) Highest positive EV from model  2) Cover prob > 54%  3) Edge strength STRONG/MODERATE  4) Sharp signal  5) Injury-adjusted.
Model EV and cover probability above are XGBoost outputs — treat as primary quantitative signal.

Produce THREE perspectives then synthesize. Output ONLY raw JSON:
{
  "quant": {
    "primary_single": "Best bet pure EV angle — cite model edge + cover prob",
    "value_gap": "+X.X% EV (model)",
    "confidence_score": 0.75,
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "cite stat/model number", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "cite stat/model number", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "cite stat/model number", "espn_id": "" }
    ],
    "omni_report": "2 sentences — cite model predicted margin, cover %, EV."
  },
  "simulation": {
    "primary_single": "Best bet situational angle — cite injury, rest, game-script",
    "value_gap": "+X.X% EV",
    "confidence_score": 0.70,
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" }
    ],
    "omni_report": "2 sentences situational view — cite fatigue, contrarian, or injury."
  },
  "primary_single": "FINAL pick — highest EV + model confirmation (specific line + odds)",
  "value_gap": "Final EV — cite model number",
  "confidence_score": 0.80,
  "sgp_blueprint": [
    { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "Why", "espn_id": "" },
    { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "Why", "espn_id": "" },
    { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "Why", "espn_id": "" }
  ],
  "omni_report": "2-sentence verdict citing model edge, cover prob, conviction level, and biggest risk."
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

    const exec = unified as SwarmAgentData;
    const payload: SwarmFinalPayload = {
      ...exec,
      swarm_report: {
        quant: unified.quant as SwarmAgentData,
        simulation: unified.simulation as SwarmAgentData,
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
// ALPHA SHEETS — today's top props cheat sheet (real data only, no hallucination)
// ─────────────────────────────────────────────────────────────────────────────

// Extract matchup strings from live odds context (pattern: "Away @ Home —")
function parseMatchupsFromOdds(oddsCtx: string): string[] {
  // Match "Team Name @ Other Team —" per line (no newlines, digits allowed for 76ers etc.)
  const matches = [...oddsCtx.matchAll(/([A-Z][a-zA-Z0-9 '\.]+?)\s+@\s+([A-Z][a-zA-Z0-9 '\.]+?)\s+[—–-]/g)];
  return matches.map(m => `${m[1].trim()} vs ${m[2].trim()}`);
}

export async function generateAlphaSheet(sport: string): Promise<AlphaSheetContainer> {
  const today = todayStr();
  const s = sport.toUpperCase();

  // ── Step 1: Fetch real data before calling Claude ────────────────────────
  const [oddsCtx, scheduleCtx] = await Promise.all([
    fetchLiveOdds(s).catch(() => ''),
    fetchESPNScoreboard(s).catch(() => ''),
  ]);

  // ── Step 2: Fetch player/pitcher stats for today's games ─────────────────
  let playerCtx = '';
  let pitcherCtx = '';
  let batterCtx  = '';
  // Parse matchups from both odds AND ESPN schedule (handle whichever has data)
  const gameMatchups = parseMatchupsFromOdds(`${oddsCtx}\n${scheduleCtx}`).slice(0, 6);

  if ((s === 'NBA' || s === 'WNBA') && gameMatchups.length) {
    const blocks = await Promise.all(gameMatchups.map(g => fetchNBAPlayerStats(g).catch(() => '')));
    playerCtx = blocks.filter(Boolean).join('\n\n');
  }
  if (s === 'MLB' && gameMatchups.length) {
    const [pitcherBlocks, batterBlocks] = await Promise.all([
      Promise.all(gameMatchups.map(g => fetchMLBPitcherStats(g).catch(() => ''))),
      Promise.all(gameMatchups.map(g => fetchMLBBatterStats(g).catch(() => ''))),
    ]);
    pitcherCtx = pitcherBlocks.filter(Boolean).join('\n\n');
    batterCtx  = batterBlocks.filter(Boolean).join('\n\n');
  }

  const hasGames = !!(oddsCtx || scheduleCtx);
  const hasPlayerData = !!(playerCtx || pitcherCtx || batterCtx);

  // Hard gate: no real data = no Claude call = no hallucinations
  const titles: Record<string, string> = {
    NBA: "NBA PROP HEATBOARD", MLB: "DINGER & STRIKEOUT SHEET",
    NFL: "NFL PROP SHEET", NHL: "PUCK LINE PROPS",
    TENNIS: "TENNIS EDGE SHEET", SOCCER: "SOCCER PROP SHEET",
    WNBA: "WNBA PROP SHEET", UFC: "UFC FIGHT SHEET", F1: "F1 RACE SHEET",
  };
  const emptyResult = {
    title: titles[s] || `${s} PROP SHEET`,
    subtitle: `@cavemanlocks AI Edge — ${today}`,
    data: [] as AlphaSheetItem[],
    timestamp: new Date().toLocaleDateString(),
  };

  // Sports where we have real player-level stat APIs — require data before calling Claude
  // (without it, Claude hallucinates player names/lines from memory)
  const requiresPlayerData = ['NBA','WNBA','MLB','NFL','NHL'];
  if (requiresPlayerData.includes(s) && !hasPlayerData) return emptyResult;
  // For remaining sports (F1/UFC/Soccer/Tennis): require at minimum a game list from odds
  if (!oddsCtx && !hasPlayerData) return emptyResult;

  const prompt = `
You are a sharp sports betting analyst building a ${s} prop cheat sheet.
Today is ${today}.

⛔ ABSOLUTE RULES — VIOLATION = FAILURE:
1. ONLY pick players from the REAL PLAYER DATA block below. If a player's name does not appear in that block, they are BANNED.
2. ONLY reference games from the REAL GAMES TODAY block below. If a game does not appear there, it does not exist today.
3. If REAL PLAYER DATA is empty → return [] immediately. Do NOT generate props from memory.
4. Never invent prop lines. Anchor lines to the real season averages in the data block.
5. espn_id: always "" — never invent IDs.

REAL GAMES TODAY (ONLY pick from these):
${oddsCtx || scheduleCtx || '⛔ NO GAMES FOUND — return empty array []'}

${playerCtx ? `REAL PLAYER STATS (ESPN box score — cite exactly):\n${playerCtx}` : ''}
${pitcherCtx ? `REAL PITCHER STATS (MLB API — cite exactly):\n${pitcherCtx}` : ''}
${batterCtx ? `REAL BATTER STATS (MLB API — cite exactly):\n${batterCtx}` : ''}
${!hasPlayerData && s !== 'NFL' && s !== 'F1' && s !== 'UFC' ? '⛔ NO PLAYER DATA AVAILABLE — return empty array []' : ''}

${hasPlayerData ? `
PROP GENERATION RULES BY SPORT:
- NBA/WNBA: Points (anchor to PPG ±1.5), Rebounds (anchor to RPG ±0.5), Assists (anchor to APG ±0.5). Only players with ≥15 PPG, ≥7 RPG, or ≥6 APG qualify.
- MLB batters: Hits prop = anchor line to (BA × 3.8 AB average), round to nearest 0.5. HR props for sluggers (≥15 HR pace). RBI for middle of order.
- MLB pitchers: Strikeout prop = anchor to (K/9 ÷ 9 × expected IP 5.5). Only for starters listed in pitcher block.
- ai_score: 7-8 = solid edge backed by real mismatch; 6 = marginal; 9+ = extremely rare, only if clear mispricing.
- status_color: #22c55e if ai_score ≥ 7.5, #eab308 if 6.5-7.4, #f97316 if < 6.5` : ''}

Output ONLY a raw JSON array (up to 10 objects, fewer if data is limited). If no qualifying players exist, return []:
[
  {
    "rank": 1,
    "team_logo": "${s === 'NBA' ? 'e.g. BOS' : s === 'MLB' ? 'e.g. NYY' : s}",
    "player_name": "Exact name from REAL PLAYER DATA block",
    "metric_label": "e.g. POINTS PROP or STRIKEOUTS",
    "metric_value": "e.g. Over 27.5 -115 (anchored to 28.2 PPG season avg)",
    "season_stat": "e.g. 28.2 PPG | L5: 29,31,26,28,27",
    "ai_score": 7.4,
    "status_color": "#22c55e",
    "espn_id": ""
  }
]`.trim();

  const raw = await ask(prompt);
  const data = (parseJSON(raw) as AlphaSheetItem[]) ?? [];

  return {
    title: titles[s] || `${s} PROP SHEET`,
    subtitle: `@cavemanlocks AI Edge — ${today}`,
    data: Array.isArray(data) ? data : [],
    timestamp: new Date().toLocaleDateString(),
  };
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
export interface ParlayLeg {
  pick: string;
  odds: string;
  why: string;
  game?: string;
}

export interface ParlayBlock {
  legs: ParlayLeg[];
  combined_odds: string;
  why: string;
  ev: string;
  game?: string; // SGP only
}

export interface ParlaysPayload {
  sport: string;
  best_pick: {
    selection: string;
    odds: string;
    why: string;
    ev: string;
    units: string;
    game: string;
  };
  sgp: ParlayBlock;
  multi_parlay: ParlayBlock;
  ev_parlay: ParlayBlock;
  correlation_parlay: ParlayBlock;
  hash: string;
  timestamp: string;
}

app.get('/api/parlays', async (req: express.Request, res: express.Response) => {
  if (rateLimit(req, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const game = (req.query.game as string || '').trim();
    const today = todayStr();
    const isAllSports = sport === 'ALL';

    // For cross-sport: fetch NBA + MLB + NFL + SOCCER + WNBA odds in parallel
    // Only fetch sports currently in-season — saves Odds API credits (Fix #4)
    const month = new Date().getMonth() + 1; // 1-12
    const inSeason = (s: string) => {
      if (s === 'NBA')    return month >= 10 || month <= 6;
      if (s === 'WNBA')   return month >= 5 && month <= 9;
      if (s === 'MLB')    return month >= 4 && month <= 10;
      if (s === 'NFL')    return month >= 9 || month <= 2;
      if (s === 'NHL')    return month >= 10 || month <= 6;
      if (s === 'SOCCER') return true; // always some league running
      if (s === 'TENNIS') return true;
      return false;
    };
    const crossSportKeys = ['NBA', 'WNBA', 'MLB', 'NFL', 'NHL', 'SOCCER'].filter(inSeason);
    const sgpSport = isAllSports ? 'NBA' : sport;
    const [parlayOdds, crossOdds, parlayNba, parlayInjuries, parlaySharp] = await Promise.all([
      fetchLiveOdds(sgpSport, game || undefined),
      isAllSports
        ? Promise.all(crossSportKeys.map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n'))
        : Promise.all(crossSportKeys.filter(s => s !== sport).map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n')),
      isAllSports ? fetchNBAScheduleToday() : sport === 'NBA' ? fetchNBAScheduleToday('nba') : sport === 'WNBA' ? fetchNBAScheduleToday('wnba') : fetchESPNScoreboard(sport),
      fetchInjuries(sgpSport, game || undefined),
      fetchSharpSignals(sgpSport),
    ]);

    const sgpHeuristics = getBettingHeuristics(sgpSport);
    const sgpBetCtx = getSportBetContext(sgpSport);

    // Inject quantitative model — prefer odds string for correct home/away assignment
    const prlOddsGame = parseOddsForTeams(parlayOdds);
    const prlTeams = game ? game.match(/^(.+?)\s*(?:vs\.?|-)\s*(.+)$/i) : null;
    const prlHome = prlOddsGame?.home ?? (prlTeams ? prlTeams[2].trim() : '');
    const prlAway = prlOddsGame?.away ?? (prlTeams ? prlTeams[1].trim() : '');
    const prlModelCtx = prlHome && prlAway
      ? await fetchEdgeModel(sgpSport, prlHome, prlAway,
          prlOddsGame?.spread ?? 0, prlOddsGame?.homeOdds ?? -110, prlOddsGame?.awayOdds ?? -110)
      : '';

    const gameContext = game
      ? `SPECIFIC GAME TO AUDIT: "${game}". SGP and correlation parlay must be from this exact game. Multi-game and EV parlays can include this game as the anchor with 1-2 other real games tonight from ANY sport.`
      : isAllSports
        ? `Scan ALL sports tonight (NBA, WNBA, MLB, NFL, SOCCER). Pick the single best opportunity from any sport.`
        : `Generate the best betting opportunities across TODAY's ${sport} slate.`;

    const parlayOddsBlock = `
LIVE ODDS — PRIMARY SPORT (${sgpSport}):
${parlayOdds}
${parlayNba}
${parlayInjuries ? `\n${parlayInjuries}` : ''}
${parlaySharp ? `\n${parlaySharp}` : ''}
${prlModelCtx ? `\n${prlModelCtx}` : ''}

LIVE ODDS — CROSS-SPORT (for multi-parlay & EV stack legs, mix freely):
${crossOdds}
`;

    const prompt = `
You are a sharp professional sports bettor. Today is ${today}.

${sgpHeuristics}
${parlayOddsBlock}
${gameContext}

Apply all heuristics above to every leg. Use the INJURY REPORT — if a key player is OUT or DOUBTFUL, apply Next Man Up logic (backup's props are often highest EV). Use the SHARP SIGNALS — follow the Pinnacle-vs-DK gap where sharp money is detected. Run the SHARP CHECK. Flag [HIGH-RISK] legs. Apply the JUICE FILTER (reject if cumulative vig >15%). For SGP: run CORRELATION STRESS TEST on every leg pair.

CRITICAL RULES FOR EACH PARLAY TYPE:
- best_pick: Best single bet from ANY sport available tonight
- sgp (Same-Game Parlay): ALL legs MUST be from ONE single game in ${sgpSport}. Apply ${sgpBetCtx}
- multi_parlay: Legs from DIFFERENT games — can mix NBA, MLB, NFL, SOCCER. Pick 3-4 best cross-sport legs tonight
- ev_parlay: ONLY legs with >4% EV individually. Can be from ANY sport. Mix sports for max edge
- correlation_parlay: Legs that POSITIVELY correlate — team score high + player Over props, or same-game correlated outcomes. Use ${sgpSport} for strongest correlation

Output ONLY a raw JSON object with this exact structure:
{
  "best_pick": {
    "selection": "e.g. LeBron James Over 25.5 Points or Lakers -4.5",
    "odds": "-115",
    "why": "short caveman reason — 1 sentence, specific numbers",
    "ev": "+6.2%",
    "units": "2 UNITS",
    "game": "Team A vs Team B — TIME ET"
  },
  "sgp": {
    "game": "${game || `Best ${sgpSport} game on slate`} — TIME ET",
    "legs": [
      { "pick": "Player X Over 24.5 Points", "odds": "-115", "why": "caveman why" },
      { "pick": "Player X Over 5.5 Assists", "odds": "-110", "why": "caveman why" },
      { "pick": "Team A -3.5", "odds": "-110", "why": "caveman why" }
    ],
    "combined_odds": "+285",
    "why": "1 sentence: why these legs correlate in same game",
    "ev": "+8.1%"
  },
  "multi_parlay": {
    "legs": [
      { "game": "NBA: Team A vs Team B — TIME ET", "pick": "Team A ML", "odds": "-130", "why": "caveman why" },
      { "game": "MLB: Team C vs Team D — TIME ET", "pick": "Team C F5 -1.5", "odds": "+110", "why": "caveman why" },
      { "game": "NFL: Team E vs Team F — TIME ET", "pick": "Total Under 44.5", "odds": "-110", "why": "caveman why" }
    ],
    "combined_odds": "+480",
    "why": "1 sentence: why these cross-sport picks stack well tonight",
    "ev": "+6.8%"
  },
  "ev_parlay": {
    "legs": [
      { "game": "SPORT: Game 1 — TIME ET", "pick": "Pick with highest EV from any sport", "odds": "+140", "why": "caveman why: line mispriced" },
      { "game": "SPORT: Game 2 — TIME ET", "pick": "Pick with high EV", "odds": "-105", "why": "caveman why" },
      { "game": "SPORT: Game 3 — TIME ET", "pick": "Pick with high EV", "odds": "-108", "why": "caveman why" }
    ],
    "combined_odds": "+380",
    "why": "All legs >4% EV individually. Best value across ALL sports tonight.",
    "ev": "+14.2%"
  },
  "correlation_parlay": {
    "legs": [
      { "game": "${game || `${sgpSport} target game`} — TIME ET", "pick": "Team scores high / wins big", "odds": "-120", "why": "fast pace" },
      { "game": "Same game", "pick": "Star player Over points", "odds": "-115", "why": "star needs big game to win" },
      { "game": "Same or linked game", "pick": "Correlated total or prop", "odds": "-110", "why": "legs move together" }
    ],
    "combined_odds": "+320",
    "why": "1 sentence: how these legs correlate positively",
    "ev": "+9.5%"
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

    const payload: ParlaysPayload = {
      ...parsed,
      sport,
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
      timestamp: new Date().toLocaleTimeString()
    };

    setCache(parlayCacheKey, payload);
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
      if (s === 'MLB')    return month >= 4 && month <= 10;
      if (s === 'NFL')    return month >= 9 || month <= 2;
      if (s === 'NHL')    return month >= 10 || month <= 6;
      if (s === 'SOCCER') return true;
      return false;
    };
    const crossSports = ['NBA', 'MLB', 'NFL', 'NHL', 'SOCCER', 'WNBA'].filter(inSeason);

    // Fetch all data in parallel — real stats, news, odds, injuries, sharp signals
    const [oddsCtx, injuryCtx, playerStatsCtx, advancedCtx, teamStatsCtx, nicheCtx, newsCtx, pitcherCtx, batterCtx, weatherCtx, sharpCtx, crossOdds] = await Promise.all([
      fetchLiveOdds(league, matchup),
      fetchInjuries(league, matchup),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBAPlayerStats(matchup, league === 'WNBA' ? 'wnba' : 'nba')
        : Promise.resolve(''),
      league === 'NBA'
        ? fetchNBAAdvancedStats(matchup)
        : Promise.resolve(''),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBATeamStats(matchup, league === 'WNBA' ? 'wnba' : 'nba')
        : Promise.resolve(''),
      // Sport-specific niche stats
      league === 'NHL'    ? fetchNHLTeamStats(matchup) :
      league === 'SOCCER' ? fetchSoccerContext(matchup) :
      league === 'TENNIS' ? fetchTennisContext(matchup) :
      league === 'F1'     ? fetchF1LiveContext(matchup) :
      league === 'UFC'    ? fetchUFCFighterStats(matchup) :
      league === 'NFL'    ? fetchNFLTeamStats(matchup) :
      Promise.resolve(''),
      fetchESPNNews(league, matchup),
      league === 'MLB' ? fetchMLBPitcherStats(matchup) : Promise.resolve(''),
      league === 'MLB' ? fetchMLBBatterStats(matchup)  : Promise.resolve(''),
      fetchWeather(matchup, league),
      fetchSharpSignals(league),
      Promise.all(crossSports.filter(s => s !== league).map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n')),
    ]);

    // Playoff series context for NBA (non-blocking, runs after main parallel fetch)
    const seriesCtx = league === 'NBA' ? await fetchNBASeriesContext(matchup) : '';

    const heuristics = getBettingHeuristics(league);

    // Inject quantitative model — prefer odds string for home/away (Away @ Home is correct order)
    const fbOddsGame = parseOddsForTeams(oddsCtx);
    const fbTeams = matchup.match(/^(.+?)\s*(?:vs\.?|-)\s*(.+)$/i);
    const fbHome = fbOddsGame?.home ?? (fbTeams ? fbTeams[2].trim() : matchup);
    const fbAway = fbOddsGame?.away ?? (fbTeams ? fbTeams[1].trim() : '');
    const fbModelCtx = fbAway
      ? await fetchEdgeModel(league, fbHome, fbAway,
          fbOddsGame?.spread ?? 0, fbOddsGame?.homeOdds ?? -110, fbOddsGame?.awayOdds ?? -110)
      : '';

    const gamePrompt = `
${SHARP_IDENTITY()}

You are a sharp sports betting analyst. Today is ${today}.
Game: ${matchup} (${league})

${heuristics}

LIVE ODDS FOR THIS GAME (USE THESE EXACT LINES — do not invent odds):
${oddsCtx || "No live odds found — note this clearly in your output, do not fabricate lines."}

INJURY REPORT (ONLY reference players listed here — do NOT invent injuries):
${injuryCtx || "No injury data available from ESPN right now. Do NOT fabricate any injuries."}

${advancedCtx ? `${advancedCtx}\n` : ''}
${nicheCtx ? `SPORT-SPECIFIC NICHE DATA (cite these exact numbers, do NOT invent):\n${nicheCtx}\n` : ''}
${playerStatsCtx ? `REAL PLAYER STATS — ESPN box score (cite these exact numbers, do NOT invent):\n${playerStatsCtx}\n` : ''}
${teamStatsCtx ? `REAL TEAM STATS — ESPN API (cite these exact numbers, do NOT invent):\n${teamStatsCtx}\n` : ''}
${pitcherCtx ? `REAL PITCHER STATS — MLB Official API (cite these exact numbers, do NOT invent):\n${pitcherCtx}\n` : ''}
${batterCtx ? `REAL BATTER STATS — MLB Official API (cite these exact numbers, do NOT invent):\n${batterCtx}\n` : ''}
${weatherCtx ? `WEATHER DATA — wttr.in real-time:\n${weatherCtx}\n` : ''}
${newsCtx ? `LATEST NEWS — ESPN live:\n${newsCtx}\n` : ''}
${seriesCtx ? `${seriesCtx}\n` : ''}
${fbModelCtx ? `${fbModelCtx}\n` : ''}
📐 MATH ENGINE — use these formulas when computing EV and Kelly in your rationale:
- Implied prob already devigged: see "→ Implied(devigged)" lines in LIVE ODDS above.
- EV = (your_win_prob × (decimal_odds − 1)) − (1 − your_win_prob)
  decimal_odds: americanOdds ≥ 0 → odds/100+1 | americanOdds < 0 → 100/|odds|+1
- Half-Kelly units = max(0, (b×p − (1−p)) / b / 2)  where b = decimal_odds − 1, p = win_prob
- Edge = your win_prob − devigged market probability. Positive edge = bet has value.
- Cite: "Model: 54.3% | Market(devigged): 51.8% | Edge: +2.5% | EV: +3.1% | Half-Kelly: 0.6u"
⚠️ If QUANTITATIVE MODEL block is present, your win_prob MUST align with the model within ±15%. Do not wildly deviate without explaining why.
SHARP SIGNALS (Pinnacle vs DK line gap — directional signal only):
${sharpCtx || "No significant line gap detected."}

⚠️ HONESTY RULES — NON-NEGOTIABLE:
- win_prob: your calibrated estimate based on available data. Do NOT output >0.82 — real sharp bettors rarely see edge that clean.
- EV: label as "est." — we have no true probability model. Only output EV if you can ground it in the real stats/odds above.
- If a stat block is missing (no player stats, no pitcher data), say so in game_summary. Do NOT invent replacement numbers.
- rationale must cite at least one real number from the data blocks above or from the live odds. No narrative-only rationale accepted.

⚠️ ANTI-HALLUCINATION RULES — MUST FOLLOW:
0. TOP_PROPS ABSOLUTE RULE:
   - NBA: top_props players MUST appear by exact full name in the REAL PLAYER STATS block (men's NBA players only). If block is empty → return "top_props": []. Never invent a player. Only use players averaging ≥15 PPG (or ≥7 RPG or ≥6 APG).
   - WNBA: top_props players MUST appear by exact full name in the REAL PLAYER STATS block (women's WNBA players only — do NOT use NBA player names). If block is empty → return "top_props": []. WNBA thresholds: ≥12 PPG (or ≥6 RPG or ≥5 APG). Never invent a player. Never mix NBA and WNBA players.
   - MLB: top_props must come from REAL BATTER STATS or REAL PITCHER STATS blocks only. Batter props: Hits Over/Under (anchor to .AVG × 4 AB ≈ expected hits), HR props, RBI props. Pitcher props: Strikeouts (anchor to K/9 × expected IP). Never invent a player not in those blocks.
   - NFL: top_props must be grounded in NFL TEAM STATS block. QB passing yards (anchor to passYpg), RB rush yards (anchor to rushYpg). If no player stats available → return "top_props": [].
   - ALL SPORTS: If no stats block available → "top_props": []. Period. No exceptions.
1. PLAYER STATS: If REAL PLAYER STATS block is present, cite exact numbers (PPG, L5 form). Never round or invent.
   ADVANCED STATS: If NBA ADVANCED STATS block is present, cite OffRtg/DefRtg/NetRtg/Pace. Use "Model Expected Total" to anchor total pick. Use "Model Win Prob" to anchor spread/ML win_prob.
   NOTE: WNBA does NOT have advanced stats (OffRtg/DefRtg model). Use team stats block instead.
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

📊 LINE SELECTION — IMPORTANT:
The LIVE ODDS block contains h2h (moneyline), spreads, and totals from Pinnacle and DraftKings.
For each pick, use the exact lines shown. Set "is_alt": false for all picks (no alt lines available on current feed).
- If Pinnacle and DraftKings show different lines, flag the gap (sharp vs public disparity).
- Never fabricate lines. If LIVE ODDS block is empty → label all odds as "est." and say so.

Analyze this specific game. win_prob = true win probability (0.50–0.95). Apply heuristics above to every pick.

For the SGP: pick 3 correlated legs from THIS game only. Legs must positively correlate.

Output ONLY raw JSON — no markdown:
{
  "game": "${matchup}",
  "game_summary": "2-3 sentences: key injuries (only from report above), pace, sharp signals, biggest edge",
  "spread_pick": { "pick": "Team -X.X or alt line", "odds": "-110", "win_prob": 0.68, "rationale": "2 sharp sentences citing real roster/matchup data", "niche_stat": "Specific ATS trend", "is_alt": false },
  "ml_pick": { "pick": "Team ML", "odds": "-180", "win_prob": 0.72, "rationale": "2 sharp sentences", "niche_stat": "Specific ML trend", "is_alt": false },
  "total_pick": { "pick": "Over/Under X.X or alt line", "odds": "-108", "win_prob": 0.64, "rationale": "2 sharp sentences", "niche_stat": "Specific pace/total trend", "is_alt": false },
  "top_props": [
    { "player": "EXACT name from REAL PLAYER STATS block — NO others allowed", "market": "Points", "pick": "Over X.X", "odds": "-115", "win_prob": 0.68, "rationale": "cite exact PPG from stats block", "niche_stat": "e.g. 24.6 PPG this season | L5: 26,22,28,25,24" },
    { "player": "EXACT name from REAL PLAYER STATS block only", "market": "Rebounds", "pick": "Over X.X", "odds": "-110", "win_prob": 0.64, "rationale": "cite exact RPG", "niche_stat": "Real RPG" },
    { "player": "EXACT name from REAL PLAYER STATS block only", "market": "Assists", "pick": "Over X.X", "odds": "-115", "win_prob": 0.62, "rationale": "cite exact APG", "niche_stat": "Real APG" },
    { "player": "EXACT name from REAL PLAYER STATS block only", "market": "Points", "pick": "Over X.X", "odds": "-110", "win_prob": 0.61, "rationale": "cite exact PPG", "niche_stat": "Real PPG" },
    { "player": "EXACT name from REAL PLAYER STATS block only", "market": "Threes", "pick": "Over X.X", "odds": "-115", "win_prob": 0.60, "rationale": "cite exact 3P%", "niche_stat": "Real 3P%" }
  ],
  "sgp": {
    "legs": [
      { "pick": "Team covers or wins", "odds": "-130", "why": "caveman reason max 10 words" },
      { "pick": "Player from REAL PLAYER STATS block Over X stat", "odds": "-115", "why": "caveman reason" },
      { "pick": "Correlated total or prop from this game", "odds": "-110", "why": "caveman reason" }
    ],
    "combined_odds": "+280",
    "why": "1 sentence: why these legs from THIS game correlate",
    "ev": "+9.5%"
  }
}`.trim();

    const dailyPrompt = `
You are a sharp professional sports bettor. Today is ${today}.

CROSS-SPORT ODDS TONIGHT (ONLY use games/lines listed below — do NOT invent games):
${crossOdds || "No cross-sport odds available right now."}

⚠️ STRICT RULE: Only pick from REAL games in the ODDS block above. If odds block is empty, return empty legs arrays. Do NOT fabricate game results, player props, or lines.

Task 1 — PICK OF THE DAY: Find the single best bet from the ODDS BLOCK above. Must be from a real listed game.

Task 2 — PARLAY OF THE DAY: Build the best 3-leg cross-sport parlay. Each leg must be from a DIFFERENT game in the odds block above.

Output ONLY raw JSON — no markdown:
{
  "pick_of_day": {
    "selection": "e.g. LeBron James Over 25.5 Points",
    "odds": "-115",
    "why": "1 sentence, specific numbers, caveman short",
    "ev": "+6.2%",
    "units": "2U",
    "game": "Team A vs Team B",
    "sport": "NBA"
  },
  "parlay_of_day": {
    "legs": [
      { "pick": "Team A ML", "odds": "-130", "why": "caveman why", "game": "NBA: Game 1" },
      { "pick": "Team B -1.5 F5", "odds": "+110", "why": "caveman why", "game": "MLB: Game 2" },
      { "pick": "Player Over X goals", "odds": "-115", "why": "caveman why", "game": "SOCCER: Game 3" }
    ],
    "combined_odds": "+480",
    "why": "1 sentence: why these cross-sport picks stack tonight",
    "ev": "+8.1%"
  }
}`.trim();

    const cacheKey = `fullbreakdown:${league}:${matchup.toLowerCase().replace(/\s+/g, '_')}`;
    const cached = getCached(cacheKey);
    // Don't serve cache if it was built with no real odds — stale est. data is worse than fresh
    const cachedHasRealOdds = cached && JSON.stringify(cached).includes('Pinnacle');
    if (cachedHasRealOdds) return res.json(cached);

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

    const payload = {
      ...game,
      pick_of_day: daily.pick_of_day,
      parlay_of_day: daily.parlay_of_day,
      hash: "FB_" + Math.random().toString(36).substring(7).toUpperCase(),
    };
    // 5-min TTL if no real odds; 20-min if odds loaded
    const hasRealOdds = oddsCtx.includes('Pinnacle');
    setCache(cacheKey, payload, hasRealOdds ? 20 * 60 * 1000 : 5 * 60 * 1000);
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
      sport === 'NBA' ? fetchNBAScheduleToday('nba') : sport === 'WNBA' ? fetchNBAScheduleToday('wnba') : fetchESPNScoreboard(sport),
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

Output ONLY this raw JSON:
{
  "sport": "${sport}",
  "steam_moves": [
    {
      "game": "Team A vs Team B — TIME ET",
      "bet": "Exact bet e.g. Celtics -4.5 or Ohtani Over 7.5 strikeouts",
      "opening_line": "e.g. -3 or -115",
      "current_line": "e.g. -4.5 or -130",
      "move": "e.g. 1.5 points or -15 cents",
      "direction": "STEAM",
      "why": "Sharp hammered this side. Line moved fast with low public %",
      "ev": "+5.2%"
    }
  ],
  "rlm": [
    {
      "game": "Team C vs Team D — TIME ET",
      "bet": "Exact bet",
      "opening_line": "opening",
      "current_line": "current",
      "move": "moved description",
      "direction": "RLM",
      "why": "68% of public on Team C but line moved to Team D. Sharps on opposite side.",
      "ev": "+6.1%"
    }
  ],
  "best_ev_plays": [
    {
      "game": "Game — TIME ET",
      "bet": "Best EV pick",
      "odds": "-110",
      "ev": "+7.3%",
      "why": "Specific reason with numbers why this is +EV"
    },
    {
      "game": "Game — TIME ET",
      "bet": "Second best EV pick",
      "odds": "+130",
      "ev": "+5.8%",
      "why": "Specific reason"
    },
    {
      "game": "Game — TIME ET",
      "bet": "Third best EV pick",
      "odds": "-105",
      "ev": "+4.4%",
      "why": "Specific reason"
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
const distPath = path.resolve(process.cwd(), 'dist');
app.use(express.static(distPath));
app.get('/{*splat}', (_req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(port, '0.0.0.0', () => {
  console.log(`🚀 CTE LOCKS Engine live → http://localhost:${port}`);
});
