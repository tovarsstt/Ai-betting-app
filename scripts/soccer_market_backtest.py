#!/usr/bin/env python3
"""
soccer_market_backtest.py — does the model beat the MARKET, not just the results?

soccer_backtest.py measures skill against outcomes and says so explicitly:
"no odds involved". That answers "is the model better than guessing", which is
not the question a bettor has. Beating a naive baseline earns nothing; the only
thing that pays is being right where the CLOSING PRICE was wrong, by more than
the vig.

This runs the same walk-forward discipline (monthly refits, `as_of` so the
fitter cannot see the future) but settles every game against the real closing
odds in match_stats.csv, and reports flat-stake ROI.

It also devigs the closing line to get the market's own probability, so we can
say whether the model is adding information or just re-deriving the price.

Honest by construction: no bet sizing, no compounding, no best-of-N book
shopping. Flat 1 unit at the CLOSING price, which is the hardest price to beat
and the one that makes the result meaningful rather than flattering.

Run: python3 scripts/soccer_market_backtest.py [--from 2025-11-01] [--edge 0.05]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fit_club_ratings as fcr
import soccer_markets as sm
from poisson_model import score_matrix, win_draw_loss

DATA = Path(__file__).parent.parent / "data" / "soccer"
STATS = DATA / "match_stats.csv"
OUT = DATA / "market_backtest.json"
DEFAULT_FROM = "2025-11-01"


PRICE_SETS = {"open": ("open_home", "open_draw", "open_away"),
              "close": ("close_home", "close_draw", "close_away"),
              "best": ("best_home", "best_draw", "best_away")}


def load(price: str = "close") -> list[dict]:
    with STATS.open() as f:
        rows = [r for r in csv.DictReader(f)
                if r.get("home_goals") not in (None, "") and r.get("date")]
    cols = PRICE_SETS[price]
    out = []
    for r in rows:
        try:
            o = (float(r[cols[0]]), float(r[cols[1]]), float(r[cols[2]]))
        except (TypeError, ValueError, KeyError):
            continue
        if min(o) <= 1.0:
            continue
        out.append({**r, "odds": o})
    return out


def devig(odds: tuple) -> tuple:
    """Market's implied probabilities with the overround divided out."""
    raw = [1.0 / o for o in odds]
    s = sum(raw)
    return tuple(p / s for p in raw)


def model_probs(league: dict, home: str, away: str):
    th, ta = league["teams"].get(home), league["teams"].get(away)
    if not th or not ta or th.get("attack") is None or ta.get("attack") is None:
        return None
    lh = math.exp(league["mu"] + league["home_advantage"] + th["attack"] - ta["defense"])
    la = math.exp(league["mu"] + ta["attack"] - th["defense"])
    return win_draw_loss(score_matrix(lh, la, rho=sm.DEFAULT_RHO))


def run(start_from: str = DEFAULT_FROM, edge_min: float = 0.05,
        price: str = "close") -> dict:
    games = load(price)
    months = sorted({g["date"][:7] for g in games if g["date"] >= start_from})

    bets: list[dict] = []
    matched = 0
    unmatched: set = set()
    market_brier = model_brier = 0.0
    n_scored = 0

    for m in months:
        ratings = fcr.build(as_of=date.fromisoformat(m + "-01"))["leagues"]
        for g in games:
            if g["date"][:7] != m or g["date"] < start_from:
                continue
            league = ratings.get(g["league"])
            if not league:
                continue
            p = model_probs(league, g["home_team"], g["away_team"])
            if p is None:
                unmatched.add(g["home_team"])
                continue
            matched += 1
            hs, as_ = int(g["home_goals"]), int(g["away_goals"])
            outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
            mk = devig(g["odds"])

            # Is the model adding information, or re-deriving the price?
            for i in range(3):
                model_brier += (p[i] - (outcome == i)) ** 2
                market_brier += (mk[i] - (outcome == i)) ** 2
            n_scored += 1

            # Flat 1u on every selection whose model edge clears the threshold.
            for i in range(3):
                edge = p[i] - mk[i]
                if edge < edge_min:
                    continue
                price = g["odds"][i]
                bets.append({
                    "date": g["date"], "league": g["league"],
                    "pick": ("H", "D", "A")[i], "price": price,
                    "model_p": p[i], "market_p": mk[i], "edge": edge,
                    "won": outcome == i,
                    "pnl": (price - 1.0) if outcome == i else -1.0,
                })

    if not bets:
        return {"error": "NO_BETS", "matched_games": matched,
                "note": f"no selection cleared a {edge_min:.0%} edge"}

    pnl = sum(b["pnl"] for b in bets)
    wins = sum(1 for b in bets if b["won"])
    exp_wins = sum(b["model_p"] for b in bets)

    by_league: dict = {}
    for b in bets:
        L = by_league.setdefault(b["league"], {"n": 0, "pnl": 0.0, "w": 0})
        L["n"] += 1
        L["pnl"] += b["pnl"]
        L["w"] += b["won"]

    return {
        "window_from": start_from,
        "price_used": price,
        "edge_threshold": edge_min,
        "games_priced": matched,
        "bets": len(bets),
        "wins": wins,
        "hit_rate": round(wins / len(bets), 4),
        "roi": round(pnl / len(bets), 4),
        "profit_units": round(pnl, 2),
        "avg_price": round(statistics.fmean([b["price"] for b in bets]), 3),
        "calibration": {
            "model_expected_wins": round(exp_wins, 1),
            "actual_wins": wins,
            "note": "model claimed this many winners; reality delivered the other. "
                    "A big gap means the edge was imaginary, not just unlucky.",
        },
        "vs_market": {
            "model_brier": round(model_brier / n_scored, 4) if n_scored else None,
            "market_brier": round(market_brier / n_scored, 4) if n_scored else None,
            "note": "lower is better. If the market's is lower, the model is NOT "
                    "adding information over the closing price, whatever the ROI says.",
        },
        "by_league": {k: {"n": v["n"], "roi": round(v["pnl"] / v["n"], 4),
                          "hit_rate": round(v["w"] / v["n"], 4)}
                      for k, v in sorted(by_league.items())},
        "unmatched_teams": sorted(unmatched)[:15],
        "method": ["walk-forward monthly refits; fitter blind to future games",
                   "flat 1u at the CLOSING price — no book shopping, no staking",
                   "closing line is the hardest price to beat; that is the point"],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_FROM)
    ap.add_argument("--edge", type=float, default=0.05)
    ap.add_argument("--price", choices=sorted(PRICE_SETS), default="close")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    res = run(a.start, a.edge, a.price)
    print(json.dumps(res, indent=1))
    if a.save and "error" not in res:
        OUT.write_text(json.dumps(res, indent=1))
        print(f"\nwrote {OUT}")
