#!/usr/bin/env python3
"""
market_anchor.py — stop replacing the price, start adjusting it.

Rule 30 measured the models losing to the market at every price and every edge
threshold, with the market better calibrated in all three tests. The Brier
numbers say precisely what is wrong: the model is not adding information, it is
re-deriving the line more noisily. So a model used as a REPLACEMENT for the
price is a losing bet by construction.

The fix this points to is to anchor on the market and let the model move it:

    p_final = w * p_model + (1 - w) * p_market

`w` is not chosen by taste. It is FITTED out-of-sample, and the honest outcome
is that it may come back at or near zero — which is the finding that the model
adds nothing, not a failure of the method. Anything else would be fitting the
answer we want.

Two guards against fooling ourselves:
  * WALK-FORWARD. `w` is fitted on earlier matches and scored on later ones
    only. Fitting and scoring on the same games would always show improvement.
  * The benchmark is the MARKET's Brier, not the model's. Beating the model we
    already know is bad is not an achievement.

Run: python3 scripts/market_anchor.py --sport tennis --tour atp
     python3 scripts/market_anchor.py --sport soccer
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "market_anchor.json"
WEIGHTS = [i / 20 for i in range(21)]          # 0.00 .. 1.00


def brier(pairs: list[tuple[float, int]]) -> float:
    return statistics.fmean((p - o) ** 2 for p, o in pairs)


def blend(pm: float, pk: float, w: float) -> float:
    return max(1e-6, min(1 - 1e-6, w * pm + (1 - w) * pk))


def _samples_tennis(tour: str, year: int) -> list[dict]:
    from fetch_tennis_rank_history import load_history, ranking_as_of
    from tennis_market_backtest import devig
    from tennis_pit_backtest import _prob, _resolve
    from tennis_totals_backtest import load_matches

    hist = load_history()
    out = []
    for m in load_matches(tour, year):
        if m["best_of"] != 3 or not m.get("date") or not m.get("avg_w"):
            continue
        snap = ranking_as_of(tour, m["date"], hist)
        if not snap:
            continue
        a, b = sorted((m["winner"], m["loser"]))
        ra, rb = _resolve(a, snap["players"]), _resolve(b, snap["players"])
        if not ra or not rb:
            continue
        o_a, o_b = ((m["avg_w"], m["avg_l"]) if a == m["winner"]
                    else (m["avg_l"], m["avg_w"]))
        mk_a, _ = devig(o_a, o_b)
        out.append({"date": m["date"], "model": _prob(ra, rb), "market": mk_a,
                    "won": 1 if a == m["winner"] else 0, "price": o_a})
    out.sort(key=lambda r: r["date"])
    return out


def _samples_soccer(start_from: str) -> list[dict]:
    import fit_club_ratings as fcr
    from soccer_market_backtest import devig, load, model_probs

    games = load("close")
    months = sorted({g["date"][:7] for g in games if g["date"] >= start_from})
    out = []
    for mo in months:
        ratings = fcr.build(as_of=date.fromisoformat(mo + "-01"))["leagues"]
        for g in games:
            if g["date"][:7] != mo or g["date"] < start_from:
                continue
            lg = ratings.get(g["league"])
            if not lg:
                continue
            p = model_probs(lg, g["home_team"], g["away_team"])
            if p is None:
                continue
            mk = devig(g["odds"])
            hs, as_ = int(g["home_goals"]), int(g["away_goals"])
            outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
            # One row per selection so the 3-way is scored like the 2-way.
            for i in range(3):
                out.append({"date": g["date"], "model": p[i], "market": mk[i],
                            "won": 1 if outcome == i else 0, "price": g["odds"][i]})
    out.sort(key=lambda r: r["date"])
    return out


def run(sport: str, tour: str = "atp", year: int = 2026,
        start_from: str = "2025-11-01", split: float = 0.5) -> dict:
    rows = (_samples_tennis(tour, year) if sport == "tennis"
            else _samples_soccer(start_from))
    if len(rows) < 200:
        return {"error": "TOO_FEW", "n": len(rows)}

    cut = int(len(rows) * split)
    train, test = rows[:cut], rows[cut:]

    # Fit w on the EARLIER half only.
    scored = [(w, brier([(blend(r["model"], r["market"], w), r["won"]) for r in train]))
              for w in WEIGHTS]
    best_w = min(scored, key=lambda t: t[1])[0]

    def b(rs, w):
        return brier([(blend(r["model"], r["market"], w), r["won"]) for r in rs])

    test_market = b(test, 0.0)
    test_model = b(test, 1.0)
    test_blend = b(test, best_w)

    # Does the anchored probability actually find bets the market misprices?
    bets = [r for r in test
            if blend(r["model"], r["market"], best_w) - r["market"] >= 0.03]
    roi = None
    if bets:
        pnl = sum((r["price"] - 1) if r["won"] else -1 for r in bets)
        roi = pnl / len(bets)

    return {
        "sport": sport, "tour": tour if sport == "tennis" else None,
        "n_total": len(rows), "n_train": len(train), "n_test": len(test),
        "fitted_weight_on_model": best_w,
        "out_of_sample_brier": {
            "market_only": round(test_market, 5),
            "model_only": round(test_model, 5),
            "anchored_blend": round(test_blend, 5),
        },
        "improvement_over_market": round(test_market - test_blend, 5),
        "beats_market": bool(test_blend < test_market),
        "betting_on_blend": ({"bets": len(bets), "roi": round(roi, 4),
                              "note": "3% blended edge threshold, flat 1u"}
                             if bets else {"bets": 0}),
        "verdict": (
            f"model carries information: {best_w:.0%} weight improves on the "
            f"price out-of-sample" if test_blend < test_market - 1e-6 and best_w > 0
            else "model adds NOTHING over the market — fitted weight collapses "
                 "to the price, which is the honest result"),
        "method": ["walk-forward: weight fitted on the earlier half, scored on "
                   "the later half only",
                   "benchmark is the MARKET's Brier, not the model's"],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", choices=("tennis", "soccer"), default="tennis")
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--from", dest="start", default="2025-11-01")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    res = run(a.sport, a.tour, a.year, a.start)
    print(json.dumps(res, indent=1))
