# Chaos Engine + Tiered Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic per-slate "chaos engine" (chaos flags + DRAW SCORE) and a bankroll-tiered card (Normal/Mild/Wild) to Caveman Locks, grounded only in real data, with a fixture replay harness.

**Architecture:** Two new pure-Python modules in `scripts/` next to `soccer_markets.py`. `chaos_engine.py` consumes the devigged 1X2 + Dixon-Coles board the engine already produces (via `soccer_markets.py` / `/predict-soccer`) and emits per-match chaos grade + DRAW SCORE + slate weather. `staking.py` routes value-cleared candidates into Normal/Mild/Wild tiers with bankroll caps. Heuristic `.md` files tell the LLM to consume these numbers and render the tiered card with cited evidence. No network in any module or test.

**Tech Stack:** Python 3.13, stdlib + existing `soccer_markets.py`. Tests: pytest 9.x via **system** `python3` (run from repo root; pytest prepend-import resolves `import soccer_markets`). No new dependencies.

---

## File Structure

- Create `scripts/chaos_engine.py` — `TeamForm`, `MatchInput`, `ChaosResult` dataclasses; `draw_score()`, `assess_match()`, `slate_weather()`. Imports `soccer_markets as sm` to reuse `upset_risk`.
- Create `scripts/staking.py` — `Candidate`, `TierConfig`, `StakedPick` dataclasses; `route_tier()`, `size_card()`. No imports beyond stdlib.
- Create `scripts/test_chaos_engine.py` — unit tests (pure math).
- Create `scripts/test_staking.py` — unit tests (pure math).
- Create `scripts/fixtures/wc_2026_jun11_15.json` — illustrative pre-match fixtures for the replay harness (NOT live odds; deterministic test input).
- Create `scripts/replay_wc.py` — loads fixtures, runs `assess_match`, prints flagged vs actual + honest "not-flaggable" list.
- Create `scripts/test_replay_wc.py` — asserts the Canada-draw spot flags CHAOS-LITE.
- Modify `skills/betting/global_heuristics.md` — add Rule 10 (mandatory chaos pass + DRAW SCORE + tiered output format).
- Modify `skills/betting/soccer_skill.md` — add the CHAOS / DRAW SCORE section.
- Modify `scripts/edge_api.py` — add `POST /chaos-slate` endpoint exposing the pipeline.

All run commands assume CWD = repo root: `/Users/josetovar/Documents/APP AI BETS`.

---

### Task 1: `chaos_engine.py` — data model + `draw_score()`

**Files:**
- Create: `scripts/chaos_engine.py`
- Test: `scripts/test_chaos_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_chaos_engine.py
"""Tests for the chaos engine. Pure math — no network, no API."""
import chaos_engine as ce


def _canada_bosnia() -> ce.MatchInput:
    # Modest favourite (Canada) with a live draw — the Canada lesson.
    return ce.MatchInput(
        home=ce.TeamForm(name="Canada", gf=1, ga=1, gp=1, strength=0.02),
        away=ce.TeamForm(name="Bosnia", gf=1, ga=1, gp=1, strength=0.01),
        market_home=0.50, market_draw=0.27, market_away=0.23,
        fav_decimal_odds=1.83, draw_decimal_odds=3.40,
        model_home=0.46, model_draw=0.31, model_away=0.23,
        home_tag="CAN_DRAW", away_tag=None,
    )


def test_draw_score_in_unit_interval():
    out = ce.draw_score(_canada_bosnia())
    assert 0.0 <= out["draw_score"] <= 1.0


def test_draw_score_cites_evidence_for_each_present_component():
    out = ce.draw_score(_canada_bosnia())
    # parity + low_scoring + motivation + model_gap all present here
    assert set(out["components"]) >= {"parity", "low_scoring", "motivation", "model_gap"}
    assert len(out["evidence"]) >= 4


def test_missing_model_drops_model_gap_component_no_invention():
    m = _canada_bosnia()
    m_no_model = ce.replace_model(m, None, None, None)
    out = ce.draw_score(m_no_model)
    assert "model_gap" not in out["components"]
    assert 0.0 <= out["draw_score"] <= 1.0  # renormalized over present components
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chaos_engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/chaos_engine.py
"""
Chaos engine — Caveman Locks.

Deterministic, no network. Consumes the devigged 1X2 + Dixon-Coles board the
engine already produces and emits, per match:
  - a DRAW SCORE (0-1) built only from real data (parity, low-scoring profile,
    motivation tag, model-vs-market draw gap, cited injury/news nudge),
  - a graded CHAOS flag (NONE / LITE / FULL) for vulnerable favourites,
  - an evidence trail (every component names the stat/price it leans on).

No-hallucination contract: a component is included ONLY when its inputs are
present; the score is renormalized over present components. Missing data is
never filled with a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import soccer_markets as sm

# Tunable thresholds (calibrated on the replay harness, not guessed).
HEAVY_FAV_DEC = 1.50      # <= this decimal price = heavy chalk
MID_FAV_DEC = 1.90        # (HEAVY, this] = mid favourite
INFLATION_MIN = 0.08      # market-implied fav - model fair fav = overpriced chalk
DRAW_EDGE_MIN = 0.03      # model draw% - market draw% = underpriced draw
NON_WIN_FULL = 0.30       # fav non-win prob needed for a Chaos-FULL flag

# DRAW SCORE component weights (renormalized over PRESENT components).
W_PARITY = 0.30
W_LOWSCORING = 0.25
W_MOTIVATION = 0.15
W_MODEL_GAP = 0.25
W_INJURY = 0.05
INJURY_NUDGE_CAP = 0.05   # +/-5% max, cited


@dataclass(frozen=True)
class TeamForm:
    name: str
    gf: float
    ga: float
    gp: int
    strength: Optional[float] = None  # devigged title-outright prob (0-1), optional

    @property
    def gf_per_game(self) -> Optional[float]:
        return self.gf / self.gp if self.gp > 0 else None

    @property
    def ga_per_game(self) -> Optional[float]:
        return self.ga / self.gp if self.gp > 0 else None


@dataclass(frozen=True)
class MatchInput:
    home: TeamForm
    away: TeamForm
    market_home: float            # devigged market probs (0-1), required
    market_draw: float
    market_away: float
    fav_decimal_odds: float       # decimal price of the market favourite
    draw_decimal_odds: Optional[float] = None
    model_home: Optional[float] = None  # Dixon-Coles probs, optional
    model_draw: Optional[float] = None
    model_away: Optional[float] = None
    home_tag: Optional[str] = None      # QUALIFIED/ELIMINATED/MUST_WIN/CAN_DRAW
    away_tag: Optional[str] = None
    injury_draw_nudge: Optional[float] = None  # cited, toward draw (+) / away (-)
    injury_note: Optional[str] = None


def replace_model(
    m: MatchInput,
    model_home: Optional[float],
    model_draw: Optional[float],
    model_away: Optional[float],
) -> MatchInput:
    """Immutable helper: return a copy with model probs replaced."""
    from dataclasses import replace
    return replace(m, model_home=model_home, model_draw=model_draw, model_away=model_away)


def draw_score(m: MatchInput) -> dict:
    """Weighted draw-likelihood score in [0,1], renormalized over present
    components. Each present component appends a cited evidence string."""
    comps: dict[str, tuple[float, float]] = {}  # name -> (weight, value)
    evidence: list[str] = []

    # 1) Parity — small market gap, and title-strength gap when present.
    fav_mkt = max(m.market_home, m.market_away)
    dog_mkt = min(m.market_home, m.market_away)
    parity = 1.0 - (fav_mkt - dog_mkt)
    if m.home.strength is not None and m.away.strength is not None:
        sgap = abs(m.home.strength - m.away.strength)
        strength_parity = max(0.0, 1.0 - sgap / 0.30)
        parity = (parity + strength_parity) / 2.0
        evidence.append(
            f"parity: market fav {fav_mkt:.0%} vs dog {dog_mkt:.0%}, "
            f"title-strength gap {sgap:.0%}"
        )
    else:
        evidence.append(f"parity: market fav {fav_mkt:.0%} vs dog {dog_mkt:.0%}")
    comps["parity"] = (W_PARITY, max(0.0, min(1.0, parity)))

    # 2) Low-scoring profile — low GF/game across both (goals scarce -> draw).
    gpg = [t.gf_per_game for t in (m.home, m.away) if t.gf_per_game is not None]
    if len(gpg) == 2:
        avg_gpg = sum(gpg) / 2.0
        low = max(0.0, min(1.0, (2.5 - avg_gpg) / 1.5))
        comps["low_scoring"] = (W_LOWSCORING, low)
        evidence.append(f"low-scoring: avg {avg_gpg:.2f} GF/game across both")

    # 3) Motivation — CAN_DRAW or QUALIFIED (rotation) on either side.
    tags = {t for t in (m.home_tag, m.away_tag) if t}
    if tags:
        mot = 0.0
        if "CAN_DRAW" in tags:
            mot = max(mot, 1.0)
        if "QUALIFIED" in tags:
            mot = max(mot, 0.6)
        comps["motivation"] = (W_MOTIVATION, mot)
        if mot > 0:
            evidence.append(f"motivation: {'/'.join(sorted(tags))} -> settles for a point")

    # 4) Model-vs-market gap — Dixon-Coles draw% over market draw% = underpriced.
    if m.model_draw is not None:
        gap = m.model_draw - m.market_draw
        g = max(0.0, min(1.0, gap / 0.10))
        comps["model_gap"] = (W_MODEL_GAP, g)
        evidence.append(
            f"model gap: model draw {m.model_draw:.0%} vs market {m.market_draw:.0%} ({gap:+.0%})"
        )

    # 5) Injury/news nudge — cited, capped.
    if m.injury_draw_nudge is not None:
        nudge = max(-INJURY_NUDGE_CAP, min(INJURY_NUDGE_CAP, m.injury_draw_nudge))
        n = 0.5 + nudge / (2 * INJURY_NUDGE_CAP)
        comps["injury"] = (W_INJURY, n)
        if m.injury_note:
            evidence.append(f"injury/news: {m.injury_note} (nudge {nudge:+.0%}, cited)")

    total_w = sum(w for w, _ in comps.values())
    score = (sum(w * v for w, v in comps.values()) / total_w) if total_w > 0 else 0.0
    return {
        "draw_score": round(score, 4),
        "components": {k: round(v, 4) for k, (_, v) in comps.items()},
        "evidence": evidence,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/chaos_engine.py scripts/test_chaos_engine.py
git commit -m "feat: chaos_engine DRAW SCORE with renormalized, cited components"
```

---

### Task 2: `chaos_engine.py` — `assess_match()` grading

**Files:**
- Modify: `scripts/chaos_engine.py`
- Test: `scripts/test_chaos_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# append to scripts/test_chaos_engine.py

def test_mid_fav_underpriced_draw_flags_chaos_lite():
    res = ce.assess_match(_canada_bosnia())
    assert res.grade == "LITE"
    assert res.favourite == "Canada"
    assert res.side == "Draw"


def test_heavy_overpriced_fav_with_live_dog_flags_chaos_full():
    m = ce.MatchInput(
        home=ce.TeamForm(name="BigDog", gf=2, ga=2, gp=1, strength=0.18),
        away=ce.TeamForm(name="Minnow", gf=1, ga=2, gp=1, strength=0.04),
        market_home=0.66, market_draw=0.20, market_away=0.14,
        fav_decimal_odds=1.45,
        model_home=0.54, model_draw=0.24, model_away=0.22,  # market 66% > model 54%
    )
    res = ce.assess_match(m)
    assert res.grade == "FULL"
    assert res.side == "Minnow"


def test_clean_strong_fav_no_chaos():
    m = ce.MatchInput(
        home=ce.TeamForm(name="Germany", gf=7, ga=1, gp=1, strength=0.12),
        away=ce.TeamForm(name="Curacao", gf=1, ga=7, gp=1, strength=0.001),
        market_home=0.93, market_draw=0.05, market_away=0.02,
        fav_decimal_odds=1.04,
        model_home=0.93, model_draw=0.05, model_away=0.02,
    )
    res = ce.assess_match(m)
    assert res.grade == "NONE"


def test_lite_value_check_uses_draw_price():
    res = ce.assess_match(_canada_bosnia())  # model draw 31% > implied 1/3.40=29%
    assert res.value_ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: FAIL with `AttributeError: module 'chaos_engine' has no attribute 'assess_match'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/chaos_engine.py

@dataclass(frozen=True)
class ChaosResult:
    grade: str                 # "NONE" | "LITE" | "FULL"
    draw_score: float
    favourite: str
    underdog: str
    market: Optional[str]      # recommended chaos market label
    side: Optional[str]        # team name or "Draw"
    value_ok: Optional[bool]   # did chaos market clear value gate (price known)
    components: dict
    evidence: list
    upset_level: str           # LOW/ELEVATED/HIGH from sm.upset_risk


def assess_match(m: MatchInput) -> ChaosResult:
    home_fav = m.market_home >= m.market_away
    fav = m.home.name if home_fav else m.away.name
    dog = m.away.name if home_fav else m.home.name

    ds = draw_score(m)
    evidence = list(ds["evidence"])

    up = sm.upset_risk(
        m.market_home, m.market_draw, m.market_away,
        fav_decimal_odds=m.fav_decimal_odds,
    )

    model_fav = None
    if m.model_home is not None and m.model_away is not None:
        model_fav = m.model_home if home_fav else m.model_away
    market_implied_fav = 1.0 / m.fav_decimal_odds if m.fav_decimal_odds > 0 else max(m.market_home, m.market_away)
    inflation = (market_implied_fav - model_fav) if model_fav is not None else None

    grade = "NONE"
    market: Optional[str] = None
    side: Optional[str] = None
    value_ok: Optional[bool] = None

    overpriced = (
        (inflation is not None and inflation >= INFLATION_MIN)
        or up["level"] in ("ELEVATED", "HIGH")
    )
    if m.fav_decimal_odds <= HEAVY_FAV_DEC and overpriced and up["non_win_prob"] >= NON_WIN_FULL:
        grade = "FULL"
        market, side = "Underdog Win / Double Chance X2", dog
        evidence.append(
            f"CHAOS-FULL: heavy fav at {m.fav_decimal_odds:.2f} but non-win "
            f"{up['non_win_prob']:.0%} (upset {up['level']})"
        )
    elif (
        HEAVY_FAV_DEC < m.fav_decimal_odds <= MID_FAV_DEC
        and m.model_draw is not None
        and (m.model_draw - m.market_draw) >= DRAW_EDGE_MIN
    ):
        grade = "LITE"
        market, side = "Draw (X) / Double Chance", "Draw"
        evidence.append(
            f"CHAOS-LITE: mid fav at {m.fav_decimal_odds:.2f}, draw underpriced "
            f"(model {m.model_draw:.0%} > market {m.market_draw:.0%})"
        )

    if grade == "LITE" and m.draw_decimal_odds and m.model_draw is not None:
        implied = 1.0 / m.draw_decimal_odds
        value_ok = m.model_draw > implied
        evidence.append(
            f"value: draw priced {implied:.0%} vs model {m.model_draw:.0%} "
            f"-> {'clears' if value_ok else 'fails'} gate"
        )

    return ChaosResult(
        grade=grade, draw_score=ds["draw_score"], favourite=fav, underdog=dog,
        market=market, side=side, value_ok=value_ok,
        components=ds["components"], evidence=evidence, upset_level=up["level"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/chaos_engine.py scripts/test_chaos_engine.py
git commit -m "feat: graded chaos flag (NONE/LITE/FULL) reusing upset_risk + value gate"
```

---

### Task 3: `chaos_engine.py` — `slate_weather()`

**Files:**
- Modify: `scripts/chaos_engine.py`
- Test: `scripts/test_chaos_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# append to scripts/test_chaos_engine.py

def test_slate_weather_cagey_when_many_draw_leans():
    drawish = _canada_bosnia()
    results = [ce.assess_match(drawish) for _ in range(4)]
    w = ce.slate_weather(results)
    assert w["weather"] == "CAGEY"
    assert w["draw_lean_share"] >= 0.5
    assert w["n_matches"] == 4


def test_slate_weather_normal_on_empty():
    w = ce.slate_weather([])
    assert w["weather"] == "NORMAL"
    assert w["chaos_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: FAIL with `AttributeError: module 'chaos_engine' has no attribute 'slate_weather'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/chaos_engine.py

DRAW_LEAN_MIN = 0.33   # draw_score at/above this = the match "leans draw"


def slate_weather(results: list[ChaosResult]) -> dict:
    """Soft aggregate tilt over a slate. NOT chaos — only a totals modifier."""
    n = len(results)
    if n == 0:
        return {"weather": "NORMAL", "draw_lean_share": 0.0, "chaos_count": 0, "n_matches": 0}
    draw_leans = sum(1 for r in results if r.draw_score >= DRAW_LEAN_MIN)
    chaos = sum(1 for r in results if r.grade != "NONE")
    share = draw_leans / n
    weather = "CAGEY" if share >= 0.50 else "OPEN" if share <= 0.15 else "NORMAL"
    return {
        "weather": weather,
        "draw_lean_share": round(share, 3),
        "chaos_count": chaos,
        "n_matches": n,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_chaos_engine.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/chaos_engine.py scripts/test_chaos_engine.py
git commit -m "feat: slate_weather soft aggregate (CAGEY/OPEN/NORMAL)"
```

---

### Task 4: `staking.py` — `route_tier()`

**Files:**
- Create: `scripts/staking.py`
- Test: `scripts/test_staking.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_staking.py
"""Tests for the staking tier router + sizer. Pure math — no network."""
import staking as st


def test_normal_tier_for_high_winprob():
    assert st.route_tier(0.62, "NONE") == "NORMAL"


def test_mild_tier_for_mid_winprob():
    assert st.route_tier(0.45, "NONE") == "MILD"


def test_chaos_lite_routes_mild_even_if_low_winprob():
    assert st.route_tier(0.30, "LITE") == "MILD"


def test_chaos_full_routes_wild():
    assert st.route_tier(0.30, "FULL") == "WILD"


def test_low_winprob_no_chaos_routes_wild():
    assert st.route_tier(0.25, "NONE") == "WILD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_staking.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'staking'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/staking.py
"""
Staking — Caveman Locks.

Routes value-cleared candidates into Normal / Mild / Wild tiers and sizes them
against a bankroll split (default 70/20/10). Wild picks are hard-capped so
longshots can never drain the bank. Pure functions, immutable outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

NORMAL_MIN = 0.58   # win-prob at/above -> Normal tier
MILD_MIN = 0.40     # win-prob at/above (or Chaos-LITE) -> Mild tier


def route_tier(win_prob: float, chaos_grade: str) -> str:
    """Assign a tier from win probability + chaos grade."""
    if chaos_grade == "FULL":
        return "WILD"
    if win_prob >= NORMAL_MIN:
        return "NORMAL"
    if win_prob >= MILD_MIN or chaos_grade == "LITE":
        return "MILD"
    return "WILD"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_staking.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/staking.py scripts/test_staking.py
git commit -m "feat: staking tier router (Normal/Mild/Wild)"
```

---

### Task 5: `staking.py` — `size_card()` with bankroll caps

**Files:**
- Modify: `scripts/staking.py`
- Test: `scripts/test_staking.py`

- [ ] **Step 1: Write the failing test**

```python
# append to scripts/test_staking.py

def _cand(market, side, wp, grade="NONE", odds=2.0):
    return st.Candidate(market=market, side=side, win_prob=wp,
                        decimal_odds=odds, chaos_grade=grade, evidence="x")


def test_size_card_respects_tier_pools_and_bankroll():
    cands = [
        _cand("Total 2.5", "Under", 0.62),          # NORMAL
        _cand("Double Chance", "1X", 0.45),         # MILD
        _cand("Underdog Win", "Minnow", 0.22, "FULL"),  # WILD
    ]
    cfg = st.TierConfig(bankroll=200.0)
    picks = st.size_card(cands, cfg)
    by_tier = {p.tier: p for p in picks}
    # Normal pool = 70% of 200 = 140 (single pick gets it all)
    assert abs(by_tier["NORMAL"].stake_usd - 140.0) < 0.01
    # Wild pick is capped at 0.25u (1u = 1% of 200 = $2) -> <= $0.50
    assert by_tier["WILD"].stake_usd <= 0.50 + 1e-9


def test_size_card_caps_number_of_wild_picks():
    cfg = st.TierConfig(bankroll=200.0, max_wild=2)
    cands = [_cand(f"dog{i}", f"D{i}", 0.20, "FULL") for i in range(5)]
    picks = st.size_card(cands, cfg)
    assert sum(1 for p in picks if p.tier == "WILD") == 2


def test_size_card_does_not_mutate_input():
    cands = [_cand("Total 2.5", "Under", 0.62)]
    snapshot = cands[0]
    st.size_card(cands, st.TierConfig())
    assert cands[0] is snapshot  # immutability
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_staking.py -q`
Expected: FAIL with `AttributeError: module 'staking' has no attribute 'Candidate'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/staking.py

@dataclass(frozen=True)
class Candidate:
    market: str
    side: str
    win_prob: float
    decimal_odds: Optional[float] = None
    chaos_grade: str = "NONE"   # NONE | LITE | FULL
    evidence: str = ""


@dataclass(frozen=True)
class TierConfig:
    bankroll: float = 200.0
    split_normal: float = 0.70
    split_mild: float = 0.20
    split_wild: float = 0.10
    unit_pct: float = 0.01        # 1 unit = 1% of bankroll
    wild_cap_units: float = 0.25  # each wild pick capped here
    max_wild: int = 3


@dataclass(frozen=True)
class StakedPick:
    candidate: Candidate
    tier: str
    stake_units: float
    stake_usd: float


def size_card(candidates: list[Candidate], config: TierConfig = TierConfig()) -> list[StakedPick]:
    """Route + size every candidate. Returns new StakedPick objects; never
    mutates the input list or candidates."""
    unit = config.bankroll * config.unit_pct
    pools = {
        "NORMAL": config.bankroll * config.split_normal,
        "MILD": config.bankroll * config.split_mild,
        "WILD": config.bankroll * config.split_wild,
    }
    routed: dict[str, list[Candidate]] = {"NORMAL": [], "MILD": [], "WILD": []}
    for c in candidates:
        routed[route_tier(c.win_prob, c.chaos_grade)].append(c)

    # Keep only the strongest Wild picks (highest win prob).
    routed["WILD"] = sorted(routed["WILD"], key=lambda c: c.win_prob, reverse=True)[: config.max_wild]

    picks: list[StakedPick] = []
    for tier in ("NORMAL", "MILD", "WILD"):
        cands = routed[tier]
        if not cands:
            continue
        wsum = sum(c.win_prob for c in cands) or 1.0
        for c in cands:
            usd = pools[tier] * (c.win_prob / wsum)
            units = usd / unit if unit > 0 else 0.0
            if tier == "WILD":
                units = min(units, config.wild_cap_units)
                usd = units * unit
            picks.append(StakedPick(
                candidate=c, tier=tier,
                stake_units=round(units, 3), stake_usd=round(usd, 2),
            ))
    return picks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_staking.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/staking.py scripts/test_staking.py
git commit -m "feat: size_card tier sizing with wild caps + immutability"
```

---

### Task 6: Replay harness + fixtures

**Files:**
- Create: `scripts/fixtures/wc_2026_jun11_15.json`
- Create: `scripts/replay_wc.py`
- Test: `scripts/test_replay_wc.py`

- [ ] **Step 1: Write the fixture (illustrative pre-match inputs, NOT live odds)**

```json
// scripts/fixtures/wc_2026_jun11_15.json
[
  {
    "label": "Canada vs Bosnia (actual 1-1 draw)",
    "home": {"name": "Canada", "gf": 1, "ga": 1, "gp": 1, "strength": 0.02},
    "away": {"name": "Bosnia", "gf": 1, "ga": 1, "gp": 1, "strength": 0.01},
    "market_home": 0.50, "market_draw": 0.27, "market_away": 0.23,
    "fav_decimal_odds": 1.83, "draw_decimal_odds": 3.40,
    "model_home": 0.46, "model_draw": 0.31, "model_away": 0.23,
    "home_tag": "CAN_DRAW", "away_tag": null,
    "actual": "DRAW"
  },
  {
    "label": "Germany vs Curacao (actual 7-1)",
    "home": {"name": "Germany", "gf": 7, "ga": 1, "gp": 1, "strength": 0.12},
    "away": {"name": "Curacao", "gf": 1, "ga": 7, "gp": 1, "strength": 0.001},
    "market_home": 0.93, "market_draw": 0.05, "market_away": 0.02,
    "fav_decimal_odds": 1.04, "draw_decimal_odds": 12.0,
    "model_home": 0.93, "model_draw": 0.05, "model_away": 0.02,
    "home_tag": null, "away_tag": null,
    "actual": "HOME"
  }
]
```

- [ ] **Step 2: Write the failing test**

```python
# scripts/test_replay_wc.py
"""Replay harness test — fixture-driven, no network."""
import replay_wc as rw


def test_replay_flags_canada_draw_as_lite():
    report = rw.run_replay()
    canada = next(r for r in report if "Canada" in r["label"])
    assert canada["grade"] == "LITE"
    assert canada["actual"] == "DRAW"


def test_replay_does_not_flag_germany_blowout():
    report = rw.run_replay()
    germany = next(r for r in report if "Germany" in r["label"])
    assert germany["grade"] == "NONE"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_replay_wc.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'replay_wc'`

- [ ] **Step 4: Write minimal implementation**

```python
# scripts/replay_wc.py
"""
Replay harness — runs the chaos engine over fixed pre-match fixtures and reports
which spots it flagged vs the actual result. Honest by design: it prints the
matches it could NOT flag rather than pretending. No network (fixtures only).
"""
from __future__ import annotations

import json
from pathlib import Path

import chaos_engine as ce

FIXTURE = Path(__file__).parent / "fixtures" / "wc_2026_jun11_15.json"


def _to_match(row: dict) -> ce.MatchInput:
    return ce.MatchInput(
        home=ce.TeamForm(**row["home"]),
        away=ce.TeamForm(**row["away"]),
        market_home=row["market_home"],
        market_draw=row["market_draw"],
        market_away=row["market_away"],
        fav_decimal_odds=row["fav_decimal_odds"],
        draw_decimal_odds=row.get("draw_decimal_odds"),
        model_home=row.get("model_home"),
        model_draw=row.get("model_draw"),
        model_away=row.get("model_away"),
        home_tag=row.get("home_tag"),
        away_tag=row.get("away_tag"),
    )


def run_replay() -> list[dict]:
    rows = json.loads(FIXTURE.read_text())
    report = []
    for row in rows:
        res = ce.assess_match(_to_match(row))
        report.append({
            "label": row["label"],
            "grade": res.grade,
            "draw_score": res.draw_score,
            "actual": row["actual"],
            "side": res.side,
            "evidence": res.evidence,
        })
    return report


def main() -> None:
    for r in run_replay():
        hit = "—"
        if r["grade"] == "LITE" and r["actual"] == "DRAW":
            hit = "✓ draw flagged"
        elif r["grade"] == "NONE" and r["actual"] in ("HOME", "AWAY"):
            hit = "✓ correctly quiet"
        print(f"{r['label']}: {r['grade']} (draw_score {r['draw_score']}) actual={r['actual']} {hit}")
        for e in r["evidence"]:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_replay_wc.py -q`
Expected: PASS (2 tests)

- [ ] **Step 6: Eyeball the harness output**

Run: `cd scripts && python3 replay_wc.py && cd ..`
Expected: Canada line shows `LITE ... ✓ draw flagged`; Germany shows `NONE ... ✓ correctly quiet`.

- [ ] **Step 7: Commit**

```bash
git add scripts/fixtures/wc_2026_jun11_15.json scripts/replay_wc.py scripts/test_replay_wc.py
git commit -m "feat: fixture replay harness (Canada-draw flags LITE, blowout stays quiet)"
```

---

### Task 7: Heuristics — Rule 10 + tiered output format

**Files:**
- Modify: `skills/betting/global_heuristics.md` (append after line 16, the current Rule 9)
- Modify: `skills/betting/soccer_skill.md` (append a new section before the footer line `*Soccer v3.0 ...`)

- [ ] **Step 1: Append Rule 10 to `skills/betting/global_heuristics.md`**

Add exactly this after the existing Rule 9 line:

```markdown
10. **CHAOS PASS + TIERED CARD (deterministic, no hallucination)**: The chaos engine (`scripts/chaos_engine.py`) runs on EVERY match with a favourite and returns a graded flag + DRAW SCORE, each carrying an `evidence[]` trail. Consume those numbers — never invent them.
   - **CHAOS-FULL** = heavy fav (≤1.50) the model says is overpriced + live dog → back the dog / X2 (Wild tier only, tiny stake).
   - **CHAOS-LITE** = mid fav (1.50–1.90) with an underpriced draw (model draw% > market draw%) → the draw (X) / Double Chance (Mild or Wild).
   - A chaos pick is only a PICK when it clears the value gate (Rule 1); otherwise it is a NOTE.
   - **DATA CONTRACT**: every probability cites a real input or the devigged price. Narrative (news/motivation) may nudge ±5% max and MUST name its source. Missing data → "unavailable", widen uncertainty, never fill with a guess.
   - **TIERED OUTPUT**: render the card in three sections sized by `scripts/staking.py` (70% Normal / 20% Mild / 10% Wild of bankroll). Each pick: market + price + one-line evidence + stake (units & $). Empty tier prints "PASS — no value today." `slate_weather` (CAGEY/OPEN/NORMAL) is a soft totals modifier only — NOT chaos.
```

- [ ] **Step 2: Append the CHAOS section to `skills/betting/soccer_skill.md`**

Add this block immediately before the final `*Soccer v3.0 — Caveman Locks. World Cup 2026.*` line:

```markdown
## CHAOS DETECTOR + DRAW SCORE (deterministic — chaos_engine.py)
Runs on every WC match with a favourite. The DRAW SCORE (0-1) is built only from
real data, renormalized over whatever is present (never invented):
- **Parity** — small gap in the devigged 1X2 + title-strength prior.
- **Low-scoring** — both teams low GF/game (goals scarce → draw/under).
- **Motivation** — CAN_DRAW / QUALIFIED (rotation) advancement tag.
- **Model gap** — Dixon-Coles draw% > market devigged draw% = underpriced draw.
- **Injury/news nudge** — key attacker out → +draw/under, ±5% cap, cited; skipped when no data.

CHAOS grades: **LITE** (mid fav 1.50–1.90, underpriced draw → X / Double Chance),
**FULL** (heavy fav ≤1.50 overpriced + live dog → dog / X2, Wild tier only).
The draw is a PICK only when model draw% > market draw% AND the draw price clears
the value gate — else it's a note. This is the Canada-draw fix, grounded in stats.
Lineups/injuries: use ESPN injuries + news when present (cited soft nudge); no
predicted-XI feed exists, so never fabricate one. Club-vs-country form is not
modelled (no clean data) — soft cited nudge only.
```

- [ ] **Step 3: Verify the files still load (no syntax/markdown breakage)**

Run: `python3 -c "import pathlib; [print(p, pathlib.Path(p).stat().st_size) for p in ['skills/betting/global_heuristics.md','skills/betting/soccer_skill.md']]"`
Expected: both paths print with a larger byte size than before (non-zero, no exception).

- [ ] **Step 4: Commit**

```bash
git add skills/betting/global_heuristics.md skills/betting/soccer_skill.md
git commit -m "feat: heuristics rule 10 — chaos pass + DRAW SCORE + tiered card contract"
```

---

### Task 8: Expose pipeline via `POST /chaos-slate`

**Files:**
- Modify: `scripts/edge_api.py` (add endpoint near the other soccer endpoints, after `/predict-soccer` ends at line 428)

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_chaos_api.py
"""Endpoint test for /chaos-slate — uses FastAPI TestClient, no external network."""
from fastapi.testclient import TestClient
import edge_api


def test_chaos_slate_returns_tiered_card_and_weather():
    client = TestClient(edge_api.app)
    payload = {
        "bankroll": 200.0,
        "matches": [
            {
                "home": {"name": "Canada", "gf": 1, "ga": 1, "gp": 1, "strength": 0.02},
                "away": {"name": "Bosnia", "gf": 1, "ga": 1, "gp": 1, "strength": 0.01},
                "market_home": 0.50, "market_draw": 0.27, "market_away": 0.23,
                "fav_decimal_odds": 1.83, "draw_decimal_odds": 3.40,
                "model_home": 0.46, "model_draw": 0.31, "model_away": 0.23,
                "home_tag": "CAN_DRAW", "win_prob": 0.58, "decimal_odds": 3.40,
                "market": "Draw (X)", "side": "Draw"
            }
        ]
    }
    r = client.post("/chaos-slate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["weather"]["n_matches"] == 1
    assert body["chaos"][0]["grade"] == "LITE"
    assert "card" in body and len(body["card"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/test_chaos_api.py -q`
Expected: FAIL with 404 (endpoint not found) or assertion error.

- [ ] **Step 3: Write minimal implementation**

```python
# add near the top imports of scripts/edge_api.py (after `import ufc_markets as um`):
import chaos_engine as ce
import staking as stk
from typing import List

# add after the /predict-soccer function (after line 428):

class ChaosTeam(BaseModel):
    name: str
    gf: float
    ga: float
    gp: int
    strength: Optional[float] = None


class ChaosMatch(BaseModel):
    home: ChaosTeam
    away: ChaosTeam
    market_home: float
    market_draw: float
    market_away: float
    fav_decimal_odds: float
    draw_decimal_odds: Optional[float] = None
    model_home: Optional[float] = None
    model_draw: Optional[float] = None
    model_away: Optional[float] = None
    home_tag: Optional[str] = None
    away_tag: Optional[str] = None
    injury_draw_nudge: Optional[float] = None
    injury_note: Optional[str] = None
    # candidate fields for staking (the pick the LLM/engine wants to size)
    win_prob: Optional[float] = None
    decimal_odds: Optional[float] = None
    market: Optional[str] = None
    side: Optional[str] = None


class ChaosSlateReq(BaseModel):
    matches: List[ChaosMatch]
    bankroll: float = 200.0


@app.post("/chaos-slate")
def chaos_slate(req: ChaosSlateReq):
    results = []
    candidates = []
    for mm in req.matches:
        match = ce.MatchInput(
            home=ce.TeamForm(**mm.home.dict()),
            away=ce.TeamForm(**mm.away.dict()),
            market_home=mm.market_home, market_draw=mm.market_draw,
            market_away=mm.market_away, fav_decimal_odds=mm.fav_decimal_odds,
            draw_decimal_odds=mm.draw_decimal_odds,
            model_home=mm.model_home, model_draw=mm.model_draw, model_away=mm.model_away,
            home_tag=mm.home_tag, away_tag=mm.away_tag,
            injury_draw_nudge=mm.injury_draw_nudge, injury_note=mm.injury_note,
        )
        res = ce.assess_match(match)
        results.append(res)
        if mm.win_prob is not None and mm.market and mm.side:
            candidates.append(stk.Candidate(
                market=mm.market, side=mm.side, win_prob=mm.win_prob,
                decimal_odds=mm.decimal_odds, chaos_grade=res.grade,
                evidence="; ".join(res.evidence),
            ))

    weather = ce.slate_weather(results)
    card = stk.size_card(candidates, stk.TierConfig(bankroll=req.bankroll))
    return {
        "status": "OK",
        "weather": weather,
        "chaos": [
            {"favourite": r.favourite, "underdog": r.underdog, "grade": r.grade,
             "draw_score": r.draw_score, "side": r.side, "market": r.market,
             "value_ok": r.value_ok, "upset_level": r.upset_level,
             "evidence": r.evidence}
            for r in results
        ],
        "card": [
            {"tier": p.tier, "market": p.candidate.market, "side": p.candidate.side,
             "win_prob": p.candidate.win_prob, "stake_units": p.stake_units,
             "stake_usd": p.stake_usd, "evidence": p.candidate.evidence}
            for p in card
        ],
    }
```

Note: `.dict()` is Pydantic v1 style; if the project uses Pydantic v2, use `.model_dump()`. Check the existing `BaseModel` usage in `scripts/math_engine.py` / `edge_api.py` and match it. (`edge_api.py` already uses `BaseModel` with plain attribute access — confirm version with `python3 -c "import pydantic; print(pydantic.VERSION)"` and pick `.dict()` (v1) or `.model_dump()` (v2).)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/test_chaos_api.py -q`
Expected: PASS (1 test). If `fastapi.testclient` needs `httpx`, install into system python: `python3 -m pip install httpx` (test-only).

- [ ] **Step 5: Commit**

```bash
git add scripts/edge_api.py scripts/test_chaos_api.py
git commit -m "feat: /chaos-slate endpoint — chaos grades + slate weather + tiered card"
```

---

### Task 9: Full suite + spec sign-off

**Files:** none (verification only)

- [ ] **Step 1: Run the whole new suite**

Run: `python3 -m pytest scripts/test_chaos_engine.py scripts/test_staking.py scripts/test_replay_wc.py scripts/test_chaos_api.py -v`
Expected: all green.

- [ ] **Step 2: Confirm no regression in existing soccer tests**

Run: `python3 -m pytest scripts/test_soccer_markets.py -q`
Expected: still green (chaos engine only imports, never modifies, `soccer_markets`).

- [ ] **Step 3: Commit any fixups, then update the spec status**

Edit `docs/superpowers/specs/2026-06-16-chaos-engine-tiered-card-design.md`: change `Status: Approved shape, pending spec review` to `Status: Implemented`.

```bash
git add docs/superpowers/specs/2026-06-16-chaos-engine-tiered-card-design.md
git commit -m "docs: mark chaos engine spec implemented"
```

---

## Self-Review

**Spec coverage:**
- §5.1 chaos_engine (chaos flags + DRAW SCORE) → Tasks 1-2 ✓
- §5.2 slate_weather → Task 3 ✓
- §5.3 staking (routing + caps + immutability) → Tasks 4-5 ✓
- §5.4 heuristics update → Task 7 ✓
- §5.5 tiered card output → Task 7 (format) + Task 8 (data) ✓
- §4 no-hallucination data contract → enforced in `draw_score` renormalization (Task 1) + Rule 10 (Task 7) ✓
- §7 replay harness (fixtures, no API) + unit tests + immutability → Tasks 6, 5 ✓
- §8 inflation threshold tuning → constants exposed in `chaos_engine.py` (Task 1), exercised by replay (Task 6) ✓

**Placeholder scan:** none — every step has runnable code/commands. The one conditional (`.dict()` vs `.model_dump()`) is resolved by an explicit version check in Task 8 Step 3.

**Type consistency:** `MatchInput`/`TeamForm`/`ChaosResult` fields used in Tasks 2/3/6/8 match Task 1 definitions. `Candidate`/`TierConfig`/`StakedPick` used in Task 8 match Task 5. `route_tier`/`size_card` signatures consistent across Tasks 4/5/8. `assess_match` return type (`ChaosResult`) consistent in Tasks 2/3/6/8.
