# COMPARATIVE PROFILE — MASTER SPEC (ALL SPORTS)
# Caveman Locks. Replicate the tennis 4-dim approach for every sport.
# RULE #0: information is power, but REAL data only — never hallucinate a stat.
# RULE #1: confirmed day-of data (injury, lineup, rest, weather) OVERRIDES history.

Every match analysis compares BOTH sides across the sport's dimensions, converts to a
real probability, and compares to the devigged market. Missing side → build a profile
from REAL data + cite it; if none exists, say "no data — not estimating" and lean on
market + context. ([[feedback_profile_on_demand]])

Status key: ✅ built · 🔜 buildable now (data in hand) · ⛔ needs a feed we don't have.

---

## TENNIS ✅ (live)
Engine: `fetch_tennis_form.py` → `tennis_form.json`; nudges in `edge_api` TENNIS branch.
Dimensions:
1. **Surface profile** — surface win% affinity (clay/grass/hard), transition windows.
2. **H2H** — recency-weighted, SAME-SURFACE when available.
3. **Clutch** — deciding-set + tiebreak win% (✅). break-point%/aces/1st-serve% ⛔ (Sackmann blocked — needs paid feed).
4. **Psych & form** — comeback-after-losing-set-1, recent form, streak.
Overrides: day-of fitness; **schedule/tank risk** (small event + big event <5 days away → fade). ([[feedback_tennis_schedule_tank]])
Source: tennis-data.co.uk.

## SOCCER / WORLD CUP ✅ (live, context layer)
Engine: `fetch_soccer_form.py` → `soccer_form.json`; attached to `/predict-soccer` as `profile`.
Markets stay **market-calibrated** (Poisson fit to devigged 1X2 — sharper than our club
ratings for nations). Profile is the comparative READ:
1. **Form** — recency × competitiveness weighted ppg, win%, last5, streak (friendlies down-weighted 0.5, finals up 1.5).
2. **Attack/Defense trend** — GF, GA, clean-sheet%, failed-to-score% (drives Over/Under, BTTS, team totals).
3. **Scoring profile** — over2.5%, BTTS% (real rates for SGP legs).
4. **H2H** — recency-weighted W/D/L + avg goals + last meeting.
5. **Rest / congestion** ⚠️ live read — group-stage rest gap (fewer days since last match = fatigue edge); compute from the REAL schedule, not history.
Overrides: confirmed XI, injuries, rest days, weather. Club-vs-country fatigue.
Source: martj42/international_results (incl. 2026 WC fixtures).
Fix shipped: name-mismatch (e.g. "USA" vs "United States") no longer kills the board when odds are present.

## NBA 🔜 (data in hand, not yet wired)
Source: LOCAL `data/nba_historical.csv` (game logs) + current off/def/pace ratings.
Dimensions: net-rating differential (have); **recent form** (last-10 ATS/SU, point diff);
**rest** — back-to-back / 3-in-4 fatigue, days rest, travel/altitude; **pace & matchup**
(pace-up vs pace-down, 3PA rate, rim pressure); **H2H/scheme** this season; **clutch**
(net rtg in clutch, FT%); **availability** (star in/out — day-of override). Build next.

## WNBA 🔜/⛔ (ratings only locally)
Same dimension set as NBA. Needs a WNBA game-log feed (ESPN API) for form/rest/H2H.

## NFL ⛔ (needs game-log feed)
Have ppg/pag/net only. Dimensions: EPA/play off & def, success rate, pass vs rush splits,
pressure & sack rate, explosive-play rate, red-zone & 3rd-down %, turnover margin,
**rest** (bye, short week / Thursday, travel/time-zone), weather (wind>15 = Under/run),
H2H/division familiarity, **QB availability** (day-of override). Needs ESPN/nflverse feed.

## MLB ⛔ (needs game-log + probables feed)
Have rs/ra only. Dimensions: **starting pitcher** (the dominant input — ERA/FIP/xFIP,
K-BB%, recent starts, times-through-order), bullpen fatigue (back-to-back usage),
team wRC+ vs LHP/RHP, park factors, **weather/wind** (out=Over, in=Under), umpire
zone, lineup/rest. Needs a probables + splits feed (MLB StatsAPI).

## UFC ⛔ (needs fighter-stats feed)
Engine prices method/rounds from devigged ML + empirical priors; "never invent fighter
stats." Dimensions: striking (SLpM, str-acc, str-def, KD rate), grappling (TD avg/acc/def,
sub attempts), pace/cardio, finish rate & finish-resistance, reach/stance, **weight-cut /
short-notice / layoff & age**, camp. Needs a UFCStats.com scrape/feed.

## F1 ⛔ (needs results feed)
Have a track-traits map only. Dimensions: car pace (quali + race trim), track-type fit,
driver form & DNF rate, grid vs overtaking difficulty, weather, tyre deg, team reliability.
Needs an Ergast/F1 results feed.

---

## ROLLOUT ORDER
Tennis ✅ → Soccer/WC ✅ → **NBA** (local data, next) → NFL / MLB / UFC / F1 (each needs a
verified feed first; one sport per build — fetch script + wiring + tests, like tennis).
Never ship a sport's profile from invented numbers — verify the source first.
