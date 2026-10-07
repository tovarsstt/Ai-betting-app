# Engine v2 ("motor rejuvenecido") — what is used, what is not, and the measured gain

Entry point: `python3 scripts/engine_v2.py selftest | bench | scan | nflwind`
Modules: `engine_v2.py` (pipeline) · `tennis_vec.py` (numpy + Numba point-by-point kernel) · `betting_math.py`
(de-vig, scoring, calibration, Kelly-with-uncertainty) · `stochastic_engine.py` (heuristic injection, Hawkes, NB,
GPD, chi-square) · `heuristic_calibration.py` · `tennis_price_backtest.py` / `hier_fit.py` (the evidence).

## Measured improvement (640 held-out matches, later in time than the fit data, real closing prices)
| What | Before (iid sim) | v2 | Change |
|---|---|---|---|
| Games-margin ladder, Brier | 0.1681 | 0.1655 | -1.55% |
| Games-margin ladder, log-loss | 0.5069 | 0.4995 | -1.46% |
| Handicap Brier vs market (market 0.2523) | 0.2630 (4.2% worse) | 0.2518 (0.2% better) | -4.3% |
| Handicap, edge>=5% bets ROI | -8.3% (n=218) | +6.9% (n=83, noisy) | |
| Totals Brier vs market (0.2504) | 0.2513 | 0.2504 (parity; blend 0.2500) | -0.4% |
| Totals mean bias | +1.3 / +1.9 games (ATP/WTA) | +0.07 / +0.56 | offset fudge -96% / -74% |
| Speed | ~111k matches/s | ~1.7M/s end-to-end, ~9M/s steady state | 16x - 80x |
| De-vig log-loss, 60k tennis closing lines | 0.5526 (simple) | 0.5493 (power) | -0.6% |

Honest reading: v2 does NOT create an edge — the market stays efficient on tennis handicaps/totals (model ≈ market).
What it does is stop the OLD engine from inventing edges (e.g. "Zhou wins a set" was +2.8% EV with 14 matches of
data; v2 prices it -8.6%) and size what is left with uncertainty-aware Kelly.

## USED (and why)
- Hierarchical day-to-day serve-rate sd = 0.05 — fitted out of sample, and independently measured at 0.055 ATP /
  0.051 WTA on 13,100 charted player-matches. Replaces the 1.26 margin multiplier and most of the totals offset.
- Per-player sd = sqrt(day_sd^2 + se^2): players with 12-14 matches of data get fatter tails automatically.
- Numba kernel, antithetic draws (variance -21% on tail estimates), parallel across cores.
- Power de-vig (tennis log-loss -0.6% vs simple). 50/50 model-market blend (best Brier on handicaps and totals).
- Kelly with posterior uncertainty (stake shrinks to 0 when the edge doesn't survive the spread).
- GPD tail risk (CVaR of drawdown) for repeated tickets; exact negative-binomial / k-streak maths (verified vs 2.4M sims).
- NFL wind -> Under (validated): wind >=15 mph, closing total: Under 57.9% (n=618, 1990-2016) and 68.5% (n=73, 2017+),
  break-even 52.4%. CAVEAT: the sample uses the wind recorded at the game; forecasts are noisier, so the live edge is smaller.
- Context heuristics only when calibrated (`data/heuristic_coefficients.json`): only `wind_scoring` is.

## NOT USED (and why)
- Shin de-vig: no better than power/additive on 6.2k football and 60k tennis lines (diff <0.001 log-loss). Kept in the kit.
- Isotonic / beta / Platt calibration on market prices: closing lines are already calibrated; isotonic made it WORSE
  (log-loss 0.5912 -> 0.6026), beta/Platt ≈ 0. Kept for model outputs.
- Hawkes / negative-binomial for goals: total goals given the market-implied lambda are Poisson (chi-square p=0.10;
  NB shape -> infinity, LR=-0.2). Kept in the engine (alpha=0) for in-play work when minute-level data exists.
- Rest / back-to-back (NBA 22.8k games, NHL 29.4k): not significant vs the closing line (t<1.1, held-out MSE gain ~0).
- NFL cold/precipitation: not stable out of sample. Birthday / personal goals / pressure / altitude: NO outcome data
  anywhere -> coefficient 0 (mechanism exists; an invented effect size would be a fabricated edge).
- EVT for the model, GARCH, TDA, SEM, transfer entropy, genetic algorithms, GPU/CuPy, DBN/MRF/copulas, Cox, random
  forests: no data-supported use in this pipeline; they add parameters the data cannot pin down.
- Parlays of handicap legs: structural hold ~14% for 2 legs (Stake handicap margin 7.9% per leg vs 4.3% on ML).

## Known limits
- Serve stats are a current snapshot applied to 2025 matches (lookahead); margin tails/totals are far less sensitive to it.
- The handicap price test has n=83-115 qualifying bets: ROI figures are noise-level; Brier/log-loss are the reliable numbers.
- The Kaggle handicap columns are in the source's player order (see `align_handicap`).

## Context effects (rest / fatigue / narratives) — unbiased test, 2026-10-07
Design: frozen hypothesis list, Holm correction, features from strictly earlier matches only, effects measured as an
OFFSET on the de-vigged closing price (incremental to what the market already believes), random A/B orientation,
fit <=2022 / replicate >=2023, accepted only if significant in BOTH periods with the same sign.
`scripts/context_effects_tennis.py` -> `data/tennis_context_coefficients.json`, applied by `engine_v2.context_effect`.

| Effect (217k tennis win rows, 88k totals rows) | Result |
|---|---|
| Days since last match (cap 7) | **ACCEPTED**: -0.018 logit/day (train p<1e-4, test p=6e-4). Match rhythm, not fatigue: the longer layoff does slightly WORSE than the price says. 5 extra days ≈ -0.09 logit (~2 pts). |
| Games played last 7 days | **ACCEPTED**: +0.0075 logit per 10 games (p=0.0003 / 0.002). Tiny. |
| Altitude >=500 m | **ACCEPTED**: +0.46 total games (p=0.0002 / 0.005). |
| Back-to-back day (<=1 day rest) | Not beyond the price. 95% CI -0.011..+0.043 logit (±1 pt). |
| Long previous match | Significant on train, did NOT replicate (test p=0.50) -> 0. |
| Birthday | Underpowered (269 ATP birthday matches): CI -0.16..+0.35 logit. Can't rule out ±8 pts, can't detect it either -> 0. |
| NBA back-to-back (22.8k games) | ATS residual -0.02 / +0.24 pts (t=-0.1/1.1): already in the line. |
| NHL back-to-back (29.4k games) | totals residual ~0 (t=0.3): already in the line. |

Reading: rest/back-to-back effects are REAL — and the market already charges for them (that is why the residual is ~0).
Injecting them again would double count; only the measured incremental parts above enter. Personal goals / pressure /
press index have NO outcome data anywhere -> reported, never applied.

## Per-sport score math (calibrated on each sport's own closing lines) — `scripts/sport_math.py`
Market-anchored (closing total + de-vigged moneyline/spread fix the two team means); each sport then gets the
distribution family its scoring process has. Fit on the earliest 60% (or earlier seasons), judged on the rest.
API: `sport_math.price_game(sport, total, p_home, line=, total_line=, p_draw=)`; parameters in `data/sport_math_calibration.json`.

| Sport (n) | Family fitted | Finding | Gain |
|---|---|---|---|
| MLB (2,512) | negative binomial | runs are heavily over-dispersed: shape r≈3 (Poisson is badly wrong) | **+0.41 nats/game** held-out log-lik |
| NBA (18,537) | Normal margin & total | sigma_margin 11.77, sigma_total 17.47, corr(margin,total) -0.01; sigma falls 0.12 per spread point; Student-t nu=18.5 | spread->win prob (Normal) beats the de-vigged ML: log-loss 0.6103 vs 0.6118 |
| NFL (9,374) | empirical key-number residual pmf | sigma 13.29; alt lines priced with the empirical residuals | Brier on alternative lines 0.2256 vs 0.2261 (Normal) |
| NHL (2,847) | Poisson | no over-dispersion once market means anchor it (NB r->600, bivariate 0) | none needed |
| Soccer (6,166) | Poisson (+ diagonal inflation for 3-way) | Poisson under-prices draws (23.1% vs 25.05%); diag-inflated Poisson reproduces market 1X2 exactly, but Dixon-Coles tau dumps the extra mass on 0-0 (7.7% vs 5.9% actual) -> rejected | pricing parity: AH half-lines paired t=0.14..1.3, O/U parity |

Derived-market tests (price a market the model was NOT fitted on, vs the real price): NHL puck line Brier 0.2177 vs market 0.2179 (parity);
soccer Asian handicap (true half-lines only) parity; MLB run line calibrated (NB 0.2391 vs Poisson 0.2398).
A first soccer AH result of "+9% ROI" was an ARTEFACT: quarter lines (-0.25/+0.75) pay half and were scored as full
win/loss. Only true half-point lines are valid for a binary cover test.

## One engine, one niche per sport — `scripts/engine_all.py`
`python3 scripts/engine_all.py registry` lists, per sport: the fitted family, VALIDATED context effects, variables found
ALREADY PRICED (with the 95% CI of what the data can rule out) and variables UNTESTED for lack of data (applied as 0).
`engine_all.py <sport> --total --p-home --line --total-line [--wind] [--cover-odds a,b] [--over-odds a,b]` prices every
market, applies only validated context (NFL wind), blends with the de-vigged market and sizes Kelly with uncertainty.
Context sweep (`scripts/context_effects_sports.py`, Holm + train/test replication): soccer rest / short rest / referee,
NFL rest / short week / bye / divisional / Thursday / dome, NBA back-to-back / 3-in-4 / Denver-Utah altitude — NONE
replicated beyond the closing line (CIs in data/sport_context_coefficients.json). Tests: `python3 -m pytest tests/test_engine_math.py`.

## Heterogeneity: "the Steelers don't play the Ravens like the Bucs" — `scripts/heterogeneity_tests.py`
A pooled test can say "no average effect" while team/matchup effects exist and cancel. So test them directly, past-only:
matchup persistence (does THIS pair's past residual vs the closing line predict its next meeting), team persistence, and
favourite-size interaction, with first-half / second-half replication.
| | NFL | NBA | Soccer (5 leagues) |
|---|---|---|---|
| Matchup margin persistence | +0.06 (t=1.9) | 0.00 | +0.02 |
| Matchup total persistence | -0.02 | +0.02 | -0.01 |
| Team margin persistence (all history) | +0.26 (t=3.1, but sd of past mean only 1.2 pt -> <0.3 pt adjustment) | +0.08 (n.s.) | 0.00 |
| Betting the "hot"/fading the "cold" team (last 32 games) | ATS 49.3% / 49.5%, ROI ≈ -6% | - | - |
Reading: the market already knows each team and each pairing; the persistence that exists is too small to beat the vig.
Literature on rest -> injuries is MIXED (PubMed): NBA game injuries not associated with back-to-back or 4-in-5 alone (away games are);
NFL Thursday/short rest had FEWER in-game injuries (1.26 vs 1.53 per team-game); soccer 2 matches/week 25.6 vs 4.1 injuries/1000h at one
Champions League club, but 8 matches in 26 days showed no injury increase at another. Injuries move results through availability, which
the closing line prices once known.

## Team ratings for every league (offence / defence / team-specific venue edge / weather / pace) — `scripts/team_ratings.py`
Time-decayed ridge (hierarchical shrinkage), refit every 28 days, walk-forward on the last 40% of each league, tuned half-life and ridge,
tested against the league's own closing line. Question: does (model - line) predict (result - line)?
| League | n | Margin MSE line / model / blend | slope of residual on (model-line) |
|---|---|---|---|
| NFL (+wind/cold/dome, +team venue edge) | 3,750 | 167.7 / 182.8 / 171.3 | +0.02 (t=0.4); totals with weather: +0.04..+0.05 (t≈0.6) |
| NBA (+team venue edge) | 9,126 | 176.7 / 195.4 / 181.7 | -0.04 (t=-1.1) |
| Premier League | 537 | 2.64 / 2.72 / 2.65 | +0.14 (t=0.7) |
| La Liga | 533 | 2.04 / 2.13 / 2.06 | -0.06 |
| Bundesliga | 413 | 3.11 / 3.36 / 3.20 | -0.51 (t=-2.0) |
| Serie A | 536 | 2.03 / 2.16 / 2.07 | -0.22 |
| Ligue 1 | 456 | 2.90 / 3.06 / 2.95 | -0.11 |
Reading: in all 7 leagues the ratings model is 5-10% WORSE than the line and what it disagrees with the line about carries no signal. Team
strength, venue, weather and pace are already in the closing price. Use ratings where there is NO sharp line (alternative markets, props,
thin leagues, openers) as the prior; where a line exists the line is the model. `scripts/recalibrate.py` re-fits everything and reports drift.

## Player availability (who plays) — NBA, 6,251 games, 5 seasons — `scripts/player_availability_nba.py`
From ESPN box scores (free summary API) + closing lines: each player's expected minutes and Game Score/min from EARLIER games only; per team-game
"talent missing" = sum over rotation players (exp. minutes >= 15) who did not play. Sanity: it explains the REALISED margin (beta +0.29 pts/unit,
R2 4.7%, p<1e-4 in both periods) — so the proxy is real. Against the CLOSING line: residual beta +0.025 (p=0.09) -> the market already prices ~91% of it.
Rotation players out: +0.21 pts each (p=0.014; fit seasons +0.13 p=0.27, test +0.31 p=0.014) — shrank from +0.39 when the sample doubled (regression to 0).
Totals: +0.053 pts per unit of missing talent (p=0.002 on 2022-24; same sign p=0.22 on 2025-26): the line may over-lower totals for absences. Both are WATCH
items, not validated. Betting the healthier side when the opponent misses >=3 more rotation players: ATS 53-55% (n=260/252), ROI +1.4%/+4.3% (se ±6%).

## NFL starting quarterback — `scripts/qb_effects_nfl.py` (3,461 games, 2012-2025, ESPN box scores + closing lines)
Starter = most pass attempts; quality = past-only shrunk adjusted yards/attempt (prior = league AY/A worth 250 attempts).
Sanity (realised margin): +4.45 pts per AY/A unit (R2 7.5%, both periods); a backup starting costs ~5 points (R2 3.4%).
Against the CLOSING line: QB quality residual +0.46 pts/unit (p=0.056; fit +0.72 p=0.03, test +0.17 p=0.6) -> the market prices ~90%.
Backup / unusual starter (corrected wording): the backup team's residual vs the line was -2.4 pts in 2012-19 (95% CI -3.6..-1.2) and -0.9 pts in 2020-25 (CI -2.0..+0.3);
the trend is +0.13 pts/yr (p=0.27), so "the edge decayed" is NOT proven — it shrank and the recent sample cannot tell 0 from -2. Betting against the backup team
wins 53.5% pooled (n=960, one-sided p=0.25 vs break-even 52.4%). The heavy-favourite cut (|line|>=7: 55.5%, n=339) was found after examining 8 cuts: raw p=0.14,
Bonferroni p=1.0, and 58.4% -> 52.6% across the two eras — treated as noise.
FIX = forward testing (`scripts/forward_tests.py`, ledger `data/forward_ledger.json`): the rules were frozen on 2026-10-07 and are scored ONLY on games that
were never analysed (2026 season, 64 NFL games ingested so far), at the posted price, with a Bonferroni threshold; WATCH until n>=150. First count:
fade-backup n=30, 36.7% (ROI -30%, far below break-even — early-season QB turnover inflates the "backup" flag), heavy-fav n=7 (71%, meaningless at n=7), wind-under n=0.

## Fixes after the first review round (2026-10-07)
1. **Backup-QB flag was wrong, not the market.** The v1 flag compared a QB with last season's last 6 games, so every new franchise QB in weeks 1-3 became a "backup"
   (26 of 32 flagged 2026 games were false positives). v2 uses the SAME-SEASON modal starter (>=3 earlier games). Corrected study (785 games): the opponent of the
   backup team covers 57.3% (90% CI 54-60, p=0.003, ROI +9.4%); 2012-19 59.8%, 2020-25 54.8% (ROI +4.6%, p=0.19); the backup team's residual -3.1 pts -> -1.3 pts
   (95% CI -2.5..-0.02), trend +0.18 pts/yr (p=0.12). |line|>=7 vs <7: 56.9% vs 57.6% -> the "heavy favourite" story was noise. The definition was changed after
   seeing data (for a logical reason), so in-sample numbers are optimistic: re-registered as forward rule v2, counted from 2026-10-08 (stake 0; ~3.5 qualifying games/week).
2. **Wind rule tested with FORECAST wind** (`wind_forecast_validation.py`, 705 outdoor games 2022-25). Open-Meteo wind and the recorded-wind feed are NOT on the same scale
   (corr 0.72, R2 0.51; recorded>=15 mph ≡ Open-Meteo >=13.2 mph by exceedance share). Mapped to the recorded scale, tradeable forecast: >=12 mph Under 58.3% (n=144, p=0.09),
   >=15 mph 50.8% (n=63), >=18 mph 42.1% (n=19). The slope of (total-line) on RECORDED wind is negative in every era (-0.15..-0.53 pts/mph, 2022-25 p=0.03), so the physics holds,
   but the 15+ mph betting rule did not survive a tradeable measurement -> WATCH. `nflwind` and the forward rule now use the calibrated scale.
3. **App path wired to v2.** `tennis_games_model.predict()` (what the app's tennis endpoints call) now uses engine v2 for best-of-3 (hierarchical sd, Numba, per-player sd from
   the serve-sample size, v2 totals offsets; no extra margin multiplier), legacy for best-of-5. Same output schema plus `engine: "v2"|"legacy"`; 0.06 s per call after warm-up.
