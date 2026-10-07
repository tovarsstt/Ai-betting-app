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
