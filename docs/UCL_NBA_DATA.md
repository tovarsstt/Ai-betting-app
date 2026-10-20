# UCL + NBA data layer (what it does, what it does NOT)

Scripts: `fetch_europe_data.py` (ClubElo, NL/PT/TR/BE/GR/SCO results, ESPN NBA scoreboard) ·
`ucl_model.py` (cross-league pricing) · `nba_stack.py` (stacked ensemble + walk-forward backtest).
Tests: `scripts/test_europe_ucl_nba.py` (11, no network).

## Run order (needs a connection that can reach these hosts; the build sandbox could not)
    python3 scripts/fetch_europe_data.py clubelo
    python3 scripts/fetch_europe_data.py extra-leagues
    python3 scripts/fetch_europe_data.py nba 2025-10-21 <today>
    python3 scripts/nba_stack.py

## Verified here
- 11 new tests pass; 67 existing soccer tests still pass.
- Poisson calibration recovers known (a,h,b) from synthetic data.
- NBA walk-forward 2024 (n=1321): Elo 0.6179, stacked 0.6118 log-loss; diff -0.0062, 95% CI [-0.0132, +0.0010]
  -> NOT statistically significant. Scored vs Elo, not the closing line.

## NOT verified
- ClubElo / football-data / ESPN endpoints and schemas were NOT called (sandbox blocks them). Parsers are written
  from the documented/known formats and tested on fixtures only; first real run may need tweaks.
- `ucl_model` uses UNCALIBRATED priors (outputs say `calibrated: false`) until `calibrate()` is run on fetched
  results; club-name matching between ClubElo and football-data names is not yet mapped.
- No closing-line data: no claim of betting edge. ENGINE_V2.md found NBA rest/B2B not significant vs closing line.
- Slovan/Sabah/Slavia depend on ClubElo coverage (unchecked).
