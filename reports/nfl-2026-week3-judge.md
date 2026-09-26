# Judge — NFL 2026 Week 3 — Sunday, Sept 27

Rule: **win probability first, price second.** 2,000,000 Monte Carlo games per matchup + 2,000,000 Bernoulli slips per parlay. NFL σ=10.75 (fitted to this slate). Ran in 19.7s.
Lines: 2026-09-26 — Manual snapshot from web-search result snippets (sportsbook pages could not be fetched from the build container). Lines move — re-run with --live and ODDS_API_KEY before betting.

## Best winning pick per game (ranked by win %)

| # | Game | Pick | Win % | 2M-sim % | Market | Ratings | Grade | Price | Fair | EV (2nd) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Kansas City Chiefs @ Miami Dolphins | **Kansas City Chiefs ML** | **83.5%** | 83.5% | 84.7% | 65.8% | LOCK | 1.15 | 1.2 | -3.7% |
| 2 | Arizona Cardinals @ San Francisco 49ers | **San Francisco 49ers ML** | **79.8%** | 79.8% | 79.6% | 80.6% | LOCK | 1.22 | 1.25 | -2.6% |
| 3 | Los Angeles Chargers @ Buffalo Bills | **Buffalo Bills ML** | **77.1%** | 77.1% | 75.6% | 84.0% | LOCK | 1.27 | 1.3 | -2.0% |
| 4 | New York Jets @ Detroit Lions | **Detroit Lions ML** | **74.0%** | 73.9% | 72.7% | 79.1% | LOCK | 1.33 | 1.35 | -1.4% |
| 5 | Seattle Seahawks @ Washington Commanders | **Seattle Seahawks ML** | **72.1%** | 72.0% | 73.3% | 67.2% | LOCK | 1.30 | 1.39 | -6.0% |
| 6 | Las Vegas Raiders @ New Orleans Saints | **New Orleans Saints ML** | **65.1%** | 65.1% | 63.0% | 79.9% | PICK | 1.56 | 1.54 | +1.3% |
| 7 | Cincinnati Bengals @ Pittsburgh Steelers | **Cincinnati Bengals ML** | **61.2%** | 61.1% | 63.1% | 39.0% | LEAN | 1.54 | 1.63 | -5.5% |
| 8 | Dallas Cowboys @ Baltimore Ravens | **Baltimore Ravens ML** | **60.5%** | 60.5% | 59.6% | 63.8% | LEAN | 1.64 | 1.65 | -1.0% |
| 9 | New England Patriots @ Jacksonville Jaguars | **Jacksonville Jaguars ML** | **57.2%** | 57.1% | 59.3% | 30.1% | LEAN | 1.62 | 1.75 | -7.1% |
| 10 | Los Angeles Rams @ Denver Broncos | **Los Angeles Rams ML** | **54.6%** | 54.5% | 55.7% | 50.4% | LEAN | 1.69 | 1.83 | -7.8% |
| 11 | Carolina Panthers @ Cleveland Browns | **Carolina Panthers ML** | **53.9%** | 53.8% | 56.0% | 27.3% | LEAN | 1.68 | 1.86 | -9.7% |
| 12 | Tennessee Titans @ New York Giants | **New York Giants ML** | **53.8%** | 53.7% | 56.1% | 38.7% | LEAN | 1.67 | 1.86 | -10.3% |
| 13 | Houston Texans @ Indianapolis Colts | **Houston Texans ML** | **53.1%** | 53.0% | 55.0% | 28.2% | LEAN | 1.67 | 1.88 | -11.6% |
| 14 | Minnesota Vikings @ Tampa Bay Buccaneers | **Tampa Bay Buccaneers +2.5** | **52.4%** | 52.5% | 50.3% | 64.3% | LEAN | 1.91 | 1.91 | +0.1% |

## Best winning parlays (Bernoulli sims, one leg per game)

| Legs | Hit % (sim) | Hit % (exact) | Payout | EV (2nd) |
|---|---|---|---|---|
| Kansas City Chiefs ML @ 1.15 (83%)<br>San Francisco 49ers ML @ 1.22 (80%) | **66.7%** | 66.6% | 1.41 | -6.1% |
| Kansas City Chiefs ML @ 1.15 (83%)<br>Buffalo Bills ML @ 1.27 (77%) | **64.4%** | 64.4% | 1.47 | -5.6% |
| Kansas City Chiefs ML @ 1.15 (83%)<br>Detroit Lions ML @ 1.33 (74%) | **61.8%** | 61.8% | 1.54 | -5.0% |
| San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%) | **61.6%** | 61.6% | 1.55 | -4.6% |
| Kansas City Chiefs ML @ 1.15 (83%)<br>Seattle Seahawks ML @ 1.30 (72%) | **60.2%** | 60.2% | 1.50 | -9.4% |
| San Francisco 49ers ML @ 1.22 (80%)<br>Detroit Lions ML @ 1.33 (74%) | **59.0%** | 59.0% | 1.63 | -4.1% |
| Kansas City Chiefs ML @ 1.15 (83%)<br>San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%) | **51.4%** | 51.4% | 1.79 | -8.0% |
| Kansas City Chiefs ML @ 1.15 (83%)<br>San Francisco 49ers ML @ 1.22 (80%)<br>Buffalo Bills ML @ 1.27 (77%)<br>Detroit Lions ML @ 1.33 (74%) | **38.1%** | 38.0% | 2.38 | -9.3% |

## Per game — every market, every lens

### Los Angeles Chargers @ Buffalo Bills
Expected home margin — blended +8.0 | market +7.5 | ratings +10.7 · weights {'market': 0.65, 'ratings': 0.1306, 'agents': 0.0}

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Buffalo Bills ML | 77.1% | 77.1% | market 76 · ratings 84 · sim 77 | LOCK | 1.27 | -2.0% |
| Buffalo Bills -5.5 (Stake) | 59.3% | 59.3% | market 57 · ratings 69 · sim 59 | LEAN | 1.67 | -1.0% |
| Over 50.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 50.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Buffalo Bills -7 | 48.8% | 48.8% | market 47 · ratings 59 · sim 49 | SPLIT | 1.91 | -6.9% |
| Los Angeles Chargers +7 | 44.7% | 44.6% | market 47 · ratings 35 · sim 45 | SPLIT | 1.91 | -14.7% |
| Los Angeles Chargers ML | 22.9% | 22.8% | market 24 · ratings 16 · sim 23 | SPLIT | 3.95 | -9.8% |

### Carolina Panthers @ Cleveland Browns
Expected home margin — blended -1.1 | market -1.6 | ratings +6.5 · weights {'market': 0.65, 'ratings': 0.05, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home +6.5, market -1.6 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Carolina Panthers ML | 53.9% | 53.8% | market 56 · ratings 27 · sim 54 | LEAN | 1.68 | -9.7% |
| Cleveland Browns +2.5 | 50.9% | 50.9% | market 49 · ratings 76 · sim 51 | COINFLIP | 1.91 | -2.8% |
| Over 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Carolina Panthers -2.5 | 49.1% | 49.1% | market 51 · ratings 24 · sim 49 | LEAN | 1.91 | -6.3% |
| Cleveland Browns ML | 46.1% | 46.0% | market 44 · ratings 73 · sim 46 | SPLIT | 2.24 | +3.3% |

### New York Jets @ Detroit Lions
Expected home margin — blended +6.9 | market +6.5 | ratings +8.7 · weights {'market': 0.65, 'ratings': 0.1528, 'agents': 0.0}

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Detroit Lions ML | 74.0% | 73.9% | market 73 · ratings 79 · sim 74 | LOCK | 1.33 | -1.4% |
| Detroit Lions -3.5 (Stake) | 60.9% | 60.8% | market 59 · ratings 67 · sim 61 | LEAN | 1.61 | -2.0% |
| Detroit Lions -6.5 | 51.4% | 51.3% | market 50 · ratings 58 · sim 51 | SPLIT | 1.91 | -1.9% |
| Over 47.5 | 50.0% | 49.9% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 47.5 | 50.0% | 50.1% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| New York Jets +6.5 | 48.6% | 48.7% | market 50 · ratings 42 · sim 49 | SPLIT | 1.91 | -7.2% |
| New York Jets ML | 26.0% | 25.9% | market 27 · ratings 21 · sim 26 | SPLIT | 3.60 | -6.3% |

### Houston Texans @ Indianapolis Colts
Expected home margin — blended -0.8 | market -1.4 | ratings +6.2 · weights {'market': 0.65, 'ratings': 0.05, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home +6.2, market -1.4 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Houston Texans ML | 53.1% | 53.0% | market 55 · ratings 28 · sim 53 | LEAN | 1.67 | -11.6% |
| Houston Texans -1.5 | 50.4% | 50.4% | market 52 · ratings 26 · sim 50 | LEAN | 1.91 | -3.7% |
| Over 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Indianapolis Colts +1.5 | 49.6% | 49.5% | market 48 · ratings 74 · sim 50 | SPLIT | 1.91 | -5.4% |
| Indianapolis Colts ML | 46.9% | 46.8% | market 45 · ratings 72 · sim 47 | SPLIT | 2.25 | +5.6% |

### Kansas City Chiefs @ Miami Dolphins
Expected home margin — blended -10.5 | market -11.0 | ratings -4.4 · weights {'market': 0.65, 'ratings': 0.0583, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home -4.4, market -11.0 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 6%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Kansas City Chiefs ML | 83.5% | 83.5% | market 85 · ratings 66 · sim 83 | LOCK | 1.15 | -3.7% |
| Miami Dolphins +10.5 | 53.1% | 53.0% | market 51 · ratings 74 · sim 53 | LEAN | 1.91 | +1.4% |
| Over 45.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 45.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Kansas City Chiefs -10.5 | 46.9% | 46.9% | market 49 · ratings 26 · sim 47 | COINFLIP | 1.91 | -10.5% |
| Kansas City Chiefs -10.5 (Stake) | 46.9% | 46.9% | market 49 · ratings 26 · sim 47 | COINFLIP | 1.90 | -10.9% |
| Miami Dolphins ML | 16.5% | 16.4% | market 15 · ratings 34 · sim 16 | SPLIT | 6.40 | +5.7% |

### Cincinnati Bengals @ Pittsburgh Steelers
Expected home margin — blended -3.1 | market -3.6 | ratings +3.0 · weights {'market': 0.65, 'ratings': 0.0582, 'agents': 0.0}
- 🏥 Pittsburgh Steelers: CB Joey Porter Jr. OUT (-1.5 home margin) [https://www.si.com/betting/bengals-vs-steelers-prediction-odds-spread-injuries-trends-for-nfl-week-3-01m32wwcjkpw]
- ⚠️ RATINGS_DISAGREE: team ratings say home +3.0, market -3.6 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 6%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Cincinnati Bengals ML | 61.2% | 61.1% | market 63 · ratings 39 · sim 61 | LEAN | 1.54 | -5.5% |
| Pittsburgh Steelers +3.5 | 52.9% | 52.9% | market 51 · ratings 73 · sim 53 | LEAN | 1.91 | +1.1% |
| Over 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 42.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Cincinnati Bengals -3.5 | 47.0% | 47.1% | market 49 · ratings 27 · sim 47 | COINFLIP | 1.91 | -10.2% |
| Pittsburgh Steelers ML | 38.8% | 38.7% | market 37 · ratings 61 · sim 39 | SPLIT | 2.54 | -1.5% |

### Seattle Seahawks @ Washington Commanders
Expected home margin — blended -6.3 | market -6.7 | ratings -4.8 · weights {'market': 0.65, 'ratings': 0.1597, 'agents': 0.0}
- 🏥 Washington Commanders: QB Jayden Daniels OUT (dislocated left elbow) — Marcus Mariota starts (-3.5 home margin) [https://www.nfl.com/news/marcus-mariota-commanders-week-3-qb-jayden-daniels-elbow]
- 🏥 Washington Commanders: S Nick Cross ruled OUT (-1.5 home margin) [https://www.si.com/betting/seahawks-vs-commanders-prediction-odds-spread-injuries-trends-for-nfl-week-3-2026]

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Seattle Seahawks ML | 72.1% | 72.0% | market 73 · ratings 67 · sim 72 | LOCK | 1.30 | -6.0% |
| Seattle Seahawks -4.5 (Stake) | 55.5% | 55.5% | market 57 · ratings 50 · sim 56 | LEAN | 1.52 | -15.6% |
| Washington Commanders +6.5 | 50.8% | 50.8% | market 49 · ratings 56 · sim 51 | SPLIT | 1.91 | -3.0% |
| Under 40.5 | 50.4% | 50.4% | market 50 · sim 50 | LEAN | 1.89 | -4.5% |
| Over 40.5 | 49.6% | 49.6% | market 50 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Seattle Seahawks -6.5 | 49.2% | 49.2% | market 51 · ratings 44 · sim 49 | SPLIT | 1.91 | -6.1% |
| Washington Commanders ML | 27.9% | 27.8% | market 27 · ratings 33 · sim 28 | SPLIT | 3.65 | +1.8% |

### New England Patriots @ Jacksonville Jaguars
Expected home margin — blended +2.0 | market +2.5 | ratings -5.6 · weights {'market': 0.65, 'ratings': 0.05, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home -5.6, market +2.5 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 5%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Jacksonville Jaguars ML | 57.2% | 57.1% | market 59 · ratings 30 · sim 57 | LEAN | 1.62 | -7.1% |
| Over 45.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 45.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| New England Patriots +3 | 47.6% | 47.6% | market 45 · ratings 74 · sim 48 | SPLIT | 1.91 | -9.1% |
| Jacksonville Jaguars -3 | 43.0% | 43.0% | market 45 · ratings 19 · sim 43 | SPLIT | 1.91 | -17.9% |
| New England Patriots ML | 42.8% | 42.7% | market 41 · ratings 70 · sim 43 | SPLIT | 2.35 | +0.6% |

### Tennessee Titans @ New York Giants
Expected home margin — blended +1.0 | market +1.7 | ratings -3.1 · weights {'market': 0.65, 'ratings': 0.098, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home -3.1, market +1.7 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 10%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New York Giants ML | 53.8% | 53.7% | market 56 · ratings 39 · sim 54 | LEAN | 1.67 | -10.3% |
| Tennessee Titans +2.5 | 51.0% | 51.0% | market 49 · ratings 66 · sim 51 | COINFLIP | 1.91 | -2.7% |
| Over 38.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 38.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| New York Giants -2.5 | 49.0% | 49.0% | market 51 · ratings 34 · sim 49 | LEAN | 1.91 | -6.4% |
| Tennessee Titans ML | 46.2% | 46.1% | market 44 · ratings 61 · sim 46 | SPLIT | 2.25 | +3.9% |

### Minnesota Vikings @ Tampa Bay Buccaneers
Expected home margin — blended -0.6 | market -1.2 | ratings +2.7 · weights {'market': 0.65, 'ratings': 0.1158, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home +2.7, market -1.2 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 12%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Tampa Bay Buccaneers +2.5 | 52.4% | 52.5% | market 50 · ratings 64 · sim 52 | LEAN | 1.91 | +0.1% |
| Minnesota Vikings ML | 52.3% | 52.2% | market 55 · ratings 40 · sim 52 | SPLIT | 1.77 | -7.4% |
| Over 43.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 43.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Tampa Bay Buccaneers ML | 47.6% | 47.6% | market 45 · ratings 60 · sim 48 | SPLIT | 2.10 | +0.1% |
| Minnesota Vikings -2.5 | 47.6% | 47.5% | market 50 · ratings 36 · sim 48 | SPLIT | 1.91 | -9.2% |

### Arizona Cardinals @ San Francisco 49ers
Expected home margin — blended +9.0 | market +8.9 | ratings +9.3 · weights {'market': 0.65, 'ratings': 0.1913, 'agents': 0.0}

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| San Francisco 49ers ML | 79.8% | 79.8% | market 80 · ratings 81 · sim 80 | LOCK | 1.22 | -2.6% |
| Arizona Cardinals +8.5 | 50.9% | 50.8% | market 51 · ratings 50 · sim 51 | COINFLIP | 1.91 | -2.8% |
| Over 47.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 47.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| San Francisco 49ers -8.5 | 49.1% | 49.2% | market 49 · ratings 50 · sim 49 | COINFLIP | 1.91 | -6.3% |
| Arizona Cardinals ML | 20.2% | 20.1% | market 20 · ratings 19 · sim 20 | SPLIT | 4.50 | -9.2% |

### Dallas Cowboys @ Baltimore Ravens
Expected home margin — blended +2.9 | market +2.6 | ratings +3.8 · weights {'market': 0.65, 'ratings': 0.1744, 'agents': 0.0}

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Baltimore Ravens ML | 60.5% | 60.5% | market 60 · ratings 64 · sim 60 | LEAN | 1.64 | -1.0% |
| Over 52.5 | 50.6% | 50.6% | market 51 · sim 51 | LEAN | 1.88 | -4.5% |
| Under 52.5 | 49.4% | 49.4% | market 49 · sim 49 | COINFLIP | 1.93 | -4.5% |
| Baltimore Ravens -3 | 46.3% | 46.3% | market 45 · ratings 50 · sim 46 | SPLIT | 1.96 | -9.2% |
| Dallas Cowboys +3 | 44.3% | 44.2% | market 45 · ratings 41 · sim 44 | SPLIT | 1.87 | -17.2% |
| Dallas Cowboys ML | 39.5% | 39.4% | market 40 · ratings 36 · sim 39 | SPLIT | 2.55 | +0.8% |

### Las Vegas Raiders @ New Orleans Saints
Expected home margin — blended +4.2 | market +3.6 | ratings +9.0 · weights {'market': 0.65, 'ratings': 0.0836, 'agents': 0.0}
- ⚠️ RATINGS_DISAGREE: team ratings say home +9.0, market +3.6 — season ratings miss today's news (injuries/QB/form); ratings weight cut to 8%

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| New Orleans Saints ML | 65.1% | 65.1% | market 63 · ratings 80 · sim 65 | PICK | 1.56 | +1.3% |
| New Orleans Saints -3.5 | 51.1% | 51.1% | market 49 · ratings 68 · sim 51 | COINFLIP | 1.91 | -2.5% |
| Over 43.5 | 50.4% | 50.4% | market 50 · sim 50 | LEAN | 1.89 | -4.5% |
| Under 43.5 | 49.6% | 49.6% | market 50 · sim 50 | COINFLIP | 1.93 | -4.5% |
| Las Vegas Raiders +3.5 | 48.9% | 48.9% | market 51 · ratings 32 · sim 49 | LEAN | 1.91 | -6.6% |
| Las Vegas Raiders ML | 34.9% | 34.7% | market 37 · ratings 20 · sim 35 | SPLIT | 2.52 | -12.1% |

### Los Angeles Rams @ Denver Broncos
Expected home margin — blended -1.2 | market -1.5 | ratings -0.1 · weights {'market': 0.65, 'ratings': 0.1691, 'agents': 0.0}

| Market | Win % | Sim % | Lenses | Grade | Price | EV |
|---|---|---|---|---|---|---|
| Los Angeles Rams ML | 54.6% | 54.5% | market 56 · ratings 50 · sim 54 | LEAN | 1.69 | -7.8% |
| Denver Broncos +2.5 | 50.2% | 50.2% | market 49 · ratings 54 · sim 50 | SPLIT | 1.91 | -4.1% |
| Over 44.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Under 44.5 | 50.0% | 50.0% | market 50 · sim 50 | COINFLIP | 1.91 | -4.5% |
| Los Angeles Rams -2.5 | 49.8% | 49.8% | market 51 · ratings 46 · sim 50 | SPLIT | 1.91 | -4.9% |
| Denver Broncos ML | 45.4% | 45.3% | market 44 · ratings 50 · sim 45 | SPLIT | 2.20 | -0.1% |

Grades: LOCK ≥70% · PICK ≥62% · LEAN below · SPLIT = a weighted lens disagrees on the side. Win % never means guaranteed; EV shows whether the price pays enough for that win rate.
