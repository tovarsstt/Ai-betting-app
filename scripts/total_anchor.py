"""
total_anchor.py — rule: when the market gives a game total, the MARKET sets the total, the model only sets the split.

Why (measured, not assumed):
  * soccer: the Elo goal model under-predicted Champions League totals by 0.54 goals/match (1.0 in mismatches);
  * NFL: data/benchmarks/nfl_backtest.json — best ratings weight for TOTALS = 0.0, and when the model disagreed with
    the total by 3+ points it hit only 48.9% (n=659): the market total beats ratings totals.
So every goal/score-rate tool is rescaled to the market total before any probability is derived. Without a market
total the tool keeps its own (bias-corrected) total and the report says "total NOT anchored".
"""
from __future__ import annotations


def anchor_rates(lh: float, la: float, market_total: float | None, floor: float = 0.15) -> tuple[float, float]:
    """Rescale (λh, λa) so λh+λa == market_total, keeping the model's home share. No-op if total is None/invalid."""
    if not market_total or market_total <= 0 or lh + la <= 0:
        return lh, la
    k = market_total / (lh + la)
    return max(floor, lh * k), max(floor, la * k)
