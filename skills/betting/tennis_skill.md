# TENNIS — NICHE HEURISTICS v3.1
# 🎾 PIPELINE: Roland Garros (CLAY) → Wimbledon (GRASS) late June → US Open (HARD) Aug

---

## ⚙️ DATA RULES (never hallucinate)
- **ATP + WTA both supported** — the model is points+surface based, tour-agnostic. Pass the right `surface`; WTA prices exactly like ATP.
- **Odds come from the live board ONLY.** The app auto-discovers every active `tennis_*` tournament from the Odds API `/sports` endpoint and pulls real prices. NEVER invent a tennis odd — if a price isn't on the board or supplied by the user, say "no line", don't estimate one.
- **Ranks publish every Monday.** Auto-refreshed weekly (`fetch_tennis_ratings.py` cron, or `POST /api/refresh-rankings`). If `predict` returns `ranks_stale`, say so and refresh before trusting a rank-driven edge.
- **`bet_signal`/`edge_strength` are live for tennis** (prob-edge based, fixed 2026-06-25). STRONG = ≥10pt model-vs-market prob edge + EV>5%.
- **Live/in-play re-pricing (2026-07-01):** pass `sets_won_home`/`sets_won_away`/`best_of` to `/predict` for a match in progress and the model re-prices off the ACTUAL set score (`scripts/tennis_live.py`) instead of only showing the pregame number. `profile`'s `live` block shows the pregame vs live prob when active — use the live one.
- **Sofascore cross-check tool (2026-07-01):** `GET /sofascore/player?name=`, `/sofascore/h2h?home=&away=`, `/sofascore/odds/{event_id}`, `/sofascore/stats/{event_id}` (`scripts/sofascore.py`) — an UNOFFICIAL API, no public docs, may block/rate-limit. Use it to spot-check a surprising model read (this is exactly how the H2H surname-first bug got found and fixed), not as a silent second model — it's not wired into the automatic pick pipeline. `status: ERROR` means the call failed (connectivity/schema drift), not that the fact is wrong; `NOT_FOUND`/`NO_MEETING_FOUND` are honest no-data responses.

---

## MODEL OUTPUT — COMPARATIVE PROFILE (now real, not estimated)
The win-prob model returns a `profile` block (home − away, surface-aware) built from
REAL results. Cite these — they are data, not guesses:
- **H2H** — recency-weighted, SAME-SURFACE when available (clay H2H ≠ grass H2H).
- **form** — recency-weighted recent win-rate edge.
- **psych** — win-rate after dropping the first set (fighter vs folder).
- **clutch** — deciding-set + tiebreak-set win-rate, PLUS real break-point save/convert % for ATP (`fetch_tennis_serve_stats.py`, source: Tennismylife/TML-Database — Sackmann's original repos are gone from GitHub as of 2026-07-01). WTA still deciding-set/tiebreak only — no live-updated WTA serve-stat source found yet.
- **streak** — current W/L run.

The model blends points + surface + this profile, **capped** so profile refines but never
flips a clear points favorite (winning-priority rule). Read the model's win% first.

### ⚠️ DAY-OF OVERRIDE (non-negotiable)
Confirmed day-of data — injury, withdrawal, illness, weather/conditions, late lineup —
ALWAYS beats this historical model when they conflict. Player hurt or just withdrew →
ignore the model edge. Never bet a player whose fitness is in question pre-warmup.

### ⚠️ SCHEDULE / TANK RISK (non-negotiable)
A player entered in a SMALLER event who is CONFIRMED in the main draw of a BIG event
(Slam / Masters / WTA 1000) starting **less than 5 days later** is more likely to
underperform or lose — they manage load and avoid injury risk on the small stage.
- FADE that player (especially their short-priced ML); favor the fully-committed opponent.
- Strongest signal: a seed in a 250 / WTA 250 / challenger the week before a Slam.
- This is a SCHEDULE read — requires the real upcoming draw. Confirm the big-event entry
  before applying. No confirmed entry → do not assume.

### 🔎 PROFILE ON DEMAND (never hallucinate)
Every match analysis needs a comparative profile for BOTH players. If one player has a
model profile and the other does NOT (qualifier / challenger not in our data):
1. Look up the missing player's **REAL** recent results (ESPN, official tour, results
   sites) — surface record, recent form, any H2H, deciding-set/tiebreak record.
2. Build their profile from ACTUAL matches only. Cite where the numbers came from.
3. NEVER invent or estimate stats. If real data cannot be found, state plainly
   "no profile data — not estimating" and lean on market devig + surface only.

---

## SURFACE PIPELINE — THE EDGE WINDOW

### NOW: Roland Garros (CLAY) — Final Stages
- Clay grinders at peak value. Heavy topspin, high endurance, rally length.
- Big servers fade. Flat hitters neutralized by slow bounce.
- Clay-specific Elo > overall ranking. Always cite surface win%.

### UPCOMING: Wimbledon (GRASS) — Late June
- **SURFACE FLIP = THE ALPHA WINDOW. Biggest edge opportunity of the tennis calendar.**
- Books lag 1-2 weeks updating surface Elo. Clay Elo still in the model.
- Clay grinders MASSIVELY overbet by public rounds 1-2. Fade them.
- Big servers UNDERVALUED coming off clay. Back before books adjust.
- Transition week (Queen's Club / Halle) = maximum inefficiency.
- First set → match winner: **72% on grass** (highest of any surface).
- Serve hold rate ~90% on grass. Lean Under on total breaks. Under on total games.
- Net rushers / serve-and-volleyers: peak value rounds 1-3.

### HARD: US Open / Australian Open
- Most neutral. Overall Elo most predictive.
- US Open night sessions: faster ball under lights. Lean big servers slightly.
- AO January heat: heat policy suspensions possible. Factor retirement risk.

---

## NICHE STATS — ALWAYS CITE
- **Surface Win %**: More predictive than ATP ranking. #15 can be 70%+ clay.
- **Surface-Specific Elo**: Gap >100 pts vs opponent = edge. >200 = back with conviction.
- **1st Serve % In**: >65% = reliable. <58% = vulnerable, lean break of serve.
- **Ace Rate**: >10 aces/match on grass/hard = strong hold rate. Lean Under on breaks.
- **Break Point Conversion %**: >45% = aggressive returner. Lean Over on total breaks.
- **2nd Serve Speed**: <140 km/h = attackable. "Break in Set 1" play on the returner.
- **Return Points Won %**: >40% = elite returner. Key for game handicap sizing.
- **Rolling Match Load (sets in 14 days)**: >15 sets = HIGH FATIGUE. Fade ML regardless of ranking.
- **H2H on specific surface**: Weight last 2 years 3x vs older meetings. Overall H2H is misleading.

---

## FATIGUE (non-negotiable rules)
- 5-set match + <48hr = RETIREMENT/INJURY RISK. Never bet their ML.
- Deep run prior event (SF/Final) → hangover in rounds 1-2 next. Fade.
- Players 30+ in 5-set Slams: Fatigue degrades sharply after 3 sets. Fade late sets.
- Rolling sets >15 in 14 days = HIGH FATIGUE. Back the opponent even if lower-ranked.

---

## GAME HANDICAP RULES
- Favorites past -200 ML: Use **Game Handicap -4.5** instead. Better ROI.
  At -300 ML you need 75% to break even. At -4.5 games: usually -130 to -150.
- Underdogs +150 to +300: Profitable on ML due to plus-money. Target surface specialists.
- Best-of-5 underdogs: Cover game handicap at higher rate than BO3. Variance helps them.

---

## CONDITIONS
- Altitude (Bogota, Mexico City): Ball faster. Favor big servers. Under on breaks.
- Heat >35°C: Over total games (fatigue = more breaks = longer sets).
- Indoor: Faster. Favors servers.
- Night sessions: Cooler, heavier ball. Slight baseline grinder edge.
- **Grass surface**: Last-minute scratch risk is high (ankle rolls on slick courts). Only bet after warmup confirmation.

---

## SGP / PROP RULES
- Aces + Match Winner (big server on grass): Strong positive correlation.
- Total Games Over + Underdog +Games: If tight match expected, both correlate.
- NEVER: Total Games Under + Underdog ML. Contradictory — underdog winning means more games.

---

## SHARP SIGNALS
- Opening line moves 3+ games vs public lean = sharp on other side. Follow it.
- Wimbledon rounds 1-2: Surface Elo gap >150 = bet grass specialist even if ranked lower.
- Pinnacle sharper than DK/FD by 15+ cents on ML = follow Pinnacle.

---
*Tennis v3.0 — Caveman Locks. Surface transition is the alpha.*
