# Judge — NFL 2026 Week 3 — Sunday, Sept 27

Rule: **win probability first, price second.** 2,000,000 Monte Carlo games per matchup + 2,000,000 Bernoulli slips per parlay. NFL σ=10.75 (fitted to this slate). Ran in 19.2s.
Lines: 2026-09-26 — Manual snapshot from web-search result snippets (sportsbook pages could not be fetched from the build container). Lines move — re-run with --live and ODDS_API_KEY before betting.

## Best winning pick per game (ranked by win %)

| # | Game | Pick | Win % | 2M-sim % | Market | Ratings | Grade | Price | Fair | EV (2nd) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Kansas City Chiefs @ Miami Dolphins | **Kansas City Chiefs ML** | **83.6%** | 83.6% | 84.7% | 65.8% | LOCK | 1.15 | 1.2 | -3.5% |
| 2 | Arizona Cardinals @ San Francisco 49ers | **San Francisco 49ers ML** | **79.7%** | 79.7% | 79.6% | 80.6% | LOCK | 1.22 | 1.25 | -2.8% |
| 3 | Los Angeles Chargers @ Buffalo Bills | **Buffalo Bills ML** | **76.6%** | 76.5% | 75.6% | 84.0% | LOCK | 1.27 | 1.31 | -2.7% |
| 4 | New York Jets @ Detroit Lions | **Detroit Lions ML** | **73.5%** | 73.4% | 72.7% | 79.1% | LOCK | 1.33 | 1.36 | -2.1% |
| 5 | Seattle Seahawks @ Washington Commanders | **Seattle Seahawks ML** | **72.7%** | 72.7% | 73.3% | 68.8% | LOCK | 1.30 | 1.37 | -5.2% |
| 6 | Las Vegas Raiders @ New Orleans Saints | **New Orleans Saints ML** | **64.6%** | 64.6% | 63.0% | 79.9% | PICK | 1.56 | 1.55 | +0.5% |
| 7 | Cincinnati Bengals @ Pittsburgh Steelers | **Cincinnati Bengals ML** | **61.4%** | 61.3% | 63.1% | 37.3% | LEAN | 1.54 | 1.63 | -5.3% |
| 8 | Dallas Cowboys @ Baltimore Ravens | **Baltimore Ravens ML** | **60.1%** | 60.1% | 59.6% | 63.8% | LEAN | 1.64 | 1.66 | -1.6% |
| 9 | New England Patriots @ Jacksonville Jaguars | **Jacksonville Jaguars ML** | **57.2%** | 57.1% | 59.3% | 30.1% | LEAN | 1.62 | 1.75 | -7.1% |
| 10 | Los Angeles Rams @ Denver Broncos | **Los Angeles Rams ML** | **55.0%** | 54.9% | 55.7% | 50.4% | LEAN | 1.69 | 1.82 | -7.0% |
| 11 | Tennessee Titans @ New York Giants | **New York Giants ML** | **54.5%** | 54.4% | 56.1% | 38.7% | LEAN | 1.67 | 1.83 | -9.1% |
| 12 | Carolina Panthers @ Cleveland Browns | **Carolina Panthers ML** | **53.9%** | 53.8% | 56.0% | 27.3% | LEAN | 1.68 | 1.86 | -9.7% |
| 13 | Minnesota Vikings @ Tampa Bay Buccaneers | **Minnesota Vikings ML** | **53.1%** | 53.0% | 54.5% | 40.1% | LEAN | 1.77 | 1.88 | -6.1% |
| 14 | Houston Texans @ Indianapolis Colts | **Houston Texans ML** | **53.1%** | 53.0% | 55.0% | 28.2% | LEAN | 1.67 | 1.88 | -11.6% |

## Best winning parlays (Bernoulli sims, one leg per game)

| Legs | Hit % (sim) | Hit % (exact) | Payout | EV (2nd) |
|---|---|---|---|---|
| Kansas City Chiefs ML @ 1.15 (84%)<br>San Francisco 49ers ML @ 1.22 (80%) | **66.7%** | 66.6% | 1.41 | -6.1% |
| Kansas City Chiefs ML @ 1.15 (84%)<br>Buffalo Bills ML @ 1.27 (77%) | **64.0%** | 64.0% | 1.47 | -6.2% |
| Kansas City Chiefs ML @ 1.15 (84%)<br>Detroit Lions ML @ 1.33 (73%) | **61.4%** | 61.4% | 1.54 | -5.5% |
| San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%) | **61.0%** | 61.1% | 1.55 | -5.4% |
| Kansas City Chiefs ML @ 1.15 (84%)<br>Seattle Seahawks ML @ 1.30 (73%) | **60.8%** | 60.8% | 1.50 | -8.5% |
| San Francisco 49ers ML @ 1.22 (80%)<br>Detroit Lions ML @ 1.33 (73%) | **58.5%** | 58.6% | 1.63 | -4.8% |
| Kansas City Chiefs ML @ 1.15 (84%)<br>San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%) | **51.1%** | 51.0% | 1.79 | -8.7% |
| Kansas City Chiefs ML @ 1.15 (84%)<br>San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%)<br>Detroit Lions ML @ 1.33 (73%) | **37.5%** | 37.5% | 2.38 | -10.5% |

## Per game — every market, every lens

### Los Angeles Chargers @ Buffalo Bills — 2026: away 0-2, home 2-0
Expected home margin — blended +7.8 | market +7.5 | ratings +10.7 · weights {'market': 0.65, 'ratings': 0.0769, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 50.5 · offense×defense ratings 48.6 (home 27.5, away 21.1, 2025 data) → blended 50.3
- 🛡️ away defense allows 182.9 pass yds / 107.6 rush yds per game
- 🛡️ home defense allows 165.9 pass yds / 133.6 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Buffalo Bills ML | 76.6% | 76.5% | market 76 · ratings 84 · sim 77 | LOCK | 1.27 | -2.7% |
| Buffalo Bills -5.5 (Stake) | 58.6% | 58.6% | market 57 · ratings 69 · sim 59 | LEAN | 1.67 | -2.2% |
| Under 50.5 | 50.9% | 50.8% | market 50 · ratings 58 · sim 51 | COINFLIP | 1.91 | -2.8% |
| Over 50.5 | 49.1% | 49.1% | market 50 · ratings 42 · sim 49 | COINFLIP | 1.91 | -6.3% |
| Buffalo Bills -7 | 48.1% | 48.1% | market 47 · ratings 59 · sim 48 | SPLIT | 1.91 | -8.3% |
| Los Angeles Chargers +7 | 45.4% | 45.4% | market 47 · ratings 35 · sim 45 | SPLIT | 1.91 | -13.3% |
| Los Angeles Chargers ML | 23.4% | 23.3% | market 24 · ratings 16 · sim 23 | SPLIT | 3.95 | -7.5% |

### Carolina Panthers @ Cleveland Browns — 2026: away 1-1, home 1-1
Expected home margin — blended -1.1 | market -1.6 | ratings +6.5 · weights {'market': 0.65, 'ratings': 0.05, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.5 · offense×defense ratings 35.3 (home 16.2, away 19.0, 2025 data) → blended 42.0
- 🛡️ away defense allows 209.0 pass yds / 122.9 rush yds per game
- 🛡️ home defense allows 167.2 pass yds / 116.4 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home +6.5, market -1.6 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 5%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 35.3 pts, market 42.5 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Carolina Panthers ML | 53.9% | 53.8% | market 56 · ratings 27 · sim 54 | LEAN | 1.68 | -9.7% |
| Under 42.5 | 52.1% | 52.0% | market 50 · ratings 76 · sim 52 | COINFLIP | 1.91 | -0.6% |
| Cleveland Browns +2.5 | 50.9% | 50.9% | market 49 · ratings 76 · sim 51 | COINFLIP | 1.91 | -2.8% |
| Carolina Panthers -2.5 | 49.1% | 49.1% | market 51 · ratings 24 · sim 49 | LEAN | 1.91 | -6.3% |
| Over 42.5 | 47.9% | 48.0% | market 50 · ratings 24 · sim 48 | COINFLIP | 1.91 | -8.5% |
| Cleveland Browns ML | 46.1% | 46.0% | market 44 · ratings 73 · sim 46 | SPLIT | 2.24 | +3.3% |

### New York Jets @ Detroit Lions — 2026: away 1-1, home 1-1
Expected home margin — blended +6.8 | market +6.5 | ratings +8.7 · weights {'market': 0.65, 'ratings': 0.0843, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 47.5 · offense×defense ratings 56.0 (home 36.5, away 19.5, 2025 data) → blended 48.1
- 🛡️ away defense allows 216.1 pass yds / 139.5 rush yds per game
- 🛡️ home defense allows 217.4 pass yds / 114.5 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 56.0 pts, market 47.5 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Detroit Lions ML | 73.5% | 73.4% | market 73 · ratings 79 · sim 73 | LOCK | 1.33 | -2.1% |
| Detroit Lions -3.5 (Stake) | 60.3% | 60.2% | market 59 · ratings 67 · sim 60 | LEAN | 1.61 | -3.0% |
| Over 47.5 | 52.4% | 52.3% | market 50 · ratings 80 · sim 52 | COINFLIP | 1.91 | +0.1% |
| Detroit Lions -6.5 | 50.8% | 50.7% | market 50 · ratings 58 · sim 51 | COINFLIP | 1.91 | -3.1% |
| New York Jets +6.5 | 49.2% | 49.3% | market 50 · ratings 42 · sim 49 | LEAN | 1.91 | -6.0% |
| Under 47.5 | 47.6% | 47.7% | market 50 · ratings 20 · sim 48 | COINFLIP | 1.91 | -9.2% |
| New York Jets ML | 26.5% | 26.5% | market 27 · ratings 21 · sim 26 | SPLIT | 3.60 | -4.5% |

### Houston Texans @ Indianapolis Colts — 2026: away 0-2, home 0-2
Expected home margin — blended -0.8 | market -1.4 | ratings +6.2 · weights {'market': 0.65, 'ratings': 0.05, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.5 · offense×defense ratings 39.5 (home 21.4, away 18.1, 2025 data) → blended 42.2
- 🛡️ away defense allows 177.6 pass yds / 92.7 rush yds per game
- 🛡️ home defense allows 247.9 pass yds / 101.9 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home +6.2, market -1.4 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Houston Texans ML | 53.1% | 53.0% | market 55 · ratings 28 · sim 53 | LEAN | 1.67 | -11.6% |
| Under 42.5 | 51.3% | 51.3% | market 50 · ratings 62 · sim 51 | COINFLIP | 1.91 | -2.1% |
| Houston Texans -1.5 | 50.4% | 50.4% | market 52 · ratings 26 · sim 50 | LEAN | 1.91 | -3.7% |
| Indianapolis Colts +1.5 | 49.6% | 49.5% | market 48 · ratings 74 · sim 50 | SPLIT | 1.91 | -5.4% |
| Over 42.5 | 48.7% | 48.7% | market 50 · ratings 38 · sim 49 | COINFLIP | 1.91 | -7.0% |
| Indianapolis Colts ML | 46.9% | 46.8% | market 45 · ratings 72 · sim 47 | SPLIT | 2.25 | +5.6% |

### Kansas City Chiefs @ Miami Dolphins — 2026: away 2-0, home 0-2
Expected home margin — blended -10.5 | market -11.0 | ratings -4.4 · weights {'market': 0.65, 'ratings': 0.0528, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 45.5 · offense×defense ratings 46.2 (home 15.3, away 30.9, 2025 data) → blended 45.6
- 🛡️ away defense allows 195.8 pass yds / 105.7 rush yds per game
- 🛡️ home defense allows 216.4 pass yds / 132.4 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home -4.4, market -11.0 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Kansas City Chiefs ML | 83.6% | 83.6% | market 85 · ratings 66 · sim 84 | LOCK | 1.15 | -3.5% |
| Miami Dolphins +10.5 | 52.9% | 52.9% | market 51 · ratings 74 · sim 53 | LEAN | 1.91 | +1.0% |
| Over 45.5 | 50.4% | 50.3% | market 50 · ratings 53 · sim 50 | COINFLIP | 1.91 | -3.9% |
| Under 45.5 | 49.6% | 49.6% | market 50 · ratings 47 · sim 50 | COINFLIP | 1.91 | -5.2% |
| Kansas City Chiefs -10.5 | 47.1% | 47.1% | market 49 · ratings 26 · sim 47 | COINFLIP | 1.91 | -10.1% |
| Kansas City Chiefs -10.5 (Stake) | 47.1% | 47.1% | market 49 · ratings 26 · sim 47 | COINFLIP | 1.90 | -10.5% |
| Miami Dolphins ML | 16.4% | 16.3% | market 15 · ratings 34 · sim 16 | SPLIT | 6.40 | +5.0% |

### Cincinnati Bengals @ Pittsburgh Steelers — 2026: away 2-0, home 1-1
Expected home margin — blended -3.1 | market -3.6 | ratings +3.5 · weights {'market': 0.65, 'ratings': 0.05, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 42.5 · offense×defense ratings 57.4 (home 34.0, away 23.4, 2025 data) → blended 43.6
- 🛡️ away defense allows 233.8 pass yds / 147.1 rush yds per game
- 🛡️ home defense allows 243.9 pass yds / 115.9 rush yds per game
- 🏥 Pittsburgh Steelers: CB Joey Porter Jr. OUT (-1 home margin) [https://www.si.com/betting/bengals-vs-steelers-prediction-odds-spread-injuries-trends-for-nfl-week-3-01m32wwcjkpw]
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home +3.5, market -3.6 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 5%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 57.4 pts, market 42.5 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Cincinnati Bengals ML | 61.4% | 61.3% | market 63 · ratings 37 · sim 61 | LEAN | 1.54 | -5.3% |
| Over 42.5 | 54.2% | 54.2% | market 50 · ratings 93 · sim 54 | COINFLIP | 1.91 | +3.5% |
| Pittsburgh Steelers +3.5 | 52.8% | 52.8% | market 51 · ratings 75 · sim 53 | LEAN | 1.91 | +0.8% |
| Cincinnati Bengals -3.5 | 47.2% | 47.2% | market 49 · ratings 25 · sim 47 | COINFLIP | 1.91 | -9.9% |
| Under 42.5 | 45.8% | 45.8% | market 50 · ratings 7 · sim 46 | COINFLIP | 1.91 | -12.6% |
| Pittsburgh Steelers ML | 38.6% | 38.6% | market 37 · ratings 63 · sim 39 | SPLIT | 2.54 | -1.9% |

### Seattle Seahawks @ Washington Commanders — 2026: away 2-0, home 0-2
Expected home margin — blended -6.5 | market -6.7 | ratings -5.3 · weights {'market': 0.65, 'ratings': 0.09, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 40.4 · offense×defense ratings 48.9 (home 19.6, away 29.3, 2025 data) → blended 41.0
- 🛡️ away defense allows 202.1 pass yds / 93.2 rush yds per game
- 🛡️ home defense allows 242.5 pass yds / 141.8 rush yds per game
- 🏥 Washington Commanders: QB Jayden Daniels OUT (dislocated left elbow) — Marcus Mariota starts; 12-oddsmaker avg Daniels over Mariota = 4.98 pts (-4.98 home margin) [https://uk.sports.yahoo.com/news/oddsmakers-rank-all-32-nfl-starting-qbs-by-point-spread-value-how-valuable-is-jayden-daniels-to-the-spread-150837317.html]
- 🏥 Washington Commanders: S Nick Cross ruled OUT (-0.5 home margin) [https://www.si.com/betting/seahawks-vs-commanders-prediction-odds-spread-injuries-trends-for-nfl-week-3-2026]
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 48.9 pts, market 40.4 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Seattle Seahawks ML | 72.7% | 72.7% | market 73 · ratings 69 · sim 73 | LOCK | 1.30 | -5.2% |
| Seattle Seahawks -4.5 (Stake) | 56.2% | 56.3% | market 57 · ratings 52 · sim 56 | LEAN | 1.52 | -14.5% |
| Over 40.5 | 52.0% | 52.0% | market 50 · ratings 80 · sim 52 | COINFLIP | 1.93 | +0.1% |
| Washington Commanders +6.5 | 50.1% | 50.1% | market 49 · ratings 55 · sim 50 | COINFLIP | 1.91 | -4.4% |
| Seattle Seahawks -6.5 | 49.9% | 49.9% | market 51 · ratings 45 · sim 50 | LEAN | 1.91 | -4.7% |
| Under 40.5 | 48.0% | 48.0% | market 50 · ratings 20 · sim 48 | LEAN | 1.89 | -9.1% |
| Washington Commanders ML | 27.3% | 27.2% | market 27 · ratings 31 · sim 27 | SPLIT | 3.65 | -0.5% |

### New England Patriots @ Jacksonville Jaguars — 2026: away 1-1, home 1-1
Expected home margin — blended +2.0 | market +2.5 | ratings -5.6 · weights {'market': 0.65, 'ratings': 0.05, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 45.5 · offense×defense ratings 41.7 (home 16.4, away 25.3, 2025 data) → blended 45.1
- 🛡️ away defense allows 185.7 pass yds / 99.2 rush yds per game
- 🛡️ home defense allows 220.4 pass yds / 85.2 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home -5.6, market +2.5 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 5%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 41.7 pts, market 45.5 — ratings weight on totals 7%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Jacksonville Jaguars ML | 57.2% | 57.1% | market 59 · ratings 30 · sim 57 | LEAN | 1.62 | -7.1% |
| Under 45.5 | 51.5% | 51.5% | market 50 · ratings 65 · sim 52 | COINFLIP | 1.91 | -1.6% |
| Over 45.5 | 48.5% | 48.5% | market 50 · ratings 35 · sim 48 | COINFLIP | 1.91 | -7.5% |
| New England Patriots +3 | 47.6% | 47.6% | market 45 · ratings 74 · sim 48 | SPLIT | 1.91 | -9.1% |
| Jacksonville Jaguars -3 | 43.0% | 43.0% | market 45 · ratings 19 · sim 43 | SPLIT | 1.91 | -17.9% |
| New England Patriots ML | 42.8% | 42.7% | market 41 · ratings 70 · sim 43 | SPLIT | 2.35 | +0.6% |

### Tennessee Titans @ New York Giants — 2026: away 0-2, home 1-1
Expected home margin — blended +1.2 | market +1.7 | ratings -3.1 · weights {'market': 0.65, 'ratings': 0.066, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 38.5 · offense×defense ratings 42.6 (home 26.7, away 15.9, 2025 data) → blended 38.9
- 🛡️ away defense allows 230.5 pass yds / 114.6 rush yds per game
- 🛡️ home defense allows 214.2 pass yds / 145.3 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home -3.1, market +1.7 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 7%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 42.6 pts, market 38.5 — ratings weight on totals 7%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New York Giants ML | 54.5% | 54.4% | market 56 · ratings 39 · sim 54 | LEAN | 1.67 | -9.1% |
| Over 38.5 | 51.6% | 51.6% | market 50 · ratings 66 · sim 52 | COINFLIP | 1.91 | -1.5% |
| Tennessee Titans +2.5 | 50.3% | 50.3% | market 49 · ratings 66 · sim 50 | COINFLIP | 1.91 | -4.0% |
| New York Giants -2.5 | 49.7% | 49.7% | market 51 · ratings 34 · sim 50 | LEAN | 1.91 | -5.1% |
| Under 38.5 | 48.4% | 48.4% | market 50 · ratings 34 · sim 48 | COINFLIP | 1.91 | -7.6% |
| Tennessee Titans ML | 45.5% | 45.4% | market 44 · ratings 61 · sim 45 | SPLIT | 2.25 | +2.3% |

### Minnesota Vikings @ Tampa Bay Buccaneers — 2026: away 2-0, home 0-2
Expected home margin — blended -0.8 | market -1.2 | ratings +2.7 · weights {'market': 0.65, 'ratings': 0.0719, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 43.5 · offense×defense ratings 45.7 (home 24.5, away 21.2, 2025 data) → blended 43.8
- 🛡️ away defense allows 158.5 pass yds / 124.1 rush yds per game
- 🛡️ home defense allows 238.2 pass yds / 99.1 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home +2.7, market -1.2 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 7%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Minnesota Vikings ML | 53.1% | 53.0% | market 55 · ratings 40 · sim 53 | LEAN | 1.77 | -6.1% |
| Tampa Bay Buccaneers +2.5 | 51.7% | 51.7% | market 50 · ratings 64 · sim 52 | LEAN | 1.91 | -1.3% |
| Over 43.5 | 51.0% | 51.0% | market 50 · ratings 59 · sim 51 | COINFLIP | 1.91 | -2.6% |
| Under 43.5 | 49.0% | 49.0% | market 50 · ratings 41 · sim 49 | COINFLIP | 1.91 | -6.5% |
| Minnesota Vikings -2.5 | 48.3% | 48.3% | market 50 · ratings 36 · sim 48 | COINFLIP | 1.91 | -7.8% |
| Tampa Bay Buccaneers ML | 46.9% | 46.8% | market 45 · ratings 60 · sim 47 | SPLIT | 2.10 | -1.5% |

### Arizona Cardinals @ San Francisco 49ers — 2026: away 1-1, home 2-0
Expected home margin — blended +8.9 | market +8.9 | ratings +9.3 · weights {'market': 0.65, 'ratings': 0.0971, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 47.5 · offense×defense ratings 38.2 (home 18.9, away 19.3, 2025 data) → blended 46.8
- 🛡️ away defense allows 230.8 pass yds / 126.9 rush yds per game
- 🛡️ home defense allows 222.3 pass yds / 113.1 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 38.2 pts, market 47.5 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| San Francisco 49ers ML | 79.7% | 79.7% | market 80 · ratings 81 · sim 80 | LOCK | 1.22 | -2.8% |
| Under 47.5 | 52.6% | 52.7% | market 50 · ratings 82 · sim 53 | COINFLIP | 1.91 | +0.5% |
| Arizona Cardinals +8.5 | 51.0% | 51.0% | market 51 · ratings 50 · sim 51 | LEAN | 1.91 | -2.5% |
| San Francisco 49ers -8.5 | 48.9% | 49.0% | market 49 · ratings 50 · sim 49 | COINFLIP | 1.91 | -6.5% |
| Over 47.5 | 47.3% | 47.3% | market 50 · ratings 18 · sim 47 | COINFLIP | 1.91 | -9.6% |
| Arizona Cardinals ML | 20.3% | 20.2% | market 20 · ratings 19 · sim 20 | SPLIT | 4.50 | -8.7% |

### Dallas Cowboys @ Baltimore Ravens — 2026: away 1-1, home 1-1
Expected home margin — blended +2.8 | market +2.6 | ratings +3.8 · weights {'market': 0.65, 'ratings': 0.0915, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 52.7 · offense×defense ratings 73.1 (home 33.4, away 39.7, 2025 data) → blended 54.1
- 🛡️ away defense allows 251.5 pass yds / 125.5 rush yds per game
- 🛡️ home defense allows 247.9 pass yds / 106.6 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 73.1 pts, market 52.7 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Baltimore Ravens ML | 60.1% | 60.1% | market 60 · ratings 64 · sim 60 | LEAN | 1.64 | -1.6% |
| Over 52.5 | 56.4% | 56.4% | market 51 · ratings 98 · sim 56 | LEAN | 1.88 | +6.4% |
| Baltimore Ravens -3 | 45.9% | 45.9% | market 45 · ratings 50 · sim 46 | SPLIT | 1.96 | -10.0% |
| Dallas Cowboys +3 | 44.7% | 44.6% | market 45 · ratings 41 · sim 45 | SPLIT | 1.87 | -16.5% |
| Under 52.5 | 43.6% | 43.6% | market 49 · ratings 2 · sim 44 | COINFLIP | 1.93 | -15.7% |
| Dallas Cowboys ML | 39.9% | 39.7% | market 40 · ratings 36 · sim 40 | SPLIT | 2.55 | +1.8% |

### Las Vegas Raiders @ New Orleans Saints — 2026: away 2-0, home 1-1
Expected home margin — blended +4.0 | market +3.6 | ratings +9.0 · weights {'market': 0.65, 'ratings': 0.0612, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 43.6 · offense×defense ratings 34.2 (home 17.7, away 16.5, 2025 data) → blended 42.9
- 🛡️ away defense allows 201.0 pass yds / 116.8 rush yds per game
- 🛡️ home defense allows 179.2 pass yds / 120.6 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ RATINGS_DISAGREE: team ratings say home +9.0, market +3.6 — season ratings miss today's news (injuries/lineups/starters/form); ratings weight cut to 6%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 34.2 pts, market 43.6 — ratings weight on totals 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New Orleans Saints ML | 64.6% | 64.6% | market 63 · ratings 80 · sim 65 | PICK | 1.56 | +0.5% |
| Under 43.5 | 52.2% | 52.3% | market 50 · ratings 82 · sim 52 | COINFLIP | 1.93 | +0.6% |
| New Orleans Saints -3.5 | 50.5% | 50.6% | market 49 · ratings 68 · sim 51 | COINFLIP | 1.91 | -3.5% |
| Las Vegas Raiders +3.5 | 49.5% | 49.4% | market 51 · ratings 32 · sim 49 | LEAN | 1.91 | -5.5% |
| Over 43.5 | 47.8% | 47.7% | market 50 · ratings 18 · sim 48 | LEAN | 1.89 | -9.6% |
| Las Vegas Raiders ML | 35.4% | 35.3% | market 37 · ratings 20 · sim 35 | SPLIT | 2.52 | -10.8% |

### Los Angeles Rams @ Denver Broncos — 2026: away 1-1, home 1-1
Expected home margin — blended -1.4 | market -1.5 | ratings -0.1 · weights {'market': 0.65, 'ratings': 0.0897, 'engine': 0.0, 'agents': 0.0}
- 🔢 Total: market 44.5 · offense×defense ratings 38.9 (home 18.6, away 20.3, 2025 data) → blended 44.0
- 🛡️ away defense allows 225.6 pass yds / 110.1 rush yds per game
- 🛡️ home defense allows 184.9 pass yds / 98.5 rush yds per game
- ⚠️ RATINGS_PRIOR_SEASON: team ratings are from 2025, not 2026 — ratings weight capped at 10%
- ⚠️ TOTAL_RATINGS_DISAGREE: offense/defense ratings project 38.9 pts, market 44.5 — ratings weight on totals 6%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Los Angeles Rams ML | 55.0% | 54.9% | market 56 · ratings 50 · sim 55 | LEAN | 1.69 | -7.0% |
| Under 44.5 | 51.9% | 51.8% | market 50 · ratings 71 · sim 52 | COINFLIP | 1.91 | -0.9% |
| Los Angeles Rams -2.5 | 50.2% | 50.2% | market 51 · ratings 46 · sim 50 | LEAN | 1.91 | -4.1% |
| Denver Broncos +2.5 | 49.8% | 49.8% | market 49 · ratings 54 · sim 50 | COINFLIP | 1.91 | -5.0% |
| Over 44.5 | 48.1% | 48.1% | market 50 · ratings 29 · sim 48 | COINFLIP | 1.91 | -8.1% |
| Denver Broncos ML | 45.0% | 44.9% | market 44 · ratings 50 · sim 45 | SPLIT | 2.20 | -1.1% |

Grades: LOCK ≥70% · PICK ≥62% · LEAN below · SPLIT = a weighted lens disagrees on the side. Win % never means guaranteed; EV shows whether the price pays enough for that win rate.
