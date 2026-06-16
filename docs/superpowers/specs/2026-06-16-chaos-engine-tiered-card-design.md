# Chaos Engine + Tiered Card — Design Spec

**Date:** 2026-06-16
**Project:** Caveman Locks
**Status:** Approved shape, pending spec review

---

## 1. Problem

The engine picks well per-match (value gate, devig, draw insurance) but:

1. It cannot read a **slate** — it never notices when many matches lean the same way ("everyone drew yesterday").
2. It has no deliberate **chaos hunt** — specific heavy favorites that are vulnerable (Panama draws/beats England, Spain fails to beat Cabo Verde).
3. It has no **staking discipline** — picks are not split into safe/value/longshot tiers with bankroll caps, so a degen parlay can erase a week of sharp singles.

The losing history confirms the leak: straight-win parlays and spreads bled money; totals + Double-Chance singles made it. The wins matched the engine's own philosophy; the losses ignored it.

## 2. Goal

A single per-slate pipeline that:

- Runs a **mandatory chaos check on every match with a favorite** (anything can happen).
- Detects **draw-prone spots** (the Canada lesson) from real team data, not vibes.
- Reads the **slate weather** (soft aggregate tilt) as a totals modifier.
- Routes every qualifying pick into **Normal / Mild / Wild** tiers with bankroll-capped sizing.
- Emits a tiered card where **every pick carries a one-line evidence trail** and **nothing is invented**.

### Success criteria

- Tiered card emits per slate: NORMAL / MILD / WILD, each pick with evidence + stake (units & $).
- Chaos detector flags heavy-fav vulnerability and draw spots with cited real reasons; value-gated.
- Wild tier hard-capped at 10% of bankroll/day; never chases.
- **Zero invented stats** — replay of June 11–15 WC results shows what was and was NOT flaggable pre-match.

## 3. Non-Goals (YAGNI)

- **Predicted lineups / XI:** not in the base build (no feed wired). Workaround = ESPN injuries + ESPN news headlines as a cited soft nudge. `api-football` (api-sports.io: predicted XI + club player stats) is a documented **optional Phase 2** — non-breaking, fills the existing lineup/injury slot.
- **Club-vs-country player form:** **not modeled** — no clean data exists anywhere. Soft, cited news nudge only (±5%), never a number.
- No xG / PPDA / SPI — not available from ESPN, never invented.
- No live/in-play engine. Pre-match only.
- No new bookmaker integrations. Use existing ESPN + Odds API data only.

### Data strategy decision (2026-06-16)

The lineup/injury input is built as an **optional, source-agnostic slot** on the DRAW SCORE. Base build populates it from free ESPN injuries + news (cited). If/when `api-football` is wired (Phase 2), the same slot consumes its predicted XI + injuries with zero changes to chaos/staking logic. Missing slot → component skipped and score renormalized. This keeps the money-maker shippable now and the richer data a clean drop-in later.

## 4. Data Reality Contract (the spine — no hallucination)

Only these inputs exist and may be used. Anything else is "unavailable," widens uncertainty, and is never invented.

| Input | Source (already wired) | Use |
|---|---|---|
| W/D/L, GF, GA, GD, PPG, GP | ESPN WC standings | form, parity, low-scoring profile |
| goals/game, clean-sheet rate, GA/game | derived from standings | scoring profile |
| Devigged 1X2 / totals / DC / DNB | Odds API → existing devig | value gate, market draw% |
| Title-strength prior | devigged WC-winner outrights (injected) | class/parity rating |
| Advancement tag (QUALIFIED/ELIMINATED/MUST_WIN/CAN_DRAW) | server-computed | motivation |
| Venue tag (heat/altitude/dome) | server-injected | totals lean |
| Injuries (matchup teams) | ESPN injuries endpoint | lambda nudge **when present**; "no data" otherwise |
| News headlines (keyword-filtered) | ESPN news | soft ±5% nudge, **must cite headline** |
| Dixon-Coles modeled probs | `scripts/soccer_markets.py` / `/predict-soccer` | modeled draw%, totals, BTTS |

**Rules:**
- Every probability cites a real input or the devigged price.
- Narrative (news/motivation) may nudge a probability **±5% max** and must name its source.
- Missing input → component skipped and score renormalized over present inputs; never filled with a guess.

## 5. Architecture

Deterministic math in Python computes all numbers; the LLM only narrates with cited evidence. The model never invents a probability — it reads them.

```
slate
  └─ per match: existing /predict-soccer board (Dixon-Coles + devig)
       └─ chaos_engine.py   → CHAOS flags + DRAW SCORE (per match)
       └─ slate_weather     → OPEN / CAGEY / NORMAL (aggregate, soft)
            └─ staking.py    → tier routing (Normal/Mild/Wild) + unit sizing
                 └─ heuristics/LLM → tiered card, evidence lines, stakes
```

### 5.1 `chaos_engine.py` (new, deterministic)

Runs on every match that has a favorite. Produces, per match:

**Inflation gap:** `fav_implied (devig) − fav_fair (model/form)`. Positive = chalk overpriced.

**Graded chaos flag:**
- Heavy fav (price ≤ 1.50) AND inflation ≥ threshold AND dog has equity → **Chaos-Full** (dog ML / X2).
- Mid fav (1.50–1.90) AND high draw equity → **Chaos-Lite** (draw X / X2).
- else → no flag (note only).

**DRAW SCORE (0–1)** — weighted over present components, renormalized:
1. Parity — small title-strength gap + tight devigged 1X2.
2. Low-scoring profile — both teams low GF/game and/or low GA.
3. Motivation — `CAN_DRAW` / `QUALIFIED` (rotation) bumps.
4. Model-vs-market gap — Dixon-Coles draw% − market devigged draw% (positive → underpriced draw).
5. Injury/news nudge — key attacker out → +draw/under, ±5% cap, cited; skipped if no data.

A draw becomes a **pick** only if model draw% > market draw% AND the draw price clears the value gate. Otherwise it is a note.

Each flag/score carries `evidence[]` (the exact stats/prices it leans on) and a `value_check` boolean.

### 5.2 `slate_weather` (aggregate, soft)

Counts the share of the card leaning Under and leaning Draw. Emits `OPEN / CAGEY / NORMAL`. Only nudges totals leans. **Not** chaos (explicitly demoted per user correction).

### 5.3 `staking.py` (new)

- Config: `BANKROLL` (default $200, user-set), split **70% Normal / 20% Mild / 10% Wild**, unit = 1% bankroll.
- Routing by win-prob band + chaos grade:
  - **Normal** ≥ 58% — totals, DC, DNB (the proven winners).
  - **Mild** 40–58% — priced draw, team total, 2-leg DC SGM, Chaos-Lite.
  - **Wild** < 40% + real chaos edge — Chaos-Full / specific upset.
- Sizing: each tier shares its pool; **each Wild pick ≤ 0.25u**, hard daily Wild cap so longshots can't drain the bank.
- Immutable updates only (returns new objects per coding-style rules).

### 5.4 Heuristics update

`skills/betting/global_heuristics.md`, `skills/betting/soccer_skill.md`, `src/prompts/heuristics.ts`:
- Add the mandatory chaos pass + DRAW SCORE consumption.
- Add the no-hallucination data contract (Section 4).
- Add the tiered output format.

### 5.5 Card output

Game Breakdown renders **NORMAL / MILD / WILD** sections. Each pick: market + price + one-line evidence + stake (units & $). Header shows slate weather tag and the day's chaos flags.

## 6. Error Handling

- Any data fetch fails → that component is "unavailable," pipeline continues, score renormalizes. Never blocks the card.
- No favorite in a match → chaos check skipped for it (logged).
- No pick clears the value gate in a tier → tier prints "PASS — no value today." Forcing a pick is forbidden.

## 7. Testing

- **Replay harness:** feed June 11–15 WC results (Canada–Bosnia draw, Spain–Cabo Verde, the draw cluster) using only pre-match data. Report which the detector flags and which it honestly could not. No API calls in test (per CLAUDE.md) — use fixtures.
- Unit tests: chaos inflation math, DRAW SCORE weighting + renormalization on missing inputs, tier-band routing, staking caps, immutability.
- Target ≥ 80% coverage on the new modules.

## 8. Open Questions

- Exact inflation threshold per grade — tune on the replay harness, not guessed.
- Whether ESPN injuries actually populate for WC national teams — the replay reveals coverage; design already treats it as optional.
