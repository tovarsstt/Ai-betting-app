# Judge — NFL 2026 Week 3 — nflverse feed

Rule: **win probability first, price second.** 2,000,000 Monte Carlo games per matchup + 2,000,000 Bernoulli slips per parlay. NFL σ=12.75 (fitted to 1,759 real games 2019-2025). Ran in 18.2s.
Lines: depth_charts_2026.csv 2026-09-26 01:03 UTC, games.csv 2026-09-26 01:02 UTC, injuries_2026.csv 2026-09-26 01:02 UTC, play_by_play_2025.csv.gz 2026-09-26 01:03 UTC, roster_2026.csv 2026-09-26 01:04 UTC, roster_weekly_2026.csv 2026-09-26 01:04 UTC — nflverse games.csv (consensus lines, updated daily)

## Best winning pick per game (ranked by win %)

| # | Game | Pick | Win % | 2M-sim % | Market | Ratings | Grade | Price | Fair | EV (2nd) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Kansas City Chiefs @ Miami Dolphins | **Kansas City Chiefs ML** | **81.6%** | 81.5% | 81.6% | 69.3% | LOCK | 1.16 | 1.22 | -5.3% |
| 2 | Arizona Cardinals @ San Francisco 49ers | **San Francisco 49ers ML** | **77.2%** | 77.1% | 77.2% | 81.0% | LOCK | 1.23 | 1.3 | -5.3% |
| 3 | Seattle Seahawks @ Washington Commanders | **Seattle Seahawks ML** | **76.1%** | 76.1% | 76.1% | 94.0% | LOCK | 1.25 | 1.31 | -4.6% |
| 4 | Los Angeles Chargers @ Buffalo Bills | **Buffalo Bills ML** | **73.5%** | 73.4% | 73.5% | 71.2% | LOCK | 1.29 | 1.36 | -4.9% |
| 5 | New York Jets @ Detroit Lions | **Detroit Lions ML** | **71.8%** | 71.8% | 71.8% | 74.2% | LOCK | 1.33 | 1.39 | -4.6% |
| 6 | Philadelphia Eagles @ Chicago Bears | **Philadelphia Eagles ML** | **67.3%** | 67.2% | 67.3% | 41.4% | PICK | 1.42 | 1.49 | -4.5% |
| 7 | Cincinnati Bengals @ Pittsburgh Steelers | **Cincinnati Bengals ML** | **61.9%** | 61.8% | 61.9% | 47.9% | LEAN | 1.54 | 1.62 | -4.6% |
| 8 | Las Vegas Raiders @ New Orleans Saints | **New Orleans Saints ML** | **61.3%** | 61.3% | 61.3% | 57.0% | LEAN | 1.54 | 1.63 | -5.5% |
| 9 | Baltimore Ravens @ Dallas Cowboys | **Baltimore Ravens ML** | **60.9%** | 60.8% | 60.9% | 67.2% | LEAN | 1.57 | 1.64 | -4.3% |
| 10 | New England Patriots @ Jacksonville Jaguars | **Jacksonville Jaguars ML** | **57.4%** | 57.2% | 57.4% | 55.6% | LEAN | 1.65 | 1.74 | -5.6% |
| 11 | Carolina Panthers @ Cleveland Browns | **Carolina Panthers ML** | **56.2%** | 56.1% | 56.2% | 58.6% | LEAN | 1.68 | 1.78 | -5.9% |
| 12 | Tennessee Titans @ New York Giants | **New York Giants ML** | **54.6%** | 54.5% | 54.6% | 65.0% | LEAN | 1.74 | 1.83 | -4.9% |
| 13 | Los Angeles Rams @ Denver Broncos | **Los Angeles Rams ML** | **53.6%** | 53.5% | 53.6% | 63.8% | LEAN | 1.77 | 1.86 | -5.1% |
| 14 | Houston Texans @ Indianapolis Colts | **Houston Texans ML** | **53.6%** | 53.6% | 53.6% | 52.7% | LEAN | 1.80 | 1.87 | -3.5% |
| 15 | Minnesota Vikings @ Tampa Bay Buccaneers | **Minnesota Vikings ML** | **52.0%** | 51.8% | 52.0% | 61.4% | LEAN | 1.83 | 1.92 | -4.7% |

## Best winning parlays (Bernoulli sims, one leg per game)

| Legs | Hit % (sim) | Hit % (exact) | Payout | EV (2nd) |
|---|---|---|---|---|
| Kansas City Chiefs ML @ 1.16 (82%)<br>San Francisco 49ers ML @ 1.23 (77%) | **63.1%** | 63.0% | 1.42 | -10.2% |
| Kansas City Chiefs ML @ 1.16 (82%)<br>Seattle Seahawks ML @ 1.25 (76%) | **62.1%** | 62.2% | 1.45 | -9.7% |
| Kansas City Chiefs ML @ 1.16 (82%)<br>Buffalo Bills ML @ 1.29 (73%) | **60.0%** | 60.0% | 1.50 | -9.9% |
| San Francisco 49ers ML @ 1.23 (77%)<br>Seattle Seahawks ML @ 1.25 (76%) | **58.7%** | 58.8% | 1.54 | -9.7% |
| Kansas City Chiefs ML @ 1.16 (82%)<br>Detroit Lions ML @ 1.33 (72%) | **58.7%** | 58.6% | 1.54 | -9.6% |
| San Francisco 49ers ML @ 1.23 (77%)<br>Buffalo Bills ML @ 1.29 (73%) | **56.7%** | 56.7% | 1.59 | -10.0% |
| Kansas City Chiefs ML @ 1.16 (82%)<br>San Francisco 49ers ML @ 1.23 (77%)<br>Seattle Seahawks ML @ 1.25 (76%) | **48.0%** | 48.0% | 1.78 | -14.3% |
| Kansas City Chiefs ML @ 1.16 (82%)<br>San Francisco 49ers ML @ 1.23 (77%)<br>Seattle Seahawks ML @ 1.25 (76%)<br>Buffalo Bills ML @ 1.29 (73%) | **35.3%** | 35.2% | 2.31 | -18.5% |

## Per game — every market, every lens

### Los Angeles Chargers @ Buffalo Bills
Expected home margin — blended +8.0 | market +8.0 | ratings +7.2 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 50.1 · offense×defense ratings 49.7 → blended 50.1 (ratings weight 0%)
- 🏈 QBs: Justin Herbert @ Josh Allen · rest 7d / 10d · outdoors
- 📊 away: net -1.6 pts vs avg (off -2.3 / def +0.8, 2 games in 2026) · EPA/play off -0.084 def -0.049 · pass rate 62% · 58.3 plays/g
- 📊 home: net +4.0 pts vs avg (off +5.6 / def -1.6, 2 games in 2026) · EPA/play off +0.183 def +0.030 · pass rate 57% · 60.1 plays/g
- 👀 away: DT Dalvin Tomlinson: DNP, no game status yet
- 👀 away: T Trey Pipkins: DNP, no game status yet
- 👀 away: S Elijah Molden: DNP, no game status yet
- 👀 away: TE Charlie Kolar: DNP, no game status yet
- 👀 home: WR DJ Moore: DNP, no game status yet
- 👀 home: DE T.J. Sanders: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Buffalo Bills ML | 73.5% | 73.4% | market 73 · ratings 71 · sim 73 | LOCK | 1.29 | -4.9% |
| Over 49.5 | 51.7% | 51.8% | market 52 · ratings 51 · sim 52 | LEAN | 1.85 | -4.4% |
| Buffalo Bills -7 | 49.0% | 49.0% | market 49 · ratings 46 · sim 49 | COINFLIP | 1.87 | -8.4% |
| Under 49.5 | 48.3% | 48.2% | market 48 · ratings 49 · sim 48 | COINFLIP | 1.98 | -4.4% |
| Los Angeles Chargers +7 | 45.5% | 45.4% | market 45 · ratings 48 · sim 45 | SPLIT | 1.95 | -11.2% |
| Los Angeles Chargers ML | 26.5% | 26.5% | market 27 · ratings 29 · sim 26 | SPLIT | 3.70 | -1.8% |

### Carolina Panthers @ Cleveland Browns
Expected home margin — blended -2.0 | market -2.0 | ratings -2.8 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.5 · offense×defense ratings 42.0 → blended 42.5 (ratings weight 0%)
- 🏈 QBs: Bryce Young @ Deshaun Watson · rest 7d / 7d · outdoors
- 📊 away: net -1.4 pts vs avg (off -0.3 / def -1.2, 2 games in 2026) · EPA/play off +0.009 def +0.046 · pass rate 62% · 60.1 plays/g
- 📊 home: net -5.7 pts vs avg (off -5.1 / def -0.6, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off -0.167 def -0.053 · pass rate 63% · 53.5 plays/g
- 👀 away: S Nick Scott: DNP, no game status yet
- 👀 away: LB Devin Lloyd: DNP, no game status yet
- 👀 home: G Teven Jenkins: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Carolina Panthers ML | 56.2% | 56.1% | market 56 · ratings 59 · sim 56 | LEAN | 1.68 | -5.9% |
| Carolina Panthers -2.5 | 52.1% | 52.1% | market 52 · ratings 55 · sim 52 | LEAN | 1.87 | -2.6% |
| Over 42.5 | 50.0% | 50.0% | market 50 · ratings 48 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 42.5 | 50.0% | 50.0% | market 50 · ratings 52 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Cleveland Browns +2.5 | 47.9% | 47.9% | market 48 · ratings 46 · sim 48 | SPLIT | 1.95 | -6.5% |
| Cleveland Browns ML | 43.8% | 43.7% | market 44 · ratings 41 · sim 44 | SPLIT | 2.24 | -1.8% |

### New York Jets @ Detroit Lions
Expected home margin — blended +7.4 | market +7.4 | ratings +8.3 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 48.4 · offense×defense ratings 49.6 → blended 48.4 (ratings weight 0%)
- 🏈 QBs: Geno Smith @ Jared Goff · rest 7d / 10d · dome
- 📊 away: net -4.9 pts vs avg (off -3.7 / def -1.2, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off -0.087 def +0.080 · pass rate 60% · 63.9 plays/g
- 📊 home: net +1.9 pts vs avg (off +4.2 / def -2.3, 2 games in 2026) · EPA/play off +0.089 def +0.043 · pass rate 60% · 66.0 plays/g
- 👀 away: S Minkah Fitzpatrick: DNP, no game status yet
- 👀 away: RB Kene Nwangwu: DNP, no game status yet
- 👀 away: LB Francisco Mauigoa: DNP, no game status yet
- 👀 home: S Thomas Harper: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Detroit Lions ML | 71.8% | 71.8% | market 72 · ratings 74 · sim 72 | LOCK | 1.33 | -4.6% |
| Detroit Lions -6.5 | 52.6% | 52.6% | market 53 · ratings 55 · sim 53 | LEAN | 1.83 | -3.5% |
| Under 48.5 | 50.4% | 50.6% | market 50 · ratings 47 · sim 51 | LEAN | 1.89 | -4.5% |
| Over 48.5 | 49.6% | 49.4% | market 50 · ratings 53 · sim 49 | COINFLIP | 1.93 | -4.5% |
| New York Jets +6.5 | 47.4% | 47.4% | market 47 · ratings 45 · sim 47 | SPLIT | 2.00 | -5.2% |
| New York Jets ML | 28.2% | 28.1% | market 28 · ratings 26 · sim 28 | SPLIT | 3.45 | -2.8% |

### Houston Texans @ Indianapolis Colts
Expected home margin — blended -1.2 | market -1.2 | ratings -0.9 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 43.1 · offense×defense ratings 48.5 → blended 43.1 (ratings weight 0%)
- 🏈 QBs: C.J. Stroud @ Daniel Jones · rest 7d / 7d · division game
- 📊 away: net +4.0 pts vs avg (off +0.0 / def +4.0, 2 games in 2026) · EPA/play off -0.047 def -0.112 · pass rate 63% · 71.8 plays/g
- 📊 home: net +1.6 pts vs avg (off +4.2 / def -2.6, 2 games in 2026) · EPA/play off +0.048 def +0.074 · pass rate 59% · 58.4 plays/g
- 👀 away: TE Dalton Schultz: DNP, no game status yet
- 👀 away: WR Nico Collins: DNP, no game status yet
- 👀 away: LB Jacob Hummel: DNP, no game status yet
- 👀 home: DT Grover Stewart: DNP, no game status yet
- 👀 home: WR Ashton Dulin: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Houston Texans ML | 53.6% | 53.6% | market 54 · ratings 53 · sim 54 | LEAN | 1.80 | -3.5% |
| Over 42.5 | 51.7% | 51.7% | market 52 · ratings 68 · sim 52 | LEAN | 1.85 | -4.4% |
| Houston Texans -1.5 | 51.4% | 51.4% | market 51 · ratings 51 · sim 51 | LEAN | 1.85 | -5.1% |
| Indianapolis Colts +1.5 | 48.6% | 48.6% | market 49 · ratings 49 · sim 49 | COINFLIP | 1.98 | -3.7% |
| Under 42.5 | 48.3% | 48.2% | market 48 · ratings 32 · sim 48 | COINFLIP | 1.98 | -4.4% |
| Indianapolis Colts ML | 46.4% | 46.3% | market 46 · ratings 47 · sim 46 | SPLIT | 2.05 | -4.9% |

### New England Patriots @ Jacksonville Jaguars
Expected home margin — blended +2.4 | market +2.4 | ratings +1.8 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 46.1 · offense×defense ratings 42.6 → blended 46.1 (ratings weight 0%)
- 🏈 QBs: Drake Maye @ Trevor Lawrence · rest 7d / 7d · outdoors
- 📊 away: net +5.4 pts vs avg (off +1.0 / def +4.4, 2 games in 2026) · EPA/play off +0.052 def -0.110 · pass rate 60% · 59.4 plays/g
- 📊 home: net +5.7 pts vs avg (off +3.1 / def +2.6, 2 games in 2026) · EPA/play off +0.055 def -0.072 · pass rate 58% · 56.2 plays/g
- 👀 away: LB Dre'Mont Jones: DNP, no game status yet
- 👀 away: S Craig Woodson: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Jacksonville Jaguars ML | 57.4% | 57.2% | market 57 · ratings 56 · sim 57 | LEAN | 1.65 | -5.6% |
| Under 46.5 | 51.1% | 51.1% | market 51 · ratings 62 · sim 51 | LEAN | 1.87 | -4.5% |
| Over 46.5 | 48.9% | 48.9% | market 49 · ratings 38 · sim 49 | COINFLIP | 1.95 | -4.5% |
| New England Patriots +3 | 46.7% | 46.7% | market 47 · ratings 48 · sim 47 | SPLIT | 1.85 | -13.8% |
| Jacksonville Jaguars -3 | 45.3% | 45.3% | market 45 · ratings 44 · sim 45 | SPLIT | 1.98 | -10.2% |
| New England Patriots ML | 42.6% | 42.6% | market 43 · ratings 44 · sim 43 | SPLIT | 2.30 | -2.0% |

### Kansas City Chiefs @ Miami Dolphins
Expected home margin — blended -11.5 | market -11.5 | ratings -6.5 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 45.4 · offense×defense ratings 42.9 → blended 45.4 (ratings weight 0%)
- 🏈 QBs: Patrick Mahomes @ Malik Willis · rest 7d / 7d · outdoors
- 📊 away: net +2.6 pts vs avg (off +0.1 / def +2.5, 2 games in 2026) · EPA/play off +0.081 def -0.028 · pass rate 64% · 68.6 plays/g
- 📊 home: net -5.4 pts vs avg (off -2.9 / def -2.6, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off -0.040 def +0.108 · pass rate 58% · 53.6 plays/g
- 👀 away: T Josh Simmons: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Kansas City Chiefs ML | 81.6% | 81.5% | market 82 · ratings 69 · sim 82 | LOCK | 1.16 | -5.3% |
| Kansas City Chiefs -10 | 50.7% | 50.7% | market 51 · ratings 35 · sim 51 | LEAN | 1.87 | -5.2% |
| Under 45.5 | 50.4% | 50.4% | market 50 · ratings 58 · sim 50 | LEAN | 1.89 | -4.5% |
| Over 45.5 | 49.6% | 49.6% | market 50 · ratings 42 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Miami Dolphins +10 | 45.3% | 45.3% | market 45 · ratings 61 · sim 45 | SPLIT | 1.95 | -11.5% |
| Miami Dolphins ML | 18.4% | 18.3% | market 18 · ratings 31 · sim 18 | SPLIT | 5.55 | +1.9% |

### Tennessee Titans @ New York Giants
Expected home margin — blended +1.5 | market +1.5 | ratings +4.9 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 38.4 · offense×defense ratings 45.3 → blended 38.4 (ratings weight 0%)
- 🏈 QBs: Cam Ward @ Jameis Winston · rest 7d / 6d · outdoors
- 📊 away: net -6.5 pts vs avg (off -3.5 / def -2.9, 2 games in 2026) · EPA/play off -0.128 def +0.100 · pass rate 64% · 52.2 plays/g
- 📊 home: net -3.0 pts vs avg (off -1.4 / def -1.7, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off +0.010 def +0.126 · pass rate 58% · 60.9 plays/g
- 👀 home: LB Brian Burns: DNP, no game status yet
- 👀 home: T Andrew Thomas: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New York Giants ML | 54.6% | 54.5% | market 55 · ratings 65 · sim 54 | LEAN | 1.74 | -4.9% |
| New York Giants -2.5 | 50.5% | 50.5% | market 51 · ratings 61 · sim 51 | LEAN | 1.91 | -3.5% |
| Under 38.5 | 50.4% | 50.4% | market 50 · ratings 30 · sim 50 | LEAN | 1.89 | -4.5% |
| Over 38.5 | 49.6% | 49.6% | market 50 · ratings 70 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Tennessee Titans +2.5 | 49.5% | 49.5% | market 49 · ratings 39 · sim 49 | COINFLIP | 1.91 | -5.6% |
| Tennessee Titans ML | 45.4% | 45.4% | market 45 · ratings 35 · sim 45 | SPLIT | 2.14 | -2.9% |

### Cincinnati Bengals @ Pittsburgh Steelers
Expected home margin — blended -3.9 | market -3.9 | ratings +0.7 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.6 · offense×defense ratings 47.7 → blended 42.6 (ratings weight 0%)
- 🏈 QBs: Joe Burrow @ Aaron Rodgers · rest 7d / 7d · outdoors · division game
- 📊 away: net -1.8 pts vs avg (off +1.1 / def -3.0, 2 games in 2026) · EPA/play off -0.018 def +0.038 · pass rate 65% · 60.4 plays/g
- 📊 home: net -1.7 pts vs avg (off -1.8 / def +0.2, 2 games in 2026) · EPA/play off -0.090 def -0.025 · pass rate 63% · 62.3 plays/g
- 👀 away: DT Jonathan Allen: DNP, no game status yet
- 🏥 Pittsburgh Steelers: CB Joey Porter Jr. OUT — ruled out (-1 home margin) [https://www.si.com/betting/bengals-vs-steelers-prediction-odds-spread-injuries-trends-for-nfl-week-3-01m32wwcjkpw]
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Cincinnati Bengals ML | 61.9% | 61.8% | market 62 · ratings 48 · sim 62 | LEAN | 1.54 | -4.6% |
| Over 42.5 | 50.4% | 50.4% | market 50 · ratings 65 · sim 50 | LEAN | 1.89 | -4.5% |
| Pittsburgh Steelers +3.5 | 50.1% | 50.1% | market 50 · ratings 64 · sim 50 | LEAN | 1.89 | -5.2% |
| Cincinnati Bengals -3.5 | 49.9% | 49.9% | market 50 · ratings 36 · sim 50 | COINFLIP | 1.93 | -3.8% |
| Under 42.5 | 49.6% | 49.6% | market 50 · ratings 35 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Pittsburgh Steelers ML | 38.1% | 38.0% | market 38 · ratings 52 · sim 38 | SPLIT | 2.54 | -3.2% |

### Seattle Seahawks @ Washington Commanders
Expected home margin — blended -9.1 | market -9.1 | ratings -19.9 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 40.1 · offense×defense ratings 45.6 → blended 40.1 (ratings weight 0%)
- 🏈 QBs: Sam Darnold @ Marcus Mariota · rest 7d / 7d · outdoors
- 📊 away: net +10.9 pts vs avg (off +4.6 / def +6.3, 2 games in 2026) · EPA/play off +0.058 def -0.139 · pass rate 51% · 57.6 plays/g
- 📊 home: net -5.0 pts vs avg (off -1.6 / def -3.4, 2 games in 2026) · EPA/play off +0.023 def +0.145 · pass rate 59% · 64.9 plays/g
- 👀 away: S Julian Love: DNP, no game status yet
- 👀 away: S Ty Okada: DNP, no game status yet
- 👀 home: LB Frankie Luvu: DNP, no game status yet
- 👀 home: G Sam Cosmi: DNP, no game status yet
- 👀 home: TE Chig Okonkwo: DNP, no game status yet
- 🏥 Washington Commanders: QB Jayden Daniels OUT — dislocated left elbow; Marcus Mariota starts. 4.98 = 12-oddsmaker avg Daniels-over-Mariota (-4.98 home margin) [https://www.nfl.com/news/marcus-mariota-commanders-week-3-qb-jayden-daniels-elbow ; https://uk.sports.yahoo.com/news/oddsmakers-rank-all-32-nfl-starting-qbs-by-point-spread-value-how-valuable-is-jayden-daniels-to-the-spread-150837317.html]
- 🏥 Washington Commanders: S Nick Cross OUT — ruled out (-0.5 home margin) [https://www.si.com/betting/seahawks-vs-commanders-prediction-odds-spread-injuries-trends-for-nfl-week-3-2026]
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Seattle Seahawks ML | 76.1% | 76.1% | market 76 · ratings 94 · sim 76 | LOCK | 1.25 | -4.6% |
| Seattle Seahawks -7.5 | 52.3% | 52.3% | market 52 · ratings 82 · sim 52 | LEAN | 1.85 | -3.3% |
| Over 39.5 | 51.7% | 51.7% | market 52 · ratings 68 · sim 52 | LEAN | 1.85 | -4.4% |
| Under 39.5 | 48.3% | 48.3% | market 48 · ratings 32 · sim 48 | COINFLIP | 1.98 | -4.4% |
| Washington Commanders +7.5 | 47.7% | 47.6% | market 48 · ratings 18 · sim 48 | SPLIT | 1.98 | -5.6% |
| Washington Commanders ML | 23.9% | 23.8% | market 24 · ratings 6 · sim 24 | SPLIT | 4.10 | -2.2% |

### Arizona Cardinals @ San Francisco 49ers
Expected home margin — blended +9.5 | market +9.5 | ratings +11.2 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 47.9 · offense×defense ratings 47.1 → blended 47.9 (ratings weight 0%)
- 🏈 QBs: Jacoby Brissett @ Brock Purdy · rest 7d / 7d · outdoors · division game
- 📊 away: net -3.8 pts vs avg (off -1.4 / def -2.4, 2 games in 2026) · EPA/play off -0.025 def +0.060 · pass rate 68% · 59.3 plays/g
- 📊 home: net +6.0 pts vs avg (off +3.2 / def +2.7, 2 games in 2026) · EPA/play off +0.111 def +0.026 · pass rate 59% · 57.2 plays/g
- 👀 away: DT Roy Lopez: DNP, no game status yet
- 👀 home: WR Mike Evans: DNP, no game status yet
- 👀 home: DE Nick Bosa: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| San Francisco 49ers ML | 77.2% | 77.1% | market 77 · ratings 81 · sim 77 | LOCK | 1.23 | -5.3% |
| Over 47.5 | 51.1% | 51.1% | market 51 · ratings 49 · sim 51 | LEAN | 1.87 | -4.5% |
| San Francisco 49ers -8.5 | 50.9% | 50.9% | market 51 · ratings 56 · sim 51 | LEAN | 1.93 | -2.0% |
| Arizona Cardinals +8.5 | 49.1% | 49.1% | market 49 · ratings 44 · sim 49 | COINFLIP | 1.89 | -7.1% |
| Under 47.5 | 48.9% | 48.9% | market 49 · ratings 51 · sim 49 | COINFLIP | 1.95 | -4.5% |
| Arizona Cardinals ML | 22.8% | 22.8% | market 23 · ratings 19 · sim 23 | SPLIT | 4.40 | +0.4% |

### Minnesota Vikings @ Tampa Bay Buccaneers
Expected home margin — blended -0.6 | market -0.6 | ratings -3.7 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.5 · offense×defense ratings 41.3 → blended 42.5 (ratings weight 0%)
- 🏈 QBs: Kyler Murray @ Baker Mayfield · rest 7d / 7d · outdoors
- 📊 away: net +3.7 pts vs avg (off -1.4 / def +5.1, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off -0.098 def -0.113 · pass rate 58% · 55.1 plays/g
- 📊 home: net -1.6 pts vs avg (off +0.3 / def -1.8, 2 games in 2026) · EPA/play off -0.045 def +0.011 · pass rate 62% · 58.1 plays/g
- 👀 away: P Brett Thorson: DNP, no game status yet
- 👀 home: LB Rueben Bain Jr.: DNP, no game status yet
- 👀 home: LB Josiah Trotter: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Minnesota Vikings ML | 52.0% | 51.8% | market 52 · ratings 61 · sim 52 | LEAN | 1.83 | -4.7% |
| Tampa Bay Buccaneers +1.5 | 50.2% | 50.3% | market 50 · ratings 41 · sim 50 | LEAN | 1.89 | -4.9% |
| Over 42.5 | 50.0% | 50.0% | market 50 · ratings 46 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 42.5 | 50.0% | 50.0% | market 50 · ratings 54 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Minnesota Vikings -1.5 | 49.8% | 49.7% | market 50 · ratings 59 · sim 50 | COINFLIP | 1.93 | -4.2% |
| Tampa Bay Buccaneers ML | 48.0% | 48.0% | market 48 · ratings 39 · sim 48 | COINFLIP | 2.00 | -4.0% |

### Baltimore Ravens @ Dallas Cowboys
Expected home margin — blended -3.6 | market -3.6 | ratings -5.7 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 53.4 · offense×defense ratings 56.6 → blended 53.4 (ratings weight 0%)
- 🏈 QBs: Lamar Jackson @ Dak Prescott · rest 7d / 7d
- 📊 away: net +1.5 pts vs avg (off +1.8 / def -0.3, 2 games in 2026) · EPA/play off +0.082 def +0.013 · pass rate 54% · 57.2 plays/g
- 📊 home: net -2.2 pts vs avg (off +3.4 / def -5.6, 2 games in 2026) · EPA/play off +0.125 def +0.181 · pass rate 63% · 56.1 plays/g
- 👀 away: T Ronnie Stanley: DNP, no game status yet
- 👀 away: WR Zay Flowers: DNP, no game status yet
- 🏥 Dallas Cowboys: S Malik Hooker OUT (Forearm) (-0.5 home margin) [nflverse injuries_2026.csv week 3 (official NFL injury report)]
- 🏥 Dallas Cowboys: CB Cobie Durant OUT (Hamstring) (-1 home margin) [nflverse injuries_2026.csv week 3 (official NFL injury report)]
- 🏥 Dallas Cowboys: LB DeMarvion Overshown OUT (Hamstring) (-0.5 home margin) [nflverse injuries_2026.csv week 3 (official NFL injury report)]
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Baltimore Ravens ML | 60.9% | 60.8% | market 61 · ratings 67 · sim 61 | LEAN | 1.57 | -4.3% |
| Dallas Cowboys +3.5 | 51.1% | 51.1% | market 51 · ratings 44 · sim 51 | LEAN | 1.87 | -4.5% |
| Under 53.5 | 50.4% | 50.5% | market 50 · ratings 41 · sim 50 | LEAN | 1.89 | -4.5% |
| Over 53.5 | 49.6% | 49.5% | market 50 · ratings 59 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Baltimore Ravens -3.5 | 48.9% | 48.9% | market 49 · ratings 56 · sim 49 | COINFLIP | 1.95 | -4.5% |
| Dallas Cowboys ML | 39.1% | 39.1% | market 39 · ratings 33 · sim 39 | SPLIT | 2.45 | -4.3% |

### Las Vegas Raiders @ New Orleans Saints
Expected home margin — blended +3.7 | market +3.7 | ratings +2.3 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 44.1 · offense×defense ratings 38.8 → blended 44.1 (ratings weight 0%)
- 🏈 QBs: Kirk Cousins @ Tyler Shough · rest 7d / 7d · dome
- 📊 away: net -2.9 pts vs avg (off -3.2 / def +0.3, 2 games in 2026, NEW QB since 2025 (prior halved)) · EPA/play off -0.175 def -0.040 · pass rate 61% · 59.2 plays/g
- 📊 home: net -2.2 pts vs avg (off -2.8 / def +0.6, 2 games in 2026) · EPA/play off -0.050 def -0.030 · pass rate 64% · 71.8 plays/g
- 👀 away: DE Kwity Paye: DNP, no game status yet
- 👀 away: S Treydan Stukes: DNP, no game status yet
- 👀 home: WR Barion Brown: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New Orleans Saints ML | 61.3% | 61.3% | market 61 · ratings 57 · sim 61 | LEAN | 1.54 | -5.5% |
| Over 43.5 | 51.7% | 51.7% | market 52 · ratings 36 · sim 52 | LEAN | 1.85 | -4.4% |
| New Orleans Saints -3 | 49.4% | 49.4% | market 49 · ratings 45 · sim 49 | COINFLIP | 1.82 | -10.2% |
| Under 43.5 | 48.3% | 48.3% | market 48 · ratings 64 · sim 48 | COINFLIP | 1.98 | -4.4% |
| Las Vegas Raiders +3 | 42.7% | 42.6% | market 43 · ratings 47 · sim 43 | SPLIT | 2.02 | -13.8% |
| Las Vegas Raiders ML | 38.7% | 38.5% | market 39 · ratings 43 · sim 39 | SPLIT | 2.54 | -1.8% |

### Los Angeles Rams @ Denver Broncos
Expected home margin — blended -1.2 | market -1.2 | ratings -4.5 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 43.9 · offense×defense ratings 43.3 → blended 43.9 (ratings weight 0%)
- 🏈 QBs: Matthew Stafford @ Bo Nix · rest 6d / 7d · outdoors
- 📊 away: net +7.5 pts vs avg (off +4.5 / def +3.0, 2 games in 2026) · EPA/play off +0.118 def -0.058 · pass rate 58% · 57.8 plays/g
- 📊 home: net +1.5 pts vs avg (off -1.2 / def +2.6, 2 games in 2026) · EPA/play off +0.008 def -0.047 · pass rate 63% · 54.2 plays/g
- 👀 away: TE Colby Parkinson: DNP, no game status yet
- 👀 away: WR Puka Nacua: DNP, no game status yet
- 👀 away: S Kamren Kinchens: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Los Angeles Rams ML | 53.6% | 53.5% | market 54 · ratings 64 · sim 54 | LEAN | 1.77 | -5.1% |
| Under 44.5 | 51.7% | 51.7% | market 52 · ratings 54 · sim 52 | LEAN | 1.85 | -4.4% |
| Denver Broncos +2.5 | 50.4% | 50.4% | market 50 · ratings 40 · sim 50 | LEAN | 1.87 | -5.7% |
| Los Angeles Rams -2.5 | 49.6% | 49.6% | market 50 · ratings 60 · sim 50 | COINFLIP | 1.95 | -3.2% |
| Over 44.5 | 48.3% | 48.3% | market 48 · ratings 46 · sim 48 | COINFLIP | 1.98 | -4.4% |
| Denver Broncos ML | 46.4% | 46.3% | market 46 · ratings 36 · sim 46 | SPLIT | 2.10 | -2.6% |

### Philadelphia Eagles @ Chicago Bears
Expected home margin — blended -5.7 | market -5.7 | ratings +2.8 · weights {'market': 0.65, 'ratings': 0.0, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 41.1 · offense×defense ratings 45.5 → blended 41.1 (ratings weight 0%)
- 🏈 QBs: Jalen Hurts @ Caleb Williams · rest 8d / 8d · outdoors
- 📊 away: net +1.3 pts vs avg (off -1.2 / def +2.5, 2 games in 2026) · EPA/play off +0.029 def -0.038 · pass rate 58% · 60.9 plays/g
- 📊 home: net +2.5 pts vs avg (off +3.0 / def -0.5, 2 games in 2026) · EPA/play off +0.091 def +0.039 · pass rate 59% · 68.6 plays/g
- 👀 away: TE Dallas Goedert: DNP, no game status yet
- 👀 away: WR DeVonta Smith: DNP, no game status yet
- 👀 away: RB Will Shipley: DNP, no game status yet
- 👀 home: K Cairo Santos: DNP, no game status yet
- 👀 home: DT Grady Jarrett: DNP, no game status yet
- 👀 home: CB Tyrique Stevenson: DNP, no game status yet
- 👀 home: QB Caleb Williams: DNP, no game status yet
- ⚠️ RATINGS_DISPLAY_ONLY: NFL backtest shows the market beats team ratings (best blend weight 0) — ratings shown for context, no vote

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Philadelphia Eagles ML | 67.3% | 67.2% | market 67 · ratings 41 · sim 67 | PICK | 1.42 | -4.5% |
| Philadelphia Eagles -4.5 | 52.9% | 52.8% | market 53 · ratings 28 · sim 53 | LEAN | 1.82 | -3.8% |
| Under 41.5 | 51.1% | 51.1% | market 51 · ratings 38 · sim 51 | LEAN | 1.87 | -4.5% |
| Over 41.5 | 48.9% | 48.9% | market 49 · ratings 62 · sim 49 | COINFLIP | 1.95 | -4.5% |
| Chicago Bears +4.5 | 47.1% | 47.2% | market 47 · ratings 72 · sim 47 | SPLIT | 2.02 | -4.8% |
| Chicago Bears ML | 32.7% | 32.7% | market 33 · ratings 59 · sim 33 | SPLIT | 2.95 | -3.5% |

Grades: LOCK ≥70% · PICK ≥62% · LEAN below · SPLIT = a weighted lens disagrees on the side. Win % never means guaranteed; EV shows whether the price pays enough for that win rate.
