#!/usr/bin/env python3
"""
tennis_market_backtest.py — does the tennis model beat the PRICE?

tennis_pit_backtest.py measures calibration against results, point-in-time. Good
— but "better than a coin flip" is not "profitable". This settles the same
point-in-time predictions against real Pinnacle prices and reports ROI, plus the
market's own Brier score so we can see whether the model adds information or is
just re-deriving the line more noisily.

Point-in-time throughout: ranks are the ones that existed the week the match was
played, so this cannot repeat the lookahead that invalidated the first attempt.

Run: python3 scripts/tennis_market_backtest.py --tour atp --year 2026
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_tennis_rank_history import load_history, ranking_as_of  # noqa: E402
from tennis_pit_backtest import _prob, _resolve                    # noqa: E402
from tennis_totals_backtest import load_matches                    # noqa: E402

PRICES = {"pinnacle": ("odds_w", "odds_l"), "best": ("max_w", "max_l"),
          "avg": ("avg_w", "avg_l")}


def devig(ow: float, ol: float) -> tuple[float, float]:
    a, b = 1.0 / ow, 1.0 / ol
    s = a + b
    return a / s, b / s


def run(tour: str = "atp", year: int = 2026, best_of: int = 3,
        edge_min: float = 0.05, price: str = "pinnacle") -> dict:
    hist = load_history()
    wcol, lcol = PRICES[price]
    matches = [m for m in load_matches(tour, year)
               if m["best_of"] == best_of and m.get("date")
               and m.get(wcol) and m.get(lcol)]

    model_b = market_b = 0.0
    n = 0
    bets: list[dict] = []
    for m in matches:
        snap = ranking_as_of(tour, m["date"], hist)
        if not snap:
            continue
        a, b = sorted((m["winner"], m["loser"]))
        ra, rb = _resolve(a, snap["players"]), _resolve(b, snap["players"])
        if not ra or not rb:
            continue
        p_a = _prob(ra, rb)                      # model P(a wins)
        won_a = 1 if a == m["winner"] else 0
        # Prices are stored winner/loser; map them onto a/b.
        o_a, o_b = ((m[wcol], m[lcol]) if a == m["winner"] else (m[lcol], m[wcol]))
        mk_a, mk_b = devig(o_a, o_b)

        model_b += (p_a - won_a) ** 2
        market_b += (mk_a - won_a) ** 2
        n += 1

        for side, p_m, p_mk, price_dec, won in (
                ("a", p_a, mk_a, o_a, won_a), ("b", 1 - p_a, mk_b, o_b, 1 - won_a)):
            if p_m - p_mk < edge_min:
                continue
            bets.append({"p": p_m, "mk": p_mk, "price": price_dec, "won": bool(won),
                         "pnl": (price_dec - 1.0) if won else -1.0})

    if n < 50:
        return {"error": "TOO_FEW", "n": n}
    out = {
        "tour": tour, "year": year, "best_of": best_of, "price_used": price,
        "matches_scored": n,
        "vs_market": {
            "model_brier": round(model_b / n, 4),
            "market_brier": round(market_b / n, 4),
            "note": "lower is better; the market's is the number to beat",
        },
        "point_in_time": True,
    }
    if bets:
        pnl = sum(b["pnl"] for b in bets)
        w = sum(1 for b in bets if b["won"])
        exp = sum(b["p"] for b in bets)
        roi = pnl / len(bets)
        h = w / len(bets)
        avg = statistics.fmean(b["price"] for b in bets)
        var = h * (avg - 1 - roi) ** 2 + (1 - h) * (-1 - roi) ** 2
        se = math.sqrt(var / len(bets))
        out["betting"] = {
            "edge_threshold": edge_min, "bets": len(bets), "wins": w,
            "hit_rate": round(h, 4), "roi": round(roi, 4),
            "profit_units": round(pnl, 2), "avg_price": round(avg, 3),
            "model_expected_wins": round(exp, 1),
            "t_stat": round(roi / se, 2) if se else None,
            "significant": bool(se and abs(roi / se) > 2),
        }
    else:
        out["betting"] = {"bets": 0, "note": f"nothing cleared a {edge_min:.0%} edge"}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--best-of", type=int, default=3)
    ap.add_argument("--edge", type=float, default=0.05)
    ap.add_argument("--price", choices=sorted(PRICES), default="pinnacle")
    a = ap.parse_args()
    print(json.dumps(run(a.tour, a.year, a.best_of, a.edge, a.price), indent=1))
