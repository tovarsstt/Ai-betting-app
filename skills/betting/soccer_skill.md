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
straight Win/ML ticket dies on the draw. Before backing any favourite, price
the draw and pick the market that survives it:
- **Favourite wins ≥60% in model** → straight **Win / ML**. Dominant enough.
- **Better but wins <60% AND draw ≥26%** → **Double Chance (gana o empata, 1X)**.
  Cashes on win OR draw. This is the play we missed on the Canada draw.
- **Tight match (win≈lose) + high draw** → **Draw No Bet (apuesta sin empate)**.
  Refund on the draw, only loses if the dog actually wins.
- Still take the straight Win as a **higher-payout value alt** when its price
  carries real +EV over the draw risk.
- Engine: `POST /predict-soccer` (edge_api, port 8001) returns the full board
  (1X2 / DC / DNB / O-U / BTTS / corners) + the recommended draw-insured pick.
  Built on bivariate Poisson + Dixon-Coles (calibrates 0-0 / 1-1 draws).

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
*Soccer v3.0 — Caveman Locks. World Cup 2026.*
