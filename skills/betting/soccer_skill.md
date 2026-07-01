# SOCCER / WORLD CUP 2026 — NICHE HEURISTICS v3.0
# ⚽ WORLD CUP 2026 PRIMARY — June 11 → July 19, 2026

---

## FORMAT
- 48 teams. 16 groups of 3 (top 2 advance + 8 best 3rd-place = 32 in knockouts).
- CRITICAL: Only 3 group games per team. Every match matters. No "rest" games.

---

## STAGE-SPECIFIC EDGES

### GROUP STAGE
- First group game: Teams conservative. Under 2.5 hits ~62% in WC match-day 1.
- Final group game with elimination stakes = HIGH VARIANCE. Lean Over when both teams need points.
- Teams already through by game 3 = rotation risk. Fade player totals hard.
- Teams eliminated = no motivation. Fade ML/AH entirely.
- Simultaneous final group games: No tactical manipulation possible. More honest prices.
- Group stage Under 2.5 overall: ~55% across WC history.

### KNOCKOUT ROUNDS
- Teams play to survive. Under 2.5 hits 58% in knockout stages historically.
- 0-0 at 70 min = live Under signal. Teams protect the point.
- Draw + ET/PKs probability increases. Asian Handicap AH+0.5 = draw insurance.
- Big favorites (-200+) in knockouts cover AH-0.5 only 56%. Don't blindly lay them.
- Draw No Bet > 3-way ML every knockout match.

---

## VENUE INTELLIGENCE (auto-injected by server — always available)
- **Denver/KC ALTITUDE**: Lean Over pre-game, visiting team fatigue in 60+ min.
- **Dallas/Houston/Miami HEAT**: Lean Under 2.5, ET more likely (tired defenders).
- **Atlanta DOME**: Full Over lean, no weather, highest-scoring WC venue.
- **Seattle RAIN**: Slower play, lean Under on shots/totals.
- **South Americans** acclimatize better to US heat. Edge in Dallas/Houston vs European teams.
- **Europeans** 6hr jet lag → slow starts in game 1. Lean 1H Under.

---

## NICHE STATS — WHAT TO CITE (real only)
- W/D/L, GF, GA, GD, PPG from group standings (live in context block).
- Goals/game = GF ÷ GP. Clean sheet rate = 1 − (GA ÷ GP). Both derivable from context.
- **xG, PPDA, SPI NOT available from API. Do NOT invent. Say "xG unavailable" and use devigged implied prob instead.**
- When odds imply 65% but team is 1W-1D-1L with GD of 0 → fade the implied prob.

---

## UPSET / PUBLIC-TRAP RADAR (read first)
A "name" favourite the public backs like an 80% lock (Canada, Brazil–Morocco,
Panama–Ghana) is rarely that safe. Trust the **market's devigged win %**, never
the narrative — the public being heavy on a side is a FADE signal, not proof.
`/predict-soccer` returns `upset_risk` (LOW / ELEVATED / HIGH) from market
structure: modest favourite + live draw, real underdog equity, high non-win
probability, and "chalk illusion" (priced shorter than the true prob). When
ELEVATED/HIGH:
- Do NOT headline the straight Win. Default to Double Chance / Draw No Bet, or
  the underdog at +value.
- If you still back the favourite to win, cut to 0.5u.
- Tournament one-offs (group deciders, knockouts) raise the base upset rate —
  motivation and parity are higher than club ball.

## DRAW INSURANCE — THE CANADA LESSON (read first)
Soccer is a **3-way** market. A team can be *better* and still NOT win → a
straight Win/ML ticket dies on the draw. But the pick must also have VALUE —
draw insurance is only worth taking when its PRICE pays for the risk. Price the
draw, then pick the market that both survives the draw AND clears the value gate:
- **HEAVY chalk favourite (≈ -250 / 1.40 dec or shorter — e.g. -511)** → ML and
  DC have NO value (DC pays ~1.05, you lay a fortune for pennies). Do NOT headline
  them. Take the value in the **derivative the fav wins BY**: handicap -1.5 / -2.5,
  team total Over, correct score, winning margin. If none clears value, **PASS**.
- **"Better but not dominant" (~ -110 to -250) AND draw ≥26%** → **Double Chance
  (gana o empata, 1X)** when it pays ~1.40–2.50 and beats its devig. Cashes on
  win OR draw — the play we missed on the Canada draw.
- **Tight match (win≈lose) + high draw** → **Draw No Bet (apuesta sin empate)**.
  Refund on the draw, only loses if the dog actually wins.
- **Underdog with real equity** → the dog ML / DC (X2) at +value can be the best
  bet outright. A live dog at a fat price beats laying chalk.
- Straight Win/ML is a candidate ONLY when its price isn't crushing juice AND
  carries real +EV over the draw risk.
- Engine: `POST /predict-soccer` (edge_api, port 8001) returns the full board
  (1X2 / DC / DNB / O-U / BTTS / corners / correct score) + the recommended
  draw-insured pick. Built on bivariate Poisson + Dixon-Coles (calibrates 0-0
  / 1-1 draws). `markets.correct_score` gives the top 10 exact scorelines with
  fair odds — the swarm's "simulation" section must cite THESE, never invent
  a score line. A `simulation` block (Monte Carlo cross-check, `scripts/poisson_model.py`)
  also ships alongside it — same matrix, useful for correlated same-game
  markets (e.g. home win AND BTTS) that the closed form can't give jointly.
  Generic version (any sport, caller-supplied lambdas): `POST /simulate-match`.
- **No-odds fallback is now DATA-FIT, not a hand-tuned heuristic.** When full
  1X2 odds are missing, lambdas come from `poisson_regression.py` — a
  multivariate Poisson GLM (log link, ridge-regularized, time-decayed) fit
  jointly over ~260 national teams from real match results (real dataset:
  github.com/martj42/international_results, 49k+ verified internationals
  1872-present, cached at `data/soccer/international_results.csv`). Response
  field `lambda_source: "data_fit_poisson_regression"` marks when this fired
  vs `"ratings_heuristic"` (old static default, last-resort only) vs
  `"market_calibrated"` (odds present — always wins when available).
  `data_fit_ratings` in the response also carries each team's Keener
  eigenvector strength rating (`eigen_ratings.py` — real linear algebra:
  power iteration to the dominant/Perron eigenvector of a goal-share
  dominance matrix, so beating a strong team counts for more than beating a
  weak one, self-consistently). Refresh the fit periodically:
  `python3 scripts/fetch_international_results.py && python3 scripts/fit_soccer_ratings.py`
  then restart edge_api.py. Never fit on stale-cached data silently — rerun
  fetch first.

## MARKET PRIORITY (sharpest → softest)

**Double Chance / Draw No Bet** — primary draw insurance (see above).
- DC 1X/X2 = win-or-draw. DNB = win, draw refunded. Use per the rules above.

**Asian Handicap (AH)** — prefer over raw 3-way ML when no DC/DNB price.
- AH +0.5 underdog = draw insurance. Covers ~55% in WC.
- AH 0.0 = Draw No Bet equivalent. Best for "better but not dominant" spots.
- 1H Asian Handicap: sharpest WC derivative. Books set stale overnight. Alpha zone.

**Goals Total**
- Over 2.5: Only when both teams attacking AND group stakes force open play.
- Under 2.5: Default in knockouts. Default in conservative group game 1.
- 1H Under 1.5 goals: 62% in WC group stage. Start cautious every time.

**BTTS**
- Yes only: GF/GP > 1.2 for BOTH teams AND neither eliminated/secured.
- Never BTTS in knockout conservative setups.
- Never pair BTTS Yes + Under 2.5 (contradictory — instant reject).

**Shots on Target / Corners**
- SoT Over: Books use static models. 59-62% historical win rate. Best prop in soccer.
- Corners Over: High-crossing teams vs low blocks. Dominant home-region team.

**Cards / Anytime Scorer**
- Cards: WC elevated card rate (~35-40% "player to be carded" hit rate).
- VAR conservative in WC (clear & obvious standard). Fewer soft penalties. Don't over-fade cards.
- Stoppage time: FIFA mandate 6-10 min now. Late goal spike real. Factor into live Over at 85'.

---

## REFEREE INTELLIGENCE
- Referee nationality: Same-confederation ref → subtle favoritism in 50/50 calls.
- Card-heavy WC refs (avg 5+ yellows/game): lean Over on cards.
- Aggressive MF vs skill winger = yellow card play. Most reliable WC prop.

---

## SQUAD DEPTH / FATIGUE
- 4th game in 20 days = fatigue. Fade team totals.
- European teams: 6hr jet lag, first game slow start.
- Rosters 26 players (expanded). Rotation possible in group game 3 for qualified teams.
- Key player "carrying a knock" in press conference = fade their Over props.

---

## SGP RULES
- **Group Stage (both need points)**: Team Win AH + BTTS Yes + Over 2.5 Goals.
- **Knockout (heavy fav, conservative)**: Team Win + Under 2.5 Goals + Anytime Scorer (striker).
- **Safe add**: Player to be Carded (aggressive MF). ~37% hit rate.
- **Never**: Exact score in knockouts. BTTS Yes + Under 2.5. Total vig >15%.

---

## CHAOS DETECTOR + DRAW SCORE (deterministic — chaos_engine.py)
Runs on every WC match with a favourite. The DRAW SCORE (0-1) is built only from
real data, renormalized over whatever is present (never invented):
- **Parity** — small gap in the devigged 1X2 + title-strength prior.
- **Low-scoring** — both teams low GF/game (goals scarce → draw/under).
- **Motivation** — CAN_DRAW / QUALIFIED (rotation) advancement tag.
- **Model gap** — Dixon-Coles draw% > market devigged draw% = underpriced draw.
- **Injury/news nudge** — key attacker out → +draw/under, ±5% cap, cited; skipped when no data.

CHAOS grades: **LITE** (mid fav 1.50–1.90, underpriced draw → X / Double Chance),
**FULL** (heavy fav ≤1.50 overpriced + live dog → dog / X2, Wild tier only).
The draw is a PICK only when model draw% > market draw% AND the draw price clears
the value gate — else it's a note. This is the Canada-draw fix, grounded in stats.
Lineups/injuries: use ESPN injuries + news when present (cited soft nudge); no
predicted-XI feed exists, so never fabricate one. Club-vs-country form is not
modelled (no clean data) — soft cited nudge only.

---

## LIVE / IN-PLAY DISCIPLINE (from the Argentina–Algeria 0-0 case)
The pre-match model EXPIRES at kickoff. In-play, re-price from scratch — never
bet a live number off the kickoff read.
- **Live model = time-decayed Poisson.** Remaining λ = pre-match λ × (minutes
  left ÷ 90); rebuild the score matrix and OFFSET by the current score. That is
  the only honest live fair price — no invented in-play numbers.
- **In-play vig is wider (~7%+ vs ~5% pre-match).** The book reprices in
  milliseconds off the same events you see — you are a step behind. A live
  favourite ML is usually the WORST spot on the board.
- **The scoreless clock hurts the favourite.** Every 0-0 minute pushes the draw
  UP and drifts the favourite's fair price OUT (ARG fair 1.62 → 1.77 by min 15)
  while the book still dangles the short pre-match-ish price. Laying a live
  favourite at a "good" number gets worse, not better, as time burns.
- **Don't tap during VAR / celebrations.** Markets suspend and reprice garbage;
  goals get chalked off. This game had BOTH sides' goals ruled offside back to
  0-0 — anyone who chased a swing got whipsawed for nothing.
- **Down a goal ≠ value just because the team is better.** From 0-1 at ~min 13
  the stronger side is only ~31% to win and FALLING — a deficit needs net +2,
  which class does not refund cheaply. Comeback-chasing is the trap's 2nd costume.
- **Discount one-directional model edges in-play — the model runs HOT on the
  leading favourite.** Static λ-decay ignores game-management (favs protect
  leads) and chasing variance (dogs throw bodies forward). At ARG 1-0 / min 20
  the model had ARG win 86% vs market devig 77%, and *every* model "edge" pointed
  the same way (Unders, BTTS-No, ARG handicaps). When all edges align with the
  model's known bias, that's bias, not value — trust the sharp live market.
- **Act only on a quantified +EV across the FULL board (global rule 5), never
  the ML by default.** Nothing clears the value gate → the live play is PASS.
  Patience through chaos IS the edge.

---
*Soccer v3.1 — Caveman Locks. World Cup 2026.*
