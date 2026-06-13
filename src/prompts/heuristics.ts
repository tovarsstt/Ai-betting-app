// ── SkillLoader (Agent-Skills Integration) ────────────────────────────────────
import { readFileSync, existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// Resolve from project root (2 levels up from src/prompts/)
const ROOT = path.resolve(__dirname, '../..');

export function getBettingHeuristics(sport: string): string {
  try {
    const coreH = readFileSync(path.resolve(ROOT, 'skills/betting/cte_core_skill.md'), 'utf8');
    const globalH = readFileSync(path.resolve(ROOT, 'skills/betting/global_heuristics.md'), 'utf8');
    const sportPath = path.resolve(ROOT, `skills/betting/${sport.toLowerCase()}_skill.md`);
    const sportH = existsSync(sportPath) ? readFileSync(sportPath, 'utf8') : '';
    return `${coreH}\n\n${globalH}\n\n${sportH}`;
  } catch (err) {
    console.error(`[SkillLoader] Failed to load heuristics for ${sport}:`, err);
    return "CTE LOCKS: Find the edge. No fluff.";
  }
}

// ── Sport-specific bet type context ───────────────────────────────────────────
export function getSportBetContext(sport: string): string {
  const ctx: Record<string, string> = {
    NBA: `🏀 CURRENT: NBA Finals 2026 (June). Series dynamics, home court, and fatigue are dominant factors.
Bet types: spreads, moneyline, player props (points, rebounds, assists, steals, blocks, 3PM).
Niche: quarter lines (Q1/Q4 sharpest), halftime lines, team totals, 1H spread (less garbage time noise).
Finals niche: series elimination games — home team covers 58%. After road win game 1 — road team covers 54% in game 2 (home emotionally deflated). Game 5 of tied series = highest variance, lean Over.
Blowout risk in Finals is LOWER (parity). Fade -10+ spreads harder than regular season.
Niche stats: Net Rating On/Off, OffRtg, DefRtg, Pace (possessions/48), True Shooting %, Usage Rate, Box Plus/Minus (BPM), 5-man lineup net rating, 3PT rate allowed, turnover rate vs steal rate.
Key edges: usage-spike on star injury/rest, blowout risk on -12+ (fade starter props), referee crew (Scott Foster/Tony Brothers = 44+ fouls/game = Over + FT props), rest advantage ≥2 days covers 55.3% ATS.`,

    WNBA: `Bet types: spreads, moneyline, player props (points, rebounds, assists, steals, 3PM).
Niche: Q1/Q2 team totals (books set stale overnight), morning CLV props, pace-up matchups, B2B road fades.
Books are 2-3 seasons behind in WNBA modeling — systematic mispricing exists.
Niche stats: Pace, OffRtg, DefRtg per WNBA.com, usage rate after star injury, thin rosters = bigger prop explosions.`,

    NFL: `🏈 OFFSEASON: June 2026. Regular season starts September 2026. Active markets: futures + win totals only.
June alpha window: book models most stale right now. Max inefficiency in Super Bowl futures.
Key futures drivers: QB situation (confirmed starter = +3 wins baseline), draft class, coaching continuity, schedule difficulty.
Win Total O/U: best June bet. New HC + playoff-ready roster = Over. Unsettled QB going into June = avoid entirely.
Preseason (late July–August): Never bet 1H. 2H only (starters sit). Fade preseason Overs by default.
Niche stats (for September+ regular season reference): DVOA (team efficiency), EPA/play, CPOE, air yards, yards after contact, pressure rate, line yards, O-line run block %, Red Zone TD%.
Key numbers: 3, 7, 10, 14 — never cross without +EV price at -105 or better.
Situational edges: bye-week +3.2 pts ATS, divisional dogs cover slightly above 50% long-run (verified ~52-54%, varies by season), Thursday short-week -1.7 pts. Wind >15mph = fade all passing props, lean Under.`,

    SOCCER: `WORLD CUP 2026 IS LIVE (June 11 – July 19, 2026). Prioritize WC matches above ALL other leagues.
DRAW INSURANCE (how we make money on favourites): soccer is 3-way. A "team to WIN" pick LOSES on a draw (cost us Canada). Fav wins ≥60% → straight ML. Fav better but <60% with live draw → DOUBLE CHANCE (gana o empata / 1X). Tight + high draw → DRAW NO BET (apuesta sin empate). VALUE = pick prob must beat the devigged implied price, else PASS.
Bet types (priority): Double Chance / Draw No Bet (draw insurance) > Asian handicap > goals total > BTTS > shots on target > corners > cards. Straight 3-way ML only for ≥60% favourites.
WC FORMAT: 48 teams, 16 groups of 3. Only 3 group games per team — every game matters.
ADVANCEMENT SCENARIO TAGS (auto-injected from server):
  QUALIFIED teams with games remaining: ROTATION RISK — fade their ML, fade player props, lean opponent.
  ELIMINATED teams: Do NOT back as favorite. Motivation gone. Youth/rotation players enter. Fade hard.
  MUST WIN teams: Expect all-out attack. High line, pressing, high-tempo. Lean Over 2.5, Over team total, BTTS Yes.
  CAN DRAW teams: May play defensively for the point. Lean Under 2.5, AH+0.5 on underdog, DNB.
Stage edges: VERIFIED — group game 1 is NOT a strong under (recent WCs ~49-51% under 2.5, avg 2.4 goals). Only bet totals with price value. Knockout rounds average fewer goals (2.31/game) — mild under lean.
Venue intel: Denver/KC altitude = Over pre-game + visiting fatigue after 60min. Dallas/Houston/Miami heat = Under 2.5, ET more likely. Atlanta dome = Over lean.
CRITICAL xG WARNING: xG, PPDA, SPI are NOT available. Do NOT invent. Say "xG unavailable" — use devigged implied probability only. Cite only W/D/L, GF, GA, GD, PPG from actual group standings data.
Market priority: AH > Goals Total > BTTS > Shots on Target > Corners > Cards > Anytime Scorer.
Referee: WC elevated card rate 35-40%. VAR conservative. FIFA mandates 6-10 min stoppage time — late goal spike real.
Simultaneous final group games: No tactical manipulation possible. More honest prices. Standard lines apply.`,

    TENNIS: `TENNIS SURFACE PIPELINE: Roland Garros (clay) → Wimbledon (grass, late June–July) → US Open (hard, August).
WIMBLEDON GRASS TRANSITION = THE ALPHA WINDOW (NOW ACTIVE — June/July 2026):
  Books lag 1-2 weeks updating surface Elo. Clay Elo still in models for first 2 weeks of grass.
  Clay grinders MASSIVELY overbet by public rounds 1-2 — FADE them.
  Big servers UNDERVALUED — Back them at premium vs inflated clay-grinder favorites.
  Transition week events (Queen's Club / Halle) = MAXIMUM mispricing. Biggest edge of tennis year.
Wimbledon specifics:
  1st set winner usually wins the match (strong but sample-dependent — do not quote a precise %). Effect strongest on fast surfaces.
  Serve hold ~90% ATP / ~85% WTA on grass. Lean Under total breaks, Under total games.
  Net rushers and serve-volleyers peak value rounds 1-3.
  R1-R2 upsets on grass ~28% — avoid heavy parlays on chalk.
Fatigue rules (non-negotiable):
  5-set match + <48hr turnaround = retirement/injury risk. NEVER bet their ML.
  Deep run previous week = hangover in rounds 1-2 next event.
  Rolling sets >15 in 14 days = HIGH FATIGUE flag. Fade that player.
Niche stats: surface win%, grass-specific Elo (gap >100 = edge, >200 = back with conviction), 1st serve%, ace rate, hold%, break point conversion%, return points won%, rolling match load.
H2H surface rule: H2H on specific surface weight LAST 2 YEARS 3x vs older meetings. Surface changes everything.
Game handicap rule: Favorites at -200+ ML → use -4.5 game handicap instead. Better ROI. At -300 ML you need 75% to break even; -4.5 games usually -130 to -150.
Injury rule: Grass = slick courts = ankle/knee risk. Last-minute scratch HIGH. Confirm warmup before ANY bet.
DATA INTEGRITY: Never cite clay surface stats for grass matches. If grass records not in data, state "grass data unavailable." Do not estimate.`,

    MLB: `⚾ CURRENT: MLB regular season (June 2026). Daily slate — volume betting sport.
Bet types: moneyline, run line (±1.5), totals, F5 (First 5 innings), NRFI, player props (HRs, Ks, hits, RBIs).
Best market: F5 (removes bullpen variance entirely). Back the ace.
Niche stats: ERA, xERA, WHIP, K/9, BB/9, FIP, BABIP, xFIP, Statcast exit velocity, barrel %, hard-hit %, spin rate, release point consistency.
Park factor is non-negotiable: Coors = +20–25% runs. Petco/Oracle = -15–20%. Always cite the park.
Umpire home plate assignment = single most overlooked variable. Tight-zone ump → Under on runs/Ks up. Wide-zone → walks up/Ks down.
Third-time-through-order penalty: most starters see +0.40 ERA bump. Target Over on hits in 5th/6th inning.
Bullpen attrition: team used 3 top relievers in back-to-back games → Win Probability drops ~4% late. Lean Over 7th-9th inning.
Weather critical: wind blowing out 15mph + temp >80°F → Over. Blowing in <60°F → Under. Dome = neutral.
BABIP >.320 sustained = pitcher luck. Regression in 2 weeks. Fade that pitcher.
Road underdogs +1.5 run line: cover ~56% (verified). Only +EV if the PRICE beats that rate — check juice before betting.`,

    NHL: `🏒 CURRENT: Stanley Cup Playoffs (June 2026). Playoff hockey = defense-first, goaltending decides everything.
Bet types: moneyline (full game), puck line (±1.5), totals, period lines (1P), series prices, player props (goals, assists, shots, saves).
Goaltending is #1 variable: SV% <.900 = vulnerable, lean Over. SV% .920+ = elite, lean Under opponent total. Never bet without starter confirmed.
Underdogs +1.5 puck line: cover ~55-58% (verified; road dogs ~52-54%). Heavy juice usually prices this in — only bet when price beats the rate.
Home favorite -1.5: covers only ~38% in playoffs. FADE as parlay anchor. 1-goal games dominate playoff hockey.
Key metrics: Corsi For % (shot attempts), xGF% (expected goals), PDO (SV%+Sh% — regression signal), HDSC (high-danger scoring chances), GSAx (goalie goals saved above expected).
PDO >102 = team getting lucky. Expect regression. PDO <98 = team getting unlucky. Expect positive regression.
Special teams: PP% >25% = elite. PK% >85% = elite. Playoff refs call 20% fewer penalties than regular season.
Totals: playoff Under hits ~56% in games 1-2 of a series. After high-scoring game (7+ goals) → next game Under hits ~61%.
Series betting: Over 5.5 games hits ~55% historically. Goalie matchup determines series winner 70% of the time.
Game 7: Under hits ~59%. Fade the public side. Books shade sharp for Game 7s.`,

    F1: `🏎️ CURRENT: Formula 1 2026 season. Circuit type determines the entire betting approach.
Bet types: race winner, podium finish (top 3), top 6 finish, teammate H2H, fastest lap, DNF prop, constructor podium.
Circuit type is the #1 variable: STREET CIRCUIT (Monaco/Singapore/Baku) = qualifying predicts 80–95% of result. Back pole sitter. POWER CIRCUIT (Monza/Spa) = engine dominant, overtaking common. TECHNICAL CIRCUIT (Hungary/Silverstone/Suzuka) = aero setup critical.
Teammate H2H = cleanest F1 market. Identical equipment. Use FP3 long-run pace to identify better-setup driver.
Niche stats: FP3 long-run pace (fuel-corrected), qualifying gap vs teammate, tire strategy (undercut success ~70%), sector time breakdown, straight-line speed trap, dirty air sensitivity (high-downforce cars suffer most).
Rain = field normalizer. Midfield gains 2–3 grid positions. Fade heavy favorites (they have more to lose). Back underdog top-10 finish.
Sprint weekend: sprint result directly reveals race-trim setup. Adjust all race bets post-sprint.
DNF risk: street circuits 20–40% DNF rate. "Classified finisher" prop has clear value.
Championship pressure: tight battle → drivers race harder = higher DNF risk. Clinched = race management mode, fade them.
Avoid: race winner outright on technical circuits in mixed conditions. Too many variables. Podium finish = better EV.`,
  };
  return ctx[sport] || ctx.NBA;
}

// ── Short heuristics (~500 tokens) for simple endpoints ──────────────────────
export function getShortHeuristics(sport: string): string {
  const sportNote: Record<string, string> = {
    NBA: `🏀 NBA FINALS 2026 SHARP RULES:
- Finals: after road win game 1 → road team covers 54% game 2. After home loss game 1 → home covers 57% game 2.
- Elimination game (facing elimination): home team covers 58%. Back the wall.
- Blowout risk LOWER in Finals. Fade -10+ spreads. Backdoor covers happen less vs regular season.
- Blowout risk STILL real at -12+: fade ALL starter props on fav (garbage-time DNP).
- B2B road team: fade -3.2 pts expected. Finals has no B2B but short-turnaround travel matters.
- Usage spike: star injury/limited minutes → 2nd/3rd options become +EV immediately.
- Ref crew: Scott Foster/Tony Brothers = 44+ fouls/game → lean Over + FT prop Overs.
- On/Off net rating: team drops >8 NetRtg without star = real line value. Cite the number.
- SGP: Team total + player assists positively correlated. 1H spread + 1H total = sharpest market.`,

    WNBA: `WNBA SHARP RULES:
- Books 2-3 yrs behind = systematic mispricing. Pace exploit: Atlanta/Dallas vs slow teams → Over.
- Star removal = prop explosion (rosters only 12 deep). Grab early morning before adjustment.
- B2B commercial travel (not charter) → fade road team props hard.
- Q1/Q2 team totals massively undervalued by books. These are the alpha markets.`,

    NFL: `🏈 NFL OFFSEASON (June 2026) — FUTURES ONLY:
- Best bet right now: Win Total O/U. New HC + playoff-ready roster = Over. Unsettled QB = avoid.
- Super Bowl futures most stale in June. Book models = last season data. Max inefficiency window.
- Preseason (late July): 2H only. Never bet 1H preseason. Fade preseason Overs by default.
REGULAR SEASON (September+) reference:
- Key numbers: 3, 7, 10. Half-point off 3 or 7 = 3-5% win probability swing.
- Wind >15mph: fade all passing props -30%. Wind >25mph = hard Under, lean run game only.
- Bye-week team vs no-bye = +3.2 pts ATS edge (largest in sports).
- Divisional dogs: cover slightly above 50% long-run (verified ~52-54%). Mild lean, not an auto-bet.
- Thursday short-week: -1.7 pts. Books rarely adjust.
- DVOA gap >10 pts = structural edge. EPA/play differential >0.15 = lean that offense.`,

    SOCCER: `WORLD CUP 2026 SHARP RULES (June 11 – July 19, 2026):
- DRAW INSURANCE FIRST: fav ≥60% → ML; fav <60% but better → Double Chance (gana o empata); tight + high draw → Draw No Bet (apuesta sin empate). A win-only pick dies on a draw.
- VALUE GATE: only bet when win prob beats the devigged implied price. Else PASS. Rank win-prob first, value second.
- AH+0.5 = draw insurance when no DC/DNB price. AH > raw 3-way ML.
- xG, PPDA, SPI NOT in any API. NEVER invent them. Use devigged implied probability only.
- Check ADVANCEMENT SCENARIO TAG before every WC bet:
    QUALIFIED + games remain → FADE that team (rotation risk). Back their opponent or skip.
    ELIMINATED → NEVER back as favorite. Youth players entering.
    MUST WIN → Lean Over 2.5, BTTS Yes, Over team total. All-out attack.
    CAN DRAW → Lean Under 2.5, AH+0.5 on underdog. Defensive setup.
- Group game 1: roughly a coin flip on totals (verified ~49-51% under 2.5). No structural under edge — need price value.
- Knockout: Under 2.5 hits ~58%. Draw No Bet > 3-way ML.
- Venue: Denver/KC altitude → Over. Dallas/Houston heat → Under + ET lean.
- Big favorites (-200+) in knockouts: AH-0.5 covers only 56%. Don't blindly lay them.
- Stoppage time 6-10 min (FIFA mandate). Live Over at 85' in close game = real value.`,

    TENNIS: `TENNIS SHARP RULES (WIMBLEDON GRASS WINDOW ACTIVE — June/July 2026):
- THIS IS THE BIGGEST ALPHA WINDOW IN TENNIS. Books still running clay Elo weeks 1-2 of grass.
- Clay grinders: FADE them R1-R2 at Wimbledon/Queen's/Halle — massively overbet by public.
- Big servers: BACK them — undervalued 3-8% vs inflated clay-based lines.
- 1st set winner usually takes the match, strongest on grass — directional only, no precise % verified.
- Serve hold ~90% ATP / ~85% WTA. Lean Under total breaks. Under total games is standard.
- Game handicap (-4.5) > ML at -200+. Better ROI. At -300 ML need 75% just to break even.
- Rolling load 15+ sets in 14 days = HIGH FATIGUE. Fade that player.
- 5-set match + <48hr = retirement/injury risk. Never bet their ML. Hard rule.
- H2H on specific surface only. Weight last 2 years 3x. Clay H2H means NOTHING on grass.
- Grass: ankle/knee risk on slick courts. Confirm warmup before ANY bet. Last-minute scratches common.`,

    MLB: `⚾ MLB SHARP RULES:
- F5 (First 5 Innings) = best market. Removes bullpen variance. Back the ace here, not full game.
- Road underdog +1.5 run line covers ~61%. Safest structural edge in MLB.
- Heavy favorite >-200 ML: actual win rate ~62% vs implied ~67%. NEGATIVE ROI. Always prefer run line or F5.
- Umpire home plate assignment = most overlooked variable: tight zone → Ks up, runs down; wide zone → walks up, runs up.
- Coors Field = +20–25% runs above average. Always lean Over, always fade pitchers here.
- Petco/Oracle/Kauffman = -15–20% runs. Strong lean Under.
- Third-time-through-order: most starters give up +0.40 ERA bump. Target Over hits in 5th/6th.
- BABIP >.320 sustained = pitcher luck regressing. Fade that pitcher next 2 starts.
- Bullpen used 3 top arms in back-to-back games → Win Prob drops ~4% in 7th-9th. Lean Over late.
- Wind out 15+mph + temp >80°F = Over. Wind in 15+mph + temp <60°F = Under. Dome = neutral.`,

    NHL: `🏒 NHL SHARP RULES (Playoff Hockey):
- Road underdog +1.5 puck line covers ~59%. Best structural edge in NHL — use it every time.
- Home favorite -1.5 in playoffs covers only ~38%. FADE as parlay anchor. 1-goal games dominate.
- Never bet without starter confirmed. Backup goalie = instant 0.5–1.0 line swing.
- SV% <.900 = vulnerable goalie. Lean Over total and opponent team total immediately.
- PDO >102 = team getting lucky, regression coming. PDO <98 = unlucky, positive regression ahead.
- Playoff totals games 1-2: Under hits ~56%. Books set them too high early in series.
- After 7+ goal game: next game Under hits ~61%. Goalies tighten, coaches lock down.
- Game 7: Under hits ~59%. Fade the public side — books shade sharp on Game 7s.
- Series price: Over 5.5 games hits ~55%. Rarely sweeps. Goalie matchup = series winner 70%.
- 3-in-4 nights: third game in four nights → lean opponent ML and Over.`,

    F1: `🏎️ F1 SHARP RULES:
- Circuit type decides everything. STREET CIRCUIT = back the pole sitter (80–95% win prob). POWER CIRCUIT = follow engine advantage. TECHNICAL = best aero team wins.
- Teammate H2H = cleanest F1 market. Use FP3 long-run pace to pick side. Identical equipment removes car variable.
- Rain = field normalizer. Midfield gains 2–3 positions. Fade heavy favorites. Back underdog top-10 finish.
- DNF props: street circuits 20–40% DNF rate. "Classified finisher" has clear value on Monaco/Singapore/Baku.
- Sprint weekend: sprint result reveals race-trim setup directly. Adjust all race bets post-sprint.
- Championship pressure: tight title race → drivers race harder early laps = higher DNF risk for leaders.
- Podium finish (top 3) = better EV than outright winner. More coverage, same directional edge.
- Never bet race winner outright on technical circuits in mixed conditions. Too much variance.`,
  };

  const common = `
UNIVERSAL SHARP RULES: (0) RANKING LAW — order every pick list by win probability FIRST, edge second. Favor likely winners over +EV longshots.
(1) EV over narrative — find mispriced probability, not just winners.
(1b) SCAN ALL MARKET TYPES — compare ML / spread / total / team total / BTTS / derivative / the sport's niche PLAYER PROPS by win-prob and take the best TYPE; never auto-default to the moneyline. Float a prop only when real player stats are present, else call it a "lean".
(2) Injury first — missing star = reprice the line. (3) Pinnacle gap ≥8 pts = follow it.
(4) Juice filter — skip if vig >15%. (5) Caveman output — cite numbers, no fluff.

SGP CORRELATION STRESS TEST: Every leg MUST positively correlate or be uncorrelated.
NEVER pair: Team Win + Opponent Star Over (unless spread ≥12). BTTS Yes + Under 2.5 Goals (contradictory).
Anti-vig filter: total parlay juice >15% → reject and simplify.`;

  return `${common}\n\n${sportNote[sport.toUpperCase()] || sportNote['NBA']}`;
}
