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
  if (b <= 0 || p <= 0) return 0;
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
NBA NICHE VARIABLES + HEURISTICS:
━━ ADVANCED METRICS (use the NBA ADVANCED STATS block if present):
- NetRtg = best single predictor of team quality. Gap of 5+ NetRtg pts = strong favorite signal.
- OffRtg vs opponent DefRtg gap → true scoring edge. If a team's OffRtg (118) faces DefRtg (110) = +8 scoring edge → they score more than the book expects.
- Pace: Use model Expected Total vs book total line. If model >4 pts above book → lean Over. If model <4 pts below → lean Under.
━━ SITUATIONAL VARIABLES:
- ALTITUDE (Denver): Nuggets home games = +2.5 pts edge. Thin air at 5,280 ft exhausts visitors by Q3. Always add +2.5 to Nuggets home spread confidence.
- REST DIFFERENTIAL: Team with 2+ days rest vs 0 days rest = +1.5–2 pts historical edge. Never ignore rest mismatch.
- B2B FATIGUE: Night-2 of B2B → veteran star props average -3.5 pts vs their season avg. Young legs (<25) are less affected. Flag B2B for every prop.
- BACK-TO-BACK ROAD: Away team on B2B night-2 → fade them vs home team. Home team on B2B → slight fade but home crowd partially offsets.
- HOME/AWAY EFFICIENCY: Some teams' OffRtg drops >5 pts on road. If away team OffRtg drops to below opponent DefRtg → fade them.
━━ BLOWOUT & USAGE:
- BLOWOUT RISK: If spread >10, discount "Over" on star prop. 4th quarter rest = props die. Flag any SGP combining heavy favorite ML + star Over.
- USAGE SHIFT: Star out → backup usage rises 25–35%. Backup's prop is still set to pre-injury level = massive EV. Calculate: missing_star_minutes × usage% → redistributed possessions.
- KEY NUMBERS: 3, 5, 7, 10. Moving from -9.5 to -10.5 crosses key number 10 — blowout cover probability drops ~8%.
━━ SGP RULES:
- Team Total Over + Lead Playmaker Assists (NOT points). Assists are a pace proxy. If team scores more, playmaker gets more assists — pure correlation.
- Avoid: Star Points Over + Team ML (heavy fav). Blowout makes both legs contradict each other in Q4.`,

    MLB: `
MLB NICHE VARIABLES + HEURISTICS:
━━ PITCHER CONTEXT (use REAL PITCHER STATS block if present):
- ERA/K9/WHIP: Cite exact numbers. ERA <3.50 = elite. WHIP <1.10 = elite. K9 >10 = high strikeout value.
- PITCHER REST: 5+ days rest → ace performs better. 3 days rest → expect shorter outing, higher ERA, fade K props.
- HANDEDNESS PLATOON: LHP vs R-heavy lineup → lean pitcher. RHP vs L-heavy lineup → lean pitcher. Check lineup handedness vs pitcher.
- BULLPEN USAGE: Team's RP thrown 12+ IP in last 3 days → vulnerable late game. Lean Over 7th-9th inning total or full-game Over.
━━ PARK FACTORS (memorize these):
- COORS FIELD (COL) = +20–25% runs above average. Always lean Over and fade pitchers here.
- PETCO PARK (SD), ORACLE PARK (SF), KAUFFMAN (KC) = -15–20% runs. Strong lean Under, strong pitcher ERA support.
- YANKEE STADIUM (NYY), FENWAY (BOS), GREAT AMERICAN (CIN) = +10–15% runs. Lean Over, especially on windy days.
- All others: neutral ±5%. Park factor context = cite the specific park name in rationale.
━━ REGRESSION SIGNALS:
- BABIP >.320 sustained = luck factor. Fade that pitcher next 2 weeks (regression incoming).
- Pythagorean W%: RS^1.83/(RS^1.83+RA^1.83). If actual W% > Pythagorean by >8% → team is overperforming. Fade them.
━━ WEATHER (use WEATHER DATA block):
- Wind blowing OUT 15+mph + temp >80°F = lean Over (1–1.5 run adjustment).
- Wind blowing IN 15+mph + temp <60°F = lean Under (1–1.5 run adjustment).
- Rain delay risk → lean Under (pitchers shaken, relievers used early).
━━ SHARP BETS:
- F5 (First 5 Innings): Best when ace vs weak offense. Removes bullpen variance entirely. Sharp bettors prefer F5 on elite starters.
- NRFI (No Run First Inning): Both aces starting in pitcher park = NRFI best value. Sharp single only, never a parlay leg.
- UMPIRE ZONE: High-K ump (tight strike zone) → Over on K props, Under on hits total. Always flag if K-zone ump is assigned.
━━ SGP RULES:
- Pitcher strikeouts Over + Under hits allowed + Pitcher to win = clean triple correlation on ace days.
- AVOID run lines in parlays — low payout vs blowout bust risk.`,

    NFL: `
NFL NICHE VARIABLES + HEURISTICS:
━━ KEY NUMBERS (non-negotiable):
- 3 and 7 are sacred. Half-point off 3 or 7 worth 3–5% win probability.
- Key sequence: 3, 6, 7, 10, 13, 14, 17. Never buy past 10 unless price is -105 or better.
- Line moves from -2.5 to -3.5 = enormous (FG margin). From -4 to -5 = negligible. Never pay -130 to buy a half-point off 4.
━━ WEATHER FORMULA (use WEATHER DATA block):
- Wind >15mph → fade all passing props -30%, lean Under on game total.
- Wind >25mph → hard Under, fade QBs entirely, lean Run game props.
- Rain + cold + wind = compound effect. Each adds ~0.5 pts to Under confidence.
- Dome teams (Chiefs, Saints, Rams, Vikings) playing outdoors in cold/wind = -2 pt adjustment.
━━ REST + TRAVEL:
- Bye week team vs no-bye = +3.2 pts historical edge (biggest rest edge in sports).
- Short week (Thursday game) team = -1.7 pts. Books rarely fully adjust.
- West Coast team playing 10am local time (East Coast road game) = -1.5 pts. Circadian disruption is real.
- Long travel (LAX → NYC in winter) = -0.8 pts on road side.
━━ SITUATION EDGES:
- DIVISIONAL DOGS: ATS record for divisional underdogs = ~54% historically. Familiarity flattens lines.
- TURNOVER REGRESSION: Team +5 in turnover margin over last 3 games → regression incoming. Fade them vs positive turnover differential team.
- REVENGE SPOT: Team coming off embarrassing loss (>17 pts) at home = +2.5 pts ATS edge (motivated performance).
━━ EFFICIENCY PROXY:
- Net yards per play differential (offense - defense). >0.5 yd/play advantage = ~3 pt spread edge.
- 3rd down conversion rate: 50%+ team vs 35%- team = sustained possession advantage.
- Red zone TD% vs Red zone scoring%: Team converting TDs not FGs = scoring efficiency edge.
━━ SGP RULES:
- QB Over passing yards + WR1 Over receiving yards + Team Win = clean triple if pass-heavy team with no wind.
- NEVER pair QB passing yards + RB rushing yards unless RB is elite receiver (50+ receptions/yr).
- Avoid: TD scorer props in parlays. Too volatile, kills SGPs constantly.`,

    NHL: `
NHL NICHE VARIABLES + HEURISTICS:
━━ GOALTENDER (use NHL TEAM STATS block):
- GOALIE IS THE SINGLE MOST IMPORTANT VARIABLE. Check SV% in the stats block.
- SV% >.915 = elite. .900–.915 = average. <.900 = vulnerable. Top goalie vs bottom-10 offense = lean Under and puck line.
- NEVER BET until starting goalie is confirmed (typically announced ~1–2 hrs before puck drop). Backup goalie = line moves 0.5–1 goal instantly.
- GAA: <2.50 = elite. >3.00 = vulnerable. Cite exact from stats block.
━━ SPECIAL TEAMS (use NHL TEAM STATS block):
- PP Goals (PPG): High PPG team vs low-penalty kill team = lean Over and PP scorer prop.
- Faceoff% >52% = possession advantage. More possessions → more shots → more goals. Slight Over lean.
━━ SITUATIONAL VARIABLES:
- B2B PENALTY: Second game of B2B → -8% goals scored on average. Away B2B = -12%. Always lean Under.
- TRAVEL: East team playing Pacific coast away games = -5% performance. Pacific team playing 7pm ET road game = -3% (body clock).
- HOME ICE: NHL home advantage ≈ 0.3 extra goals per game. Small but consistent.
- HIGH SHOTS ≠ HIGH GOALS: Distinguish shot quantity (shots for/against) from shot quality. 35 perimeter shots ≠ 35 dangerous chances.
━━ POSSESSION METRICS:
- Corsi% >55% = dominant possession team. Their goal totals are sustainable (not PDO-inflated).
- Corsi% <45% = possession-weak. Good record may be PDO-inflated (shooting % + SV% above sustainable). Regression incoming.
- PDO = shooting% + save% (should ≈ 100). >102 = lucky team. <98 = unlucky team. Regress accordingly.
━━ SGP RULES:
- Team puck line (-1.5) + Over team total goals = only valid if opponent has bottom-10 defense AND your team has elite possession Corsi.
- Anytime goal scorer + Over team goals = clean correlation. If team scores 4+, multiple scorers hit.
- AVOID: Puck line parlays across multiple games. Hockey variance is violent — one goalie meltdown kills everything.`,

    SOCCER: `
SOCCER NICHE VARIABLES + HEURISTICS:
━━ xG (EXPECTED GOALS) — THE CORE SIGNAL:
- xG > actual goals = team is underperforming. Positive regression incoming. BACK THEM next match.
- xG < actual goals = team is overperforming ("fraudulent winner"). Regression incoming. FADE THEM next match.
- Both teams with xG >1.5/game → lean BTTS (Both Teams To Score). Both under 1.0 xGA → lean Clean Sheet / Under.
━━ FORM CONTEXT (use SOCCER STANDINGS if provided):
- W/D/L last 5 + GD (Goal Differential) are the primary signals.
- GD >+15 in a league = dominant team, fully justify -1.5 AH or -0.5 AH.
- PPG (Points Per Game) >.67 = above average. <.40 = relegation form.
━━ ASIAN HANDICAP (PRIMARY MARKET):
- Use AH over 1X2 always. Eliminates draw kill. -0.25 AH (quarter ball) = half bet wins even on draw. Best EV entry.
- AH -0.5 = must win outright. AH -1.5 = must win by 2. AH +0.5 = wins or draws.
━━ SITUATION EDGES:
- HOME ADVANTAGE: EPL ≈ 0.5 goals, La Liga ≈ 0.4, MLS ≈ 0.6, Bundesliga ≈ 0.45. Apply to every line.
- FIXTURE CONGESTION: 3 games in 8 days = rotation risk. Backup XI reduces quality ~15%.
- MOTIVATION: Relegation battle team vs comfortable mid-table = massive underdog value. The bottom team fights; mid-table doesn't.
- LATE-SEASON FATIGUE: Champions League participant playing domestic league late season = 20% extra fatigue. Rotation likely.
━━ NICHE MARKETS:
- CORNERS: Wing-heavy teams (crosses per game >15) generate corners even when losing. Corners O/U is bookmaker-soft — less sharp money.
- CARDS: High-card referee (>5 yellows/game) + physical matchup (derby, relegation) = Over cards EV.
- BTTS: Defend by checking last 5 H/A splits separately. A team scoring at home but not away skews BTTS calculations.
━━ SGP RULES:
- Over game goals + BTTS = correlated only if both teams have >1.2 GF/game. One defensive team kills it.
- Result + Under/Over Cards based on referee card rate = clean correlation for high-card refs.
- AVOID: Draws in parlays. Draw kill rate = parlay poison. Use double chance (Win or Draw) instead.`,

    TENNIS: `
TENNIS NICHE VARIABLES + HEURISTICS:
━━ SURFACE IS THE DOMINANT VARIABLE — ALWAYS CHECK THE TOURNAMENT SURFACE FIRST:
- CLAY (Roland Garros): Slowest surface. High-bounce, topspin-dominant, long baseline rallies. Serve matters LESS. Baseline grinders, physicality, and topspin excel. Big servers underperform. Fade flat-hitters and pure serve-bots.
- GRASS (Wimbledon): Fastest surface. Low-bounce, serve+volley, short points. Big servers and net players dominate. First-set results are highly predictive (serve holds easy). Fade clay specialists — their topspin loops into the net.
- HARD / OUTDOOR (US Open, Australian Open): Balanced surface. US Open is medium-fast. Aus Open Plexicushion is medium-slow. Recent form and ranking most predictive here. Serve still matters but not as dominant as grass.
- HARD / INDOOR: Fast, controlled. No wind, no sun. Predictable bounce. Serve dominant. Big servers favorite. Baseline players struggle more indoors than outdoor hard.
━━ SERVE + RETURN STATS BY SURFACE:
- Hold% >80% = reliable server. Use game handicap over ML. Hold% <65% = volatile — fade as heavy favorite.
- Ace rate: On grass, high ace rate = massive advantage. On clay, almost irrelevant. On hard, moderate advantage.
- Break point conversion: On clay, high because longer rallies create more opportunities. On grass, very low.
━━ FATIGUE TRACKING:
- Total SETS played this tournament week (not just W/L). 3-setter in R1 + 3-setter in R2 = 6 sets of high-intensity = fatigue by R3+.
- Total GAMES played is even better. >50 games in 2 rounds = physical fatigue. Lean against in next round.
- POST-TITLE HANGOVER: Fade any player the week AFTER winning a tournament. Documented 58% underperformance vs. expected line. Fatigue + motivation dip is real.
━━ CONDITIONS:
- Roland Garros: Heavy balls (humidity), slow court, physical. Stamina dominant.
- Wimbledon: Light balls, fast grass, serve dominant. First 2 rounds often upsets (grass specialists appear).
- US Open night sessions: Faster ball under lights, loud crowd, momentum swings. Serve is enhanced at night.
- Australian Open heat policy: Extreme heat = delays, physical attrition. Heavy favorites in 5-set danger.
━━ BETTING STRUCTURE:
- Game Handicap (+3.5/-3.5) > ML for heavy favorites (-250+). Protects against bagel+tiebreak variance. Much better EV.
- Set Handicap (-1.5 sets = must win 2-0) = value when one player is clearly physically superior AND on their best surface.
- Early rounds (R128, R64): Highest upset rate. 15–20% higher upset frequency vs R16+. Value on underdogs especially on grass.`,

    UFC: `
UFC NICHE VARIABLES + HEURISTICS:
━━ STYLE MATCHUP — THE PRIMARY VARIABLE:
- WRESTLER vs STRIKER: Elite wrestlers win 68%+ vs pure strikers. Takedowns control time, nullify striking. Fade the striker ML unless he has elite takedown defense.
- JUDO/BJJ vs STRIKER: Submission threat = striker can't fully commit to punching. Grappler ML or Decision prop.
- STRIKER vs STRIKER: Judge it on reach, speed, accuracy, recent KO results. Pressure fighter vs counter fighter = reach decides distance control.
- GRAPPLER vs GRAPPLER: Evaluate who has better takedown defense. The one who stays standing is usually better on the feet.
━━ CAGE VARIABLES:
- SMALL CAGE (UFC Apex, ~25-ft): Higher finish rate (+15% KO/Sub vs large venues). Less room to run. Pressure fighters thrive. Lean ITD (Inside the Distance).
- LARGE ARENA (MSG, T-Mobile, Kaseya): More space = more out-fighting. Counter strikers thrive. Decision rate rises. Method:Decision bet has value.
- OUTDOOR EVENT: Rarely happens but wind/heat factors apply to striking accuracy.
━━ PHYSICAL ADVANTAGES:
- REACH: >3-inch reach advantage + age advantage >3 yrs = significant edge. Every inch matters at distance fighting.
- HEIGHT: Tall fighters with long reach prefer distance. Short stocky fighters prefer clinch and grappling.
- WEIGHT CLASS: Naturally bigger fighters who cut weight hard vs fighters at their natural weight = dehydration edge for natural-weight fighter post-weigh-in.
━━ PSYCHOLOGICAL + FORM SIGNALS:
- RECENT KO LOSS: Chin concern is real. Documented increased KO vulnerability in subsequent fights. Fade under pressure vs KO artist, even if they recovered.
- STREAK: Win streak (5+) on betting favorites can be overvalued by public. Regression to mean is common.
- REVENGE SPOT: Fighter coming off a close controversial loss = motivated. Slight underdog value if styles align.
- LATE NOTICE: Fighter taking fight on <2 weeks notice = -5–8% performance estimate. Book doesn't always adjust.
━━ BETTING STRUCTURE:
- ITD (Inside the Distance) > specific round: Covers both KO and Submission. Better EV, same edge.
- Method props carry highest EV of any UFC market: Decision, KO/TKO, Submission.
- Max 2-leg UFC parlays. Single fight upset destroys 3+ leg parlays constantly.
- Main card vs Prelim: Prelim fighters less scouted by books = more mispricings in prelims.`,

    WNBA: `
WNBA NICHE VARIABLES + HEURISTICS:
━━ CORE EDGE: BOOKS ARE 2–3 SEASONS BEHIND:
- Sportsbooks allocate minimal modeling resources to WNBA. Lines are set by NBA quants using rough adjustment. Systematic mispricing exists — this is the core exploitable edge.
- Props open late (2hrs before tip). Low liquidity. Sharp money moves lines fast. Grab early props on pace-up stars before public discovers them. CLV window is 4–6x bigger than NBA.
━━ PACE EXPLOIT:
- Atlanta Dream, Dallas Wings, Indiana Fever = top-3 pace WNBA. When they play slow-pace opponents (Seattle, New York), the pace mismatch drags totals UP above book estimates. Lean Over aggressively.
- Seattle Storm = explosive Q3/Q4 but slow Q1/Q2. Fade Seattle team total in Q1 lines. Back Seattle Q4 total.
━━ STAR REMOVAL = PROP EXPLOSION:
- WNBA rosters: 12 players. No G-League call-ups. A'ja Wilson out → no equivalent backup exists. Usage redistributes across 2–3 players who get 5–8 extra possessions each.
- Their props are still set at pre-injury levels = massive EV.
- Formula: missing star usage% × team possessions → redistributed possessions to specific backups. Those backups' props are the value bet.
━━ B2B + TRAVEL:
- WNBA B2B: 48-hour turnaround, no charter flights — commercial travel only. Away team on B2B night-2: fade their spread, fade star props (especially minutes-based props).
- Home advantage in WNBA ≈ 3.5 pts but books price it at 1.5–2. Small home favorites underpriced by ~1–1.5 pts.
━━ QUARTER LINES:
- Books set Q1/Q2 totals using stale full-game models. Teams with strong quarter-specific patterns:
  → Atlanta Dream: explosive starters, Q1 Over value.
  → Seattle Storm: slow starters (bottom-5 Q1 scoring), explosive Q3/Q4. Fade Q1, back Q3.
  → Indiana Fever: Caitlin Clark creates high-pace Q2–Q3 surge. Q2 total often underpriced.
━━ SGP RULES:
- Team Total Over + Lead Playmaker Assists (not points). Assists proxy ball movement + pace better than points alone.
- Avoid WNBA moneyline parlays on heavy favorites (-200+). 30%+ upset rate on big WNBA favorites — variance is violent.`,

    F1: `
F1 NICHE VARIABLES + HEURISTICS:
━━ CIRCUIT TYPE IS THE PRIMARY VARIABLE (check CIRCUIT CONTEXT if provided):
- STREET CIRCUIT (Monaco, Singapore, Baku/Azerbaijan, Jeddah, Miami, Las Vegas, Melbourne/Albert Park, Zandvoort):
  Qualifying position predicts 80–95% of race result. Overtaking near-impossible. Dirty air = catastrophic. Back the pole sitter. Heavy favorite is actually underpriced here.
- POWER CIRCUIT (Monza, Spa/Belgium, Bahrain, Abu Dhabi, Austin):
  Engine power = dominant factor. Overtaking common via long straights. Qualifying matters ~50%. Red Bull and Ferrari power units historically strongest here.
- TECHNICAL CIRCUIT (Hungary, Silverstone, Suzuka, Interlagos):
  Aerodynamic downforce + setup critical. Low-drag vs high-downforce setups diverge. Teams with best aero engineers (Red Bull, Ferrari) dominate. Overtaking moderate.
- SPRINT WEEKEND: FP3 pace data available before race. Sprint result reveals race-trim setup directly. Adjust race bets based on sprint performance.
━━ KEY BETTING VARIABLES:
- TEAMMATE H2H: Most predictable F1 market. Both on identical equipment. Use FP3 long-run (fuel-corrected) pace to identify which teammate is better set up for race-trim.
- WET WEATHER: Rain = field normalizer. Midfield cars gain 2–3 grid positions vs dry. Back underdog +AH (top-10 finish). Fade heavy favorites (they have more to lose).
  → Rain probability on race day = major line mover. Always check weather context.
- DNF PROBABILITY: Street circuits 20–40% historical DNF rate. "Classified Finisher" prop has clear value on street circuits. Safety car = guaranteed in Monaco, Singapore.
- TIRE STRATEGY: Soft → Medium → Hard progression. Teams choosing aggressive undercut (early pit stop) gain track position. Conservative teams (overcut) rely on pace. Undercut success rate ≈ 70%.
━━ CHAMPIONSHIP PRESSURE:
- Tight championship battle → drivers race harder in early laps = higher DNF risk.
- Drivers already clinched = race management mode. Fade them in risky circuits.
- Midfield constructor battle: Teams gambling on strategy for points = more variance in results.
━━ BETTING STRUCTURE:
- Outright Race Winner: Only bet on street circuits (pole = 80% win prob) or dominant cars in dry.
- Podium Finish (Top 3): Better EV than race winner. More coverage, same edge from dominant team.
- Teammate H2H: Cleanest, most predictable F1 market. Always look here first.
- AVOID: Race winner outright on technical circuits in mixed conditions. Too many variables.`,
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

  // Tennis: surface type from sport_key — critical betting variable
  const TENNIS_SURFACE: Record<string, string> = {
    'tennis_atp_french_open':  '🏟️ ROLAND GARROS — Surface: CLAY (slowest, topspin-dominant, baseline grinders excel, big servers fade)',
    'tennis_wta_french_open':  '🏟️ ROLAND GARROS — Surface: CLAY (slowest, topspin-dominant, physical endurance key)',
    'tennis_atp_wimbledon':    '🏟️ WIMBLEDON — Surface: GRASS (fastest, serve+volley, big servers/net players dominate, clay specialists fade)',
    'tennis_wta_wimbledon':    '🏟️ WIMBLEDON — Surface: GRASS (fastest, serve dominant, low bounce, aggressive baseliners)',
    'tennis_atp_us_open':      '🏟️ US OPEN — Surface: HARD/OUTDOOR (medium-fast, night sessions faster ball under lights, loud crowd)',
    'tennis_wta_us_open':      '🏟️ US OPEN — Surface: HARD/OUTDOOR (medium-fast, night session crowd/momentum factor)',
    'tennis_atp_aus_open':     '🏟️ AUSTRALIAN OPEN — Surface: HARD/OUTDOOR (medium-slow Plexicushion, heat policy in January, long rallies)',
    'tennis_wta_aus_open':     '🏟️ AUSTRALIAN OPEN — Surface: HARD/OUTDOOR (medium-slow Plexicushion, heat delays possible)',
  };

  const results: string[] = [];

  for (const key of sportKeys) {
    try {
      const url = `${ODDS_API_BASE}/sports/${key}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals,alternate_spreads,alternate_totals&bookmakers=pinnacle,draftkings,fanduel&dateFormat=iso&oddsFormat=american`;
      const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
      if (!res.ok) continue;

      const events = await res.json() as OddsEvent[];
      if (!Array.isArray(events) || events.length === 0) continue;

      // Inject tennis surface header before listing events for this tournament
      if (TENNIS_SURFACE[key]) results.push(TENNIS_SURFACE[key]);

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
    const [liveOdds, scheduleCtx, injuryData, newsData, pitcherData, advancedData, sharpSignals] = await Promise.all([
      fetchLiveOdds(activeSport),
      activeSport === 'NBA' ? fetchNBAScheduleToday() : fetchESPNScoreboard(activeSport),
      fetchInjuries(activeSport),
      fetchESPNNews(activeSport),
      activeSport === 'MLB' ? fetchMLBPitcherStats('') : Promise.resolve(''),
      activeSport === 'NBA' ? fetchNBALeagueSnapshot() : Promise.resolve(''),
      fetchSharpSignals(activeSport),
    ]);
    const prompt = `
${SHARP_IDENTITY}

You are a sharp professional sports bettor with 15 years of experience beating closing lines.
Today is ${today} (Eastern Time). ${sportFilter}

${heuristics}

${liveOdds}
${scheduleCtx ? `\n${scheduleCtx}` : ''}
${advancedData ? `\n${advancedData}` : ''}
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
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" }
    ],
    "omni_report": "2 sentence quant view — cite specific numbers and CLV signal."
  },
  "simulation": {
    "primary_single": "Best bet from game-script/situational angle (specific line + odds)",
    "value_gap": "+X.X% EV",
    "confidence_score": 0.70,
    "sgp_blueprint": [
      { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" },
      { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "" }
    ],
    "omni_report": "2 sentence situational view — cite game script, fatigue, or contrarian signal."
  },
  "primary_single": "FINAL best bet after synthesizing both views (specific line + odds)",
  "value_gap": "Final EV estimate",
  "confidence_score": 0.80,
  "sgp_blueprint": [
    { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "" },
    { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "" },
    { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "" }
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
- espn_id: leave as "" — do NOT invent ESPN player IDs, they will be wrong

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
    "espn_id": ""
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
    const [oddsCtx, injuryCtx, playerStatsCtx, advancedCtx, teamStatsCtx, nicheCtx, newsCtx, pitcherCtx, weatherCtx, sharpCtx, crossOdds] = await Promise.all([
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
      league === 'NHL'    ? fetchNHLTeamStats(matchup) :
      league === 'SOCCER' ? fetchSoccerContext(matchup) :
      league === 'F1'     ? Promise.resolve(getF1CircuitContext(matchup)) :
      Promise.resolve(''),
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

${advancedCtx ? `${advancedCtx}\n` : ''}
${nicheCtx ? `SPORT-SPECIFIC NICHE DATA (cite these exact numbers, do NOT invent):\n${nicheCtx}\n` : ''}
${playerStatsCtx ? `REAL PLAYER STATS — BallDontLie API (cite these exact numbers, do NOT invent):\n${playerStatsCtx}\n` : ''}
${teamStatsCtx ? `REAL TEAM STATS — ESPN API (cite these exact numbers, do NOT invent):\n${teamStatsCtx}\n` : ''}
${pitcherCtx ? `REAL PITCHER STATS — MLB Official API (cite these exact numbers, do NOT invent):\n${pitcherCtx}\n` : ''}
${weatherCtx ? `WEATHER DATA — wttr.in real-time:\n${weatherCtx}\n` : ''}
${newsCtx ? `LATEST NEWS — ESPN live:\n${newsCtx}\n` : ''}
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
