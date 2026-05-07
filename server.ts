import express from 'express';
// @ts-expect-error - no types
import cors from 'cors';
import dotenv from 'dotenv';
import Anthropic from '@anthropic-ai/sdk';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '.env'), override: true });

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

// ── Response cache (30-min TTL) — Fix #1 ─────────────────────────────────────
const responseCache = new Map<string, { data: unknown; expires: number }>();
function getCached(key: string): unknown | null {
  const entry = responseCache.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expires) { responseCache.delete(key); return null; }
  return entry.data;
}
function setCache(key: string, data: unknown, ttlMs = 30 * 60 * 1000): void {
  // Evict oldest if cache grows too large
  if (responseCache.size > 200) {
    const oldest = [...responseCache.entries()].sort((a, b) => a[1].expires - b[1].expires)[0];
    if (oldest) responseCache.delete(oldest[0]);
  }
  responseCache.set(key, { data, expires: Date.now() + ttlMs });
}

// ── Dynamic Heuristic Framework ───────────────────────────────────────────────
function getBettingHeuristics(sport: string): string {
  const GLOBAL = `
GLOBAL HEURISTICS (apply to every pick):
1. EV OVER NARRATIVE: Never pick "who will win." Find where the bookmaker's implied probability is LOWER than the true statistical probability. That gap is the edge.
2. CORRELATION STRESS TEST (SGPs): Only pair legs with MATHEMATICAL multiplier effect. If Leg A hits, does it make Leg B statistically more likely — or just emotionally more likely? Reject emotional correlation.
3. JUICE FILTER: Reject any parlay where cumulative vig exceeds 15%.
4. CLV (CLOSING LINE VALUE): Evaluate whether the current line is better or worse than it was 4-8 hours ago. If line moved heavily toward a team, ask: "Is value still here or did sharps already close the window?" If line moves AGAINST your logic without obvious reason, flag as SHARP_OPPOSITION — possible injury news missed.
5. DERIVATIVE MARKET PIVOT: If the main market (game spread/total) looks efficient (heavy juice, sharp action already priced in), pivot to derivative markets. NBA: 1st quarter spread for fast-starters. NFL: team totals instead of game total. MLB: F5 line instead of full game. These are softer, less surveilled.
6. INJURY IMPACT QUANTIFIER: Missing player = structural team change. NBA: high-usage star out → analyze usage increase for backup → backup's Over props are often highest EV in the game. MLB: high-leverage reliever pitched 2 nights in a row → assume unavailable → lean Over on 7th-9th innings total.
7. CONTRARIAN FILTER: If >75% public betting volume is on one side but the line is NOT moving (or moving the opposite direction = RLM), flag as CONTRARIAN_SIGNAL. The underdog or Under usually holds statistical edge in public traps.
8. SHARP CHECK (final step before any output): (a) CLV Check: Is this line better than 4hrs ago? (b) Correlation: Is this SGP statistically grounded or "perfect world" logic? (c) Derivative: Is there a softer market with cleaner EV? (d) Fragility: If one player gets hurt/foul trouble early, does the whole thesis collapse? If yes, reduce unit size to 0.5u.
9. FLAG HIGH-RISK: If a bet violates any rule above, label it [HIGH-RISK] and provide a PIVOT that aligns with statistical reality.`.trim();

  const SPORT_RULES: Record<string, string> = {
    NBA: `
NBA HEURISTICS:
- BLOWOUT RISK: If spread >10 points, DISCOUNT "Over" on the star player's points prop. High-spread games = 4th quarter rest. Flag SGP that pairs team ML (heavy favorite) + star Over points.
- PACE VARIABLE: Only suggest "Over" game totals when BOTH teams rank Top-10 in pace. Check pace matchup. Slow-pace team vs fast-pace team = lean Under.
- B2B FATIGUE: On second night of back-to-back, weight Under on veteran star props regardless of opponent. Rest beats talent on night 2.
- SGP RULE: Prefer "Team Total Over" + "Lead Playmaker Assists Over" (not just points). Assists correlate to team pace/scoring more cleanly than points alone.
- KEY NUMBERS: Spread moves of 1-2 points matter. A team going from -9 to -11 shifts blowout probability significantly.`,

    MLB: `
MLB HEURISTICS:
- F5 PRIORITY: When an Ace starts, favor F5 (First 5 Innings) ML/spread over full-game. This removes bullpen variance — sharp plays on aces get killed by bad middle relief.
- PARK & WEATHER: Wind blowing OUT + temp >85°F = lean Over. Wind IN + cold = lean Under. Cite specific ballpark factors.
- UMPIRE BIAS: High K-rate umpire (tight zone) = lean Over on pitcher strikeouts, lean Under on game total hits. Flag if K-zone umpire assigned.
- SGP RULE: "Pitcher To Earn Win" + "Under Team Hits Allowed" — ace dominates = low hits = pitcher gets the win. Clean correlation.
- AVOID: Run lines in parlays. Low payout relative to blowout risk. NRFI is a sharp single bet, not a parlay leg.`,

    NFL: `
NFL HEURISTICS:
- KEY NUMBERS: Spreads at 3, 7, and 10 are sacred. A line moving from -2.5 to -3.5 is MASSIVE (covers the margin of a FG). From -4 to -5 is negligible. Weight accordingly.
- NEGATIVE VOLUME CORRELATION: NEVER pair "QB Over Passing Yards" with "RB Over Rushing Yards" in an SGP unless the RB is a heavy pass-catcher (50+ receptions). They compete for the same offensive reps.
- DEFENSIVE EPA: High-flying offense vs. high-pressure defense = lean Under on QB completion%. Evaluate EPA allowed vs EPA generated.
- SGP RULE: QB Over passing yards + WR1 Over receiving yards + team to win — clean correlation if pass-heavy team.
- WEATHER: Wind >15 mph = fade passing props, lean Under total.`,

    NHL: `
NHL HEURISTICS:
- GOALIE FIRST: The starting goalie is the single most important variable. A top-10 SV% goalie vs bottom-10 offense = lean Under and puck line.
- B2B: Teams on second game of B2B show -8% goals scored on average. Lean Under.
- POWER PLAY: Teams with top-5 PP% against teams with bottom-5 PK% = lean Over and anytime goal scorer on PP specialist.
- SGP RULE: Team puck line (-1.5) + Over team total goals — only valid if opposing team has bottom-10 defense.`,

    SOCCER: `
SOCCER HEURISTICS:
- ASIAN HANDICAP PRIORITY: Shift to Asian Handicaps (-0.25, +0.75) over 1X2. Splits the bet, eliminates the "draw kill" on moneyline. Primary edge vehicle.
- XG FRAUD DETECTION: Identify "Fraudulent Winners" — teams winning games they were out-produced in xG. Fade them next match. "Overperforming teams regress."
- CORNER VOLUME: Evaluate corners based on WING PLAY tactics, not score. High crossing teams (e.g., Man City, Porto) generate corners even when losing. Corners O/U is bookmaker-soft.
- SGP RULE: Result + Under/Over Cards based on the assigned referee's cards-per-game average. High card ref = Over cards + underdog +AH (tactical fouling).
- AVOID: Draws in parlays. Draw kill rate makes them parlay poison. Use double chance instead.`,

    TENNIS: `
TENNIS HEURISTICS:
- SURFACE SPECIALIZATION: Weight surface win% OVER total win%. A top-10 hardcourt player can be bottom-50 on grass. Always cite surface record, not just ranking.
- HOLD RATE STABILITY: Prioritize players with Hold% >80%. They are harder to break, providing spread safety. Low hold% players are volatile — avoid as heavy ML favorites.
- POST-TITLE HANGOVER: Fade players coming off a tournament WIN the previous week. Historically, post-title week shows elevated early-round upset rate (fatigue + motivation dip).
- PREFER GAME HANDICAPS: Use game handicap (+3.5/-3.5) over ML for top players vs. mid-tier opponents. Protects against tiebreak variance. Better EV structure.
- FATIGUE STACK: Players who played 3-set matches in previous rounds tire faster. Track match duration, not just W/L.`,

    UFC: `
UFC HEURISTICS:
- GRAPPLER VS STRIKER: When high-level wrestler faces pure striker, FAVOR wrestler ML or "Decision" props. Wrestling controls the clock, neutralizes striking.
- CAGE SIZE IMPACT: Small cage (UFC Apex) = higher finish rates (KO/Sub). Large cage (big arena) = more "Decision" and out-fighting style. Adjust method props.
- REACH + AGE ADVANTAGE: Fighter with >2-inch reach advantage AND younger by >3 years wins >65% statistically. Flag these as high-value.
- USE ITD (Inside The Distance): For heavy hitters, prefer "Wins Inside Distance" over specific round betting. Covers both KO and Submission. Better EV, same edge.
- AVOID: UFC parlays. Single fight upsets kill everything. Max 2-leg UFC. Method bets carry higher EV than straight ML.`,

    WNBA: `
WNBA HEURISTICS:
- BOOKS ARE 2-3 SEASONS BEHIND: Sportsbooks allocate minimal modeling resources to WNBA. Lines are often set by NBA quants using rough adjustments. Systematic mispricing exists — this is the core edge.
- PACE EXPLOIT: Atlanta Dream, Dallas Wings, and Indiana Fever run top-3 pace. When these teams play slow-pace opponents (Seattle, New York), fade the Under — the pace mismatch drags the total UP above the soft book estimate. Lean Over aggressively in these matchups.
- STAR REMOVAL = PROP EXPLOSION: WNBA rosters are thin (12 players, no G-League depth call-ups mid-season). A'ja Wilson out → Breanna Stewart-tier backup doesn't exist. Usage redistributes across 2-3 players who each get 5-8 extra possessions. Their points/rebounds props are almost always set to pre-injury levels — massive EV.
- B2B FADE: WNBA schedules include 48-hour turnarounds. No charter flights — teams travel commercial. Away team on 2nd game of B2B: fade their spread, fade star props (especially minutes-based stats).
- ROAD FATIGUE IS UNDERWEIGHTED: Books apply weak travel adjustments. WNBA home court advantage ~3.5 pts but books price it at ~1.5-2. Small home favorites should be bumped up in confidence.
- MORNING LINE CLV WINDOW: WNBA props open late (often 2hrs before tip). Low liquidity = sharp money moves lines fast. Grab early props on pace-up stars before public hammers them. CLV window is 4-6x bigger than NBA.
- SGP RULE: Team Total Over + Lead Playmaker Assists (not points) — in pace-up games, assists correlate better to final score than points because they track ball movement efficiency. Clean, non-redundant correlation.
- QUARTER LINES: Books set q1/q2 lines using stale data. Teams like Seattle Storm start slow (bottom-5 Q1 scoring) but dominate Q4 — fade Seattle Q1 totals, back Q3/Q4. Atlanta Dream go opposite: explosive starters.
- AVOID: WNBA moneyline parlays with heavy favorites. WNBA has 30%+ upset rate on -200+ favorites — variance is violent due to short rosters and single-player dependency.`,

    F1: `
F1 HEURISTICS:
- QUALIFYING WEIGHT BY TRACK: Street circuit (Monaco, Singapore, Zandvoort, Baku) = weight qualifying position at 80% of win probability. Overtaking near-impossible. Power circuit (Monza, Spa, Bahrain) = weight at 50%. Overtaking common.
- TEAMMATE H2H: Primary edge. Use FP3 long-run pace data (fuel-corrected lap times) to determine which teammate has better race-trim setup. This predicts race H2H better than qualifying.
- DNF PROBABILITY: High-attrition street circuits = evaluate "Classified Finishers Under" as value play. Monaco historically sees 30-40% DNF rate.
- AVOID: Race winner outright on non-dominant team in dry conditions. Podium finish (top 3) is better EV with more coverage.`,
  };

  return `${GLOBAL}\n\n${SPORT_RULES[sport.toUpperCase()] || SPORT_RULES.NBA}`;
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
  NHL:    ["icehockey_nhl"],
  SOCCER: ["soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league", "soccer_spain_la_liga"],
  TENNIS: ["tennis_atp_french_open", "tennis_wta_french_open", "tennis_atp_wimbledon", "tennis_wta_wimbledon", "tennis_atp_us_open", "tennis_wta_us_open", "tennis_atp_aus_open", "tennis_wta_aus_open"],
  UFC:    ["mma_mixed_martial_arts"],
  F1:     [], // not on this API
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

async function fetchLiveOdds(sport: string, gameQuery?: string): Promise<string> {
  if (!ODDS_API_KEY) return "Odds API key not configured.";
  const sportKeys = SPORT_KEYS[sport] || SPORT_KEYS.NBA;
  if (sportKeys.length === 0) return `No odds API coverage for ${sport}.`;

  const results: string[] = [];

  for (const key of sportKeys) {
    try {
      const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals,alternate_spreads,alternate_totals&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
      const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
      if (!res.ok) continue;

      const events = await res.json() as OddsEvent[];
      if (!Array.isArray(events) || events.length === 0) continue;

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

        const altSpreads: string[] = [];
        const altTotals: string[] = [];
        for (const market of pinnacle.markets) {
          if (market.key === 'h2h') {
            const ml = market.outcomes.map(o => `${o.name} ML ${o.price > 0 ? '+' : ''}${o.price}`).join(' | ');
            lines.push(`  Moneyline: ${ml}`);
          } else if (market.key === 'spreads') {
            const sp = market.outcomes.map(o => `${o.name} ${o.point && o.point > 0 ? '+' : ''}${o.point} (${o.price > 0 ? '+' : ''}${o.price})`).join(' | ');
            lines.push(`  Spread: ${sp}`);
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
    } catch { /* skip failed sport key */ }
  }

  if (results.length === 0) return `No live odds available for ${sport} right now.`;
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
  MLB:    "baseball/mlb",
  NHL:    "hockey/nhl",
  SOCCER: "soccer/usa.1", // MLS as default; EPL = soccer/eng.1
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
  MLB: 'baseball/mlb', NFL: 'football/nfl',
  NHL: 'hockey/nhl',   WNBA: 'basketball/wnba',
  SOCCER: 'soccer/usa.1',
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

// ── Synthetic Sharp Signal (Pinnacle vs soft-book line gap) ───────────────────
// Pinnacle is the sharpest book. When Pinnacle line diverges from DraftKings/FanDuel,
// that gap reveals where the sharp money is pointing.
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
const SHARP_IDENTITY = `\
## IDENTITY
Tier: SHARP (CTE LOCKS Engine — Specialized in Sports Betting & EV Analysis)
Protocol: Strict Odds Discipline (SOD)
Constraint: NEVER invent odds, lines, or player stats. If not in LIVE ODDS block → UNKNOWN.

## CORE DIRECTIVES
1. STRICT ODDS DISCIPLINE: Only use lines from the LIVE ODDS block. Never hallucinate prices.
2. INJURY FIRST: If a key player is OUT/DOUBTFUL in the INJURY REPORT, reprice the line mentally before picking.
3. SHARP SIGNALS: Pinnacle vs DK gap ≥8pts = real sharp money. Follow it.
4. EV BEFORE NARRATIVE: If a bet feels right but EV is negative → FADE IT.
5. CAVEMAN OUTPUT: "why" fields max 12 words. Cite numbers. No fluff.
6. RAW JSON ONLY: Never wrap in markdown. No commentary outside the JSON.`;

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
      console.log("Anthropic overloaded → falling back to DeepSeek V3");
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
    const sportFilter = sport ? `Focus ONLY on ${sport} games.` : 'Scan all sports (NBA, MLB, tennis, soccer, UFC — whatever is on tonight).';
    const prophetSport = sport || 'ALL';
    const heuristics = getBettingHeuristics(prophetSport === 'ALL' ? 'NBA' : prophetSport);
    const activeSport = prophetSport === 'ALL' ? 'NBA' : prophetSport;
    const [liveOdds, scheduleCtx, injuryData, newsData, pitcherData, sharpSignals] = await Promise.all([
      fetchLiveOdds(activeSport),
      activeSport === 'NBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(activeSport),
      fetchInjuries(activeSport),
      fetchESPNNews(activeSport),
      activeSport === 'MLB' ? fetchMLBPitcherStats('') : Promise.resolve(''),
      fetchSharpSignals(activeSport),
    ]);
    const prompt = `
${SHARP_IDENTITY}

You are a sharp professional sports bettor with 15 years of experience beating closing lines.
Today is ${today} (Eastern Time). ${sportFilter}

${heuristics}

${liveOdds}
${scheduleCtx ? `\n${scheduleCtx}` : ''}
${injuryData ? `\nINJURY REPORT (ESPN — LIVE):\n${injuryData}` : ''}
${pitcherData ? `\nREAL PITCHER STATS (MLB API — cite exact numbers):\n${pitcherData}` : ''}
${newsData ? `\nLATEST NEWS (ESPN):\n${newsData}` : ''}
${sharpSignals ? `\n${sharpSignals}` : ''}

IMPORTANT: Lines above are REAL from Pinnacle/DraftKings — use exact lines, do not invent.
Injuries are LIVE from ESPN — apply Next Man Up logic immediately.
Sharp signals = Pinnacle vs DK gap ≥8pts — follow the sharp side.
News = live ESPN headlines — questionable/out tags reprice the market.
⚠️ win_prob cap: never output >0.82. EV: label "est." — no true prob model exists here.

Your job: apply the above heuristics to identify TODAY's single highest-conviction bet from the real games listed. Run the SHARP CHECK before selecting.

Reasoning process (think step by step, don't include in output):
1. Identify 2-3 real games tonight
2. For each: check CLV opportunity, derivative market value, injury context, contrarian signals
3. Score by: EV gap, correlation quality, juice filter, fragility
4. Select the top one — flag [HIGH-RISK] if applicable, provide PIVOT if needed
5. Output JSON only

Output ONLY a raw JSON object — no markdown, no commentary:
{
  "selection": "e.g. Anthony Edwards Over 28.5 Points or Celtics -4.5",
  "odds": "American odds string e.g. -115 or +130",
  "game_name": "Team A vs Team B — League — Tonight TIME ET",
  "value_gap": "+X.X% EV",
  "recommended_unit": "1 UNIT or 2 UNITS",
  "logic_bullets": [
    "Specific stat or trend #1 with numbers",
    "Specific matchup or situational edge #2 with numbers",
    "Sharp money / line movement or injury context #3"
  ],
  "correlated_insight": "If bet wins, correlated SGP leg or same-game parlay suggestion"
}

Be specific. Use real player names, real team names, real stats. No filler phrases.
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
      league === 'NBA' || league === 'WNBA' ? fetchNBAPlayerStats(matchup) : fetchESPNScoreboard(league),
      fetchInjuries(league, matchup),
      fetchSharpSignals(league),
    ]);
    const liveOddsBlock = [
      swarmLiveOdds ? `\nLIVE ODDS FOR THIS GAME (use these exact lines):\n${swarmLiveOdds}` : '',
      swarmNbaCtx ? `\n${swarmNbaCtx}` : '',
      swarmInjuries ? `\n${swarmInjuries}` : '',
      swarmSharp ? `\n${swarmSharp}` : '',
    ].filter(Boolean).join('\n');

    // Single unified prompt — all 3 perspectives in 1 call (Fix #2: 3 calls → 1)
    const unifiedPrompt = `
You are a sharp sports betting analyst team. Today is ${today}.
Analyze: ${matchup} (${league})
${liveOddsBlock}
${swarmHeuristics}

Produce THREE perspectives on this matchup in one response, then synthesize a verdict.

Output ONLY this raw JSON (no markdown, no commentary):
{
  "quant": {
    "primary_single": "Best bet from pure line-value angle (specific line + odds)",
    "value_gap": "+X.X% EV",
    "confidence_score": 0.75,
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3975" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3202" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "6450" }
    ],
    "omni_report": "2 sentence quant view — cite specific numbers and CLV signal."
  },
  "simulation": {
    "primary_single": "Best bet from game-script/situational angle (specific line + odds)",
    "value_gap": "+X.X% EV",
    "confidence_score": 0.70,
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3975" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3202" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "6450" }
    ],
    "omni_report": "2 sentence situational view — cite game script, fatigue, or contrarian signal."
  },
  "primary_single": "FINAL best bet after synthesizing both views (specific line + odds)",
  "value_gap": "Final EV estimate",
  "confidence_score": 0.80,
  "sgp_blueprint": [
    { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "3975" },
    { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "6450" },
    { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "3202" }
  ],
  "omni_report": "Final 2-sentence verdict. State conviction and single biggest risk. Flag [HIGH-RISK] if any heuristic violated."
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
// ALPHA SHEETS — today's top props cheat sheet
// ─────────────────────────────────────────────────────────────────────────────
export async function generateAlphaSheet(sport: string): Promise<AlphaSheetContainer> {
  const today = todayStr();
  const s = sport.toUpperCase();

  const prompt = `
You are a sharp sports betting analyst building a prop betting cheat sheet.
Today is ${today}.

Generate a cheat sheet of the 10 highest-value player prop bets for ${s} games scheduled TODAY.

For each player:
- Pick a real player with a game tonight
- Identify the most mispriced prop line (points, rebounds, assists, strikeouts, hits, etc.)
- ai_score = your confidence this is +EV (0-10 scale, be realistic — 6-8 range is good, 9+ is rare)
- status_color: #22c55e (strong edge), #eab308 (moderate edge), #f97316 (speculative)
- espn_id: use a realistic ESPN player ID number (e.g. NBA players: LeBron=1966, Curry=3975, Jokic=3112335, Giannis=3032977, SGA=4277905)

Output ONLY a raw JSON array of exactly 10 objects:
[
  {
    "rank": 1,
    "team_logo": "NBA team abbreviation e.g. GSW",
    "player_name": "Full Player Name",
    "metric_label": "e.g. POINTS PROP or STRIKEOUTS",
    "metric_value": "e.g. Over 27.5 -115",
    "season_stat": "e.g. 29.4 PPG L10 or .312 BA",
    "ai_score": 7.8,
    "status_color": "#22c55e",
    "espn_id": "3975"
  }
]

Be specific. Real players, real prop lines, real reasoning baked into metric_value.
`.trim();

  const raw = await ask(prompt);
  const data = parseJSON(raw) as AlphaSheetItem[];

  const titles: Record<string, string> = {
    NBA: "NBA PROP HEATBOARD", MLB: "DINGER & STRIKEOUT SHEET",
    NFL: "NFL PROP SHEET", NHL: "PUCK LINE PROPS",
    TENNIS: "TENNIS EDGE SHEET", SOCCER: "SOCCER PROP SHEET",
  };

  return {
    title: titles[s] || `${s} PROP SHEET`,
    subtitle: `@cavemanlocks AI Edge — ${today}`,
    data,
    timestamp: new Date().toLocaleDateString()
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
    const crossSportKeys = ['NBA', 'WNBA', 'MLB', 'NFL', 'SOCCER'].filter(inSeason);
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
        ? `Scan ALL sports tonight (NBA, WNBA, MLB, NFL, SOCCER). Pick the single best opportunity from any sport.`
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
${SHARP_IDENTITY}

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
      if (s === 'SOCCER') return true;
      return false;
    };
    const crossSports = ['NBA', 'MLB', 'NFL', 'SOCCER', 'WNBA'].filter(inSeason);

    // Fetch all data in parallel — real stats, news, odds, injuries, sharp signals
    const [oddsCtx, injuryCtx, playerStatsCtx, teamStatsCtx, newsCtx, pitcherCtx, weatherCtx, sharpCtx, crossOdds] = await Promise.all([
      fetchLiveOdds(league, matchup),
      fetchInjuries(league, matchup),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBAPlayerStats(matchup)
        : Promise.resolve(''),
      league === 'NBA' || league === 'WNBA'
        ? fetchNBATeamStats(matchup)
        : Promise.resolve(''),
      fetchESPNNews(league, matchup),
      league === 'MLB' ? fetchMLBPitcherStats(matchup) : Promise.resolve(''),
      fetchWeather(matchup, league),
      fetchSharpSignals(league),
      Promise.all(crossSports.filter(s => s !== league).map(s => fetchLiveOdds(s))).then(r => r.filter(Boolean).join('\n\n')),
    ]);

    const heuristics = getBettingHeuristics(league);

    const gamePrompt = `
${SHARP_IDENTITY}

You are a sharp sports betting analyst. Today is ${today}.
Game: ${matchup} (${league})

${heuristics}

LIVE ODDS FOR THIS GAME (USE THESE EXACT LINES — do not invent odds):
${oddsCtx || "No live odds found — note this clearly in your output, do not fabricate lines."}

INJURY REPORT (ONLY reference players listed here — do NOT invent injuries):
${injuryCtx || "No injury data available from ESPN right now. Do NOT fabricate any injuries."}

${playerStatsCtx ? `REAL PLAYER STATS — BallDontLie API (cite these exact numbers, do NOT invent):\n${playerStatsCtx}\n` : ''}
${teamStatsCtx ? `REAL TEAM STATS — ESPN API (cite these exact numbers, do NOT invent):\n${teamStatsCtx}\n` : ''}
${pitcherCtx ? `REAL PITCHER STATS — MLB Official API (cite these exact numbers, do NOT invent):\n${pitcherCtx}\n` : ''}
${weatherCtx ? `WEATHER DATA — wttr.in real-time:\n${weatherCtx}\n` : ''}
${newsCtx ? `LATEST NEWS — ESPN live:\n${newsCtx}\n` : ''}
SHARP SIGNALS (Pinnacle vs DK line gap — directional signal only):
${sharpCtx || "No significant line gap detected."}

⚠️ HONESTY RULES — NON-NEGOTIABLE:
- win_prob: your calibrated estimate based on available data. Do NOT output >0.82 — real sharp bettors rarely see edge that clean.
- EV: label as "est." — we have no true probability model. Only output EV if you can ground it in the real stats/odds above.
- If a stat block is missing (no player stats, no pitcher data), say so in game_summary. Do NOT invent replacement numbers.
- rationale must cite at least one real number from the data blocks above or from the live odds. No narrative-only rationale accepted.

⚠️ ANTI-HALLUCINATION RULES — MUST FOLLOW:
1. PLAYER STATS: If REAL PLAYER STATS block is present, cite exact numbers in rationale (PPG, L5 form). Never round or invent — copy the number directly.
2. PITCHER STATS: If REAL PITCHER STATS block is present, cite pitcher's ERA, K/9, WHIP directly. Never say "2.80 ERA" if the block shows "3.84 ERA".
3. WEATHER: If WEATHER block shows wind ≥15mph, it MUST affect your total pick and any passing props. Do not ignore it.
4. INJURIES: Only cite players from the INJURY REPORT. Empty report = say "no injury data" — never invent.
5. ODDS: Use exact lines from LIVE ODDS. If block is empty, label estimates as "est."
6. PROPS: Set prop lines relative to the REAL averages provided. Player averaging 24.6PPG → prop near 24.5, not invented 28.5.
7. NEWS: Lineup changes, questionable tags in news → reprice that market immediately before picking.

🔍 ALT LINE HUNTING — VERY IMPORTANT:
The LIVE ODDS block may contain alternate_spreads and alternate_totals alongside standard lines.
For EACH market (spread, total): scan ALL listed lines (standard + alternate) and pick the one with the best true value.
- If the standard spread is Lakers +5.5 but you believe the true margin is +9, then Lakers +8.5 alt spread at real odds is far better value — pick the alt.
- If an alt line exists and gives meaningfully more cushion OR better odds edge, use it and set "is_alt": true.
- If the standard line is already the best value, leave "is_alt" as false and omit "alt_note".
- Only use alt lines that appear in the LIVE ODDS block — never fabricate alternate lines.

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
    { "player": "MUST be a real player on one of these two teams", "market": "Points", "pick": "Over 26.5", "odds": "-115", "win_prob": 0.74, "rationale": "1-2 sentences based on real stats", "niche_stat": "Season average or matchup stat" },
    { "player": "Real player on these teams only", "market": "Rebounds", "pick": "Over 8.5", "odds": "-110", "win_prob": 0.71, "rationale": "1-2 sentences", "niche_stat": "Real stat" },
    { "player": "Real player on these teams only", "market": "Assists", "pick": "Over 6.5", "odds": "-115", "win_prob": 0.68, "rationale": "1-2 sentences", "niche_stat": "Real stat" },
    { "player": "Real player on these teams only", "market": "Points", "pick": "Over 21.5", "odds": "-110", "win_prob": 0.65, "rationale": "1-2 sentences", "niche_stat": "Real stat" },
    { "player": "Real player on these teams only", "market": "Threes", "pick": "Over 2.5", "odds": "-115", "win_prob": 0.62, "rationale": "1-2 sentences", "niche_stat": "Real stat" }
  ],
  "sgp": {
    "legs": [
      { "pick": "Team covers or wins", "odds": "-130", "why": "caveman reason max 10 words" },
      { "pick": "Real player on these teams Over X stat", "odds": "-115", "why": "caveman reason" },
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

    const payload = {
      ...game,
      pick_of_day: daily.pick_of_day,
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
${SHARP_IDENTITY}

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
