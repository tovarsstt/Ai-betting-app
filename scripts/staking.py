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

# Same per-bet ceiling bank_builder uses: never more than 3% of bank on one bet,
# and quarter-Kelly when the price is known. The tier pools are CEILINGS for the
# whole tier, not amounts to spend — splitting the full 70% pool across one pick
# put $140 of a $200 bank on a single 62% bet (~3x full Kelly).
MAX_PICK_PCT = 0.03
KELLY_FRACTION = 0.25


def _pick_cap_usd(c: "Candidate", bankroll: float) -> float:
    cap = bankroll * MAX_PICK_PCT
    if c.decimal_odds and c.decimal_odds > 1.0:
        b = c.decimal_odds - 1.0
        full_kelly = (b * c.win_prob - (1.0 - c.win_prob)) / b
        cap = min(cap, max(0.0, full_kelly) * KELLY_FRACTION * bankroll)
    return cap


def route_tier(win_prob: float, chaos_grade: str) -> str:
    """Assign a tier from win probability + chaos grade."""
    if chaos_grade == "FULL":
        return "WILD"
    if win_prob >= NORMAL_MIN:
        return "NORMAL"
    if win_prob >= MILD_MIN or chaos_grade == "LITE":
        return "MILD"
    return "WILD"


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
            usd = min(pools[tier] * (c.win_prob / wsum), _pick_cap_usd(c, config.bankroll))
            units = usd / unit if unit > 0 else 0.0
            if tier == "WILD":
                units = min(units, config.wild_cap_units)
                usd = units * unit
            picks.append(StakedPick(
                candidate=c, tier=tier,
                stake_units=round(units, 3), stake_usd=round(usd, 2),
            ))
    return picks
