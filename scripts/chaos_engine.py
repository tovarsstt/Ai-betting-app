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

from dataclasses import dataclass, replace as _dc_replace
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

DRAW_LEAN_MIN = 0.33      # draw_score at/above this = the match "leans draw"


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
    return _dc_replace(m, model_home=model_home, model_draw=model_draw, model_away=model_away)


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
    market_implied_fav = (
        1.0 / m.fav_decimal_odds if m.fav_decimal_odds > 0
        else max(m.market_home, m.market_away)
    )
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
