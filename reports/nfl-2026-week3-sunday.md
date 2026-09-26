# NFL 2026 Week 3 — Sunday, Sept 27

Lines captured: 2026-09-26 — Manual snapshot from web-search result snippets (sportsbook pages could not be fetched from the build container). Lines move — re-run with --live and ODDS_API_KEY before betting.
Model: market-implied NFL margin distribution with key numbers, σ=11 (fitted to 14 spread/ML pairs), 100,000 Monte Carlo sims (seed 20260927).
Fair probabilities are the market's own no-vig view. A positive EV only appears where a price beats that consensus.

## Board

| Game | Kick (ET) | Spread (home) | Fair line | Home win (ML, no-vig) | Spread-implied | Gap | Proj. total |
|---|---|---|---|---|---|---|---|
| LAC@BUF | 13:00 | -7 | -7.5 | 75.7% | 75.0% | +0.64 | 50.5 |
| CAR@CLE | 13:00 | 2.5 | +1.5 | 42.8% | 45.3% | -2.51 | 42.5 |
| NYJ@DET | 13:00 | -6.5 | -6.5 | 72.5% | 72.4% | +0.2 | 47.5 |
| HOU@IND | 13:00 | 1.5 | +1.5 | 42.5% | 47.4% | -4.88 | 42.5 |
| KC@MIA | 13:00 | 10.5 | +11 | 15.9% | 15.2% | +0.7 | 45.5 |
| CIN@PIT | 13:00 | 3.5 | +3.5 | 37.8% | 36.2% | +1.59 | 42.5 |
| SEA@WAS | 13:00 | 6.5 | +7 | 26.3% | 27.7% | -1.34 | 40.39 |
| NE@JAX | 13:00 | -3 | -2.5 | 59.1% | 59.3% | -0.16 | 45.5 |
| TEN@NYG | 13:00 | -2.5 | -1.5 | 57.5% | 54.7% | +2.75 | 38.5 |
| MIN@TB | 16:05 | 2.5 | +1 | 45.7% | 45.3% | +0.42 | 43.5 |
| ARI@SF | 16:05 | -8.5 | -9 | 78.7% | 79.9% | -1.23 | 47.5 |
| DAL@BAL (Rio) | 16:25 | -3 | -2.5 | 60.7% | 58.2% | +2.51 | 52.66 |
| LV@NO | 16:25 | -3.5 | -3.5 | 61.8% | 63.8% | -1.96 | 43.61 |
| LAR@DEN | 20:20 | 2.5 | +1.5 | 43.4% | 45.3% | -1.87 | 44.5 |

## Most likely winners (win % first, EV guard-railed)

Best-hitting bet per game at a quoted price, ranked by win probability. Anything worse than -5% EV is dropped — a -1000 favorite "usually wins" but still loses money.

| # | Bet | Price | Win % | EV | Verdict |
|---|---|---|---|---|---|
| 1 | Kansas City Chiefs ML | -650 | 84.4% | -2.58% | LEAN (small -EV) |
| 2 | San Francisco 49ers ML | -455 | 79.3% | -3.28% | LEAN (small -EV) |
| 3 | Buffalo Bills ML | -370 | 75.3% | -4.29% | LEAN (small -EV) |
| 4 | Seattle Seahawks ML | -330 | 73.0% | -4.84% | LEAN (small -EV) |
| 5 | Detroit Lions ML | -300 | 72.5% | -3.4% | LEAN (small -EV) |
| 6 | Cincinnati Bengals ML | -184 | 63.0% | -2.76% | LEAN (small -EV) |
| 7 | New Orleans Saints ML | -180 | 62.8% | -2.29% | LEAN (small -EV) |
| 8 | Baltimore Ravens ML | -157 | 59.5% | -2.68% | LEAN (small -EV) |

## Top 10 bets by EV (vs. market consensus)

| # | Bet | Price | Book | Fair win % | Push % | EV | ½-Kelly | Price source |
|---|---|---|---|---|---|---|---|---|
| 1 | Dallas Cowboys ML | +155 | Fanatics (search snippet) | 40.6% | 0.0% | +3.39% | 1.09% | quoted |
| 2 | Indianapolis Colts ML | +125 | FanDuel Research (search snippet) | 45.0% | 0.0% | +1.21% | 0.48% | quoted |
| 3 | Houston Texans -1.5 | -110 | spread source | 52.4% | 0.0% | +0.13% | 0.07% | ASSUMED -110 |
| 4 | Miami Dolphins ML | +540 | unnamed book (search snippet) | 15.6% | 0.0% | -0.36% | 0% | quoted |
| 5 | New York Jets ML | +260 | unnamed book (search snippet) | 27.6% | 0.0% | -0.83% | 0% | quoted |
| 6 | Tennessee Titans ML | +125 | unnamed book (search snippet) | 43.9% | 0.0% | -1.17% | 0% | quoted |
| 7 | Cleveland Browns ML | +124 | FanDuel Research (search snippet) | 44.0% | 0.0% | -1.33% | 0% | quoted |
| 8 | Baltimore Ravens -3 | -104 | spread source | 50.2% | 9.2% | -1.4% | 0% | quoted |
| 9 | Washington Commanders ML | +265 | unnamed book (search snippet) | 27.0% | 0.0% | -1.55% | 0% | quoted |
| 10 | New York Giants -2.5 | -110 | spread source | 51.4% | 0.0% | -1.91% | 0% | ASSUMED -110 |

2 bet(s) show positive EV at a quoted price. Each one depends on that exact book still offering that price.

## Flags

- **HOU@IND**: ML_SPREAD_DISAGREE: ML says 42.6% vs spread-implied 47.4% — the cheaper market is on the home ML / away spread (spread juice not in source — assumed -110; confirm before acting)

## Slate scenarios (Monte Carlo)

- Expected outright upsets: **4.94** of 14 games
- P(at least 3 upsets): 92.3% · P(at least 5): 58.8% · P(zero upsets): 0.2%
- Expected favorites covering: **6.91**

## Best-EV parlays from the ranked legs (independent games)

| Legs | Price | Hit % (analytic) | Hit % (sim) | EV |
|---|---|---|---|---|
| Dallas Cowboys ML (+155, Fanatics (search snippet))<br>Indianapolis Colts ML (+125, FanDuel Research (search snippet))<br>Miami Dolphins ML (+540, unnamed book (search snippet)) | +3572 | 2.8% | 2.9% | +5.61% |
| Dallas Cowboys ML (+155, Fanatics (search snippet))<br>Indianapolis Colts ML (+125, FanDuel Research (search snippet)) | +474 | 18.2% | 18.3% | +4.87% |
| Dallas Cowboys ML (+155, Fanatics (search snippet))<br>Indianapolis Colts ML (+125, FanDuel Research (search snippet))<br>Cleveland Browns ML (+124, FanDuel Research (search snippet)) | +1185 | 8.0% | 8.1% | +3.56% |
| Dallas Cowboys ML (+155, Fanatics (search snippet))<br>Miami Dolphins ML (+540, unnamed book (search snippet)) | +1532 | 6.3% | 6.3% | +3.06% |
| Dallas Cowboys ML (+155, Fanatics (search snippet))<br>Miami Dolphins ML (+540, unnamed book (search snippet))<br>New York Jets ML (+260, unnamed book (search snippet)) | +5775 | 1.7% | 1.8% | +2.93% |

Parlays multiply the vig; they are only +EV when every leg is individually +EV.

## Source notes

- **LAC@BUF**: BUF -7 at DK/Caesars/Fanatics/BetMGM, -7.5 at FanDuel/bet365; Total 50 at BetMGM/Caesars/Fanatics, 50.5 at DK/FD/bet365; Another snippet listed BUF -340 with no LAC price
- **NYJ@DET**: Snippets disagree on total (46.5 / 47.5 / 48.5); one snippet said DET by 10 — treated as a model projection, not a line
- **HOU@IND**: Nico Collins (hamstring) questionable for HOU per Sports Interaction headline
- **KC@MIA**: Total opened 44.5; MIA WR injuries (Caleb Douglas) per team-site tracker
- **CIN@PIT**: Total reported opening 47.5 (another snippet: 43.5); PIT: Joey Porter Jr. out; Rico Dowdle (toe) DNP; Burrow off report
- **SEA@WAS**: Jayden Daniels (elbow) out — Marcus Mariota starts; Look-ahead line was WAS +1.5 before the injury; spread quoted 6.5–7.5 across snippets
- **NE@JAX**: Home/away not confirmed from a primary source — verify venue
- **TEN@NYG**: Home/away not confirmed from a primary source — verify venue
- **MIN@TB**: ML is the opening number; total 43.5 FanDuel / 44.5 elsewhere
- **ARI@SF**: ESPN FPI reportedly 90% SF
- **DAL@BAL (Rio)**: Neutral site: Maracanã, Rio de Janeiro. 'home' = Baltimore for math only; Some books BAL -3.5 (-105)
- **LV@NO**: Saints home opener
- **LAR@DEN**: Sunday Night Football (NBC); Total 43.5 at DraftKings, 44.5 elsewhere; One search summary contradicted itself on the favorite; majority of snippets have LAR -2.5
