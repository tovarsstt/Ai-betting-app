#!/usr/bin/env python3
"""
soccer_backtest.py — walk-forward validation of the club Poisson model on the
season's real results, the same honesty pass the MLB engine got.

Method: for each month of the 2025-26 club season (after a 3-month burn-in),
refit the per-league Poisson ratings AS OF the month start (fit_club_ratings
already excludes future games — verified: _parse_rows drops d > as_of), then
price every game inside that month with the Dixon-Coles score matrix and grade
the 1X2 read against the real result.

Metrics per league + overall:
  accuracy — argmax(1X2) hit rate, vs the always-home baseline
  rps      — ranked probability score (standard 1X2 skill metric; lower = better;
             0.667-uniform is the no-skill anchor at ~0.22-0.25 in practice)
  brier_home — calibration on the home-win binary

CLI:  python3 scripts/soccer_backtest.py [--from 2025-11-01]
Pure local compute over data/soccer/club_results.csv — no network.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fit_club_ratings as fcr
import soccer_markets as sm
from poisson_model import score_matrix, win_draw_loss

CSV = Path(__file__).parent.parent / "data" / "soccer" / "club_results.csv"
DEFAULT_FROM = "2025-11-01"     # burn-in: ~3 months of results before grading


def load_games() -> list[dict]:
    with CSV.open() as f:
        return [r for r in csv.DictReader(f)
                if r.get("home_score") not in (None, "",) and r.get("date")]


def month_starts(games: list[dict], start_from: str) -> list[str]:
    months = sorted({g["date"][:7] for g in games if g["date"] >= start_from})
    return [m + "-01" for m in months]


def game_probs(league: dict, home: str, away: str) -> tuple | None:
    th, ta = league["teams"].get(home), league["teams"].get(away)
    if not th or not ta or th.get("attack") is None or ta.get("attack") is None:
        return None
    import math
    lh = math.exp(league["mu"] + league["home_advantage"] + th["attack"] - ta["defense"])
    la = math.exp(league["mu"] + ta["attack"] - th["defense"])
    return win_draw_loss(score_matrix(lh, la, rho=sm.DEFAULT_RHO))


def rps(probs: tuple, outcome_idx: int) -> float:
    """Ranked probability score over ordered outcomes (home, draw, away)."""
    cum_p = 0.0
    cum_o = 0.0
    total = 0.0
    for i, p in enumerate(probs):
        cum_p += p
        cum_o += 1.0 if i == outcome_idx else 0.0
        total += (cum_p - cum_o) ** 2
    return total / (len(probs) - 1)


def backtest(start_from: str = DEFAULT_FROM) -> dict:
    games = load_games()
    per_league: dict[str, dict] = {}
    overall = {"n": 0, "hits": 0, "home_hits": 0, "rps": 0.0, "brier_home": 0.0}

    for mstart in month_starts(games, start_from):
        as_of = date.fromisoformat(mstart)
        ratings = fcr.build(as_of=as_of)["leagues"]
        month = mstart[:7]
        for g in games:
            if g["date"][:7] != month or g["date"] < start_from:
                continue
            league = ratings.get(g["league"])
            if not league:
                continue
            probs = game_probs(league, g["home_team"], g["away_team"])
            if probs is None:
                continue
            hs, as_ = int(g["home_score"]), int(g["away_score"])
            outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
            pick = max(range(3), key=lambda i: probs[i])
            L = per_league.setdefault(g["league"], {"n": 0, "hits": 0, "rps": 0.0})
            for acc in (L, overall):
                acc["n"] += 1
                acc["hits"] += pick == outcome
                acc["rps"] += rps(probs, outcome)
            overall["home_hits"] += outcome == 0
            overall["brier_home"] += (probs[0] - (outcome == 0)) ** 2

    if overall["n"] == 0:
        return {"error": "NO_GAMES", "note": f"nothing after {start_from}"}
    out = {
        "window_from": start_from, "n_games": overall["n"],
        "accuracy": round(overall["hits"] / overall["n"], 4),
        "always_home_baseline": round(overall["home_hits"] / overall["n"], 4),
        "rps": round(overall["rps"] / overall["n"], 4),
        "brier_home": round(overall["brier_home"] / overall["n"], 4),
        "per_league": {
            lg: {"n": v["n"], "accuracy": round(v["hits"] / v["n"], 4),
                 "rps": round(v["rps"] / v["n"], 4)}
            for lg, v in sorted(per_league.items())
        },
        "notes": ["walk-forward: monthly refits, future games excluded by fitter",
                  "no odds involved — model skill vs results, not vs market"],
    }
    return out


if __name__ == "__main__":
    frm = DEFAULT_FROM
    if "--from" in sys.argv:
        frm = sys.argv[sys.argv.index("--from") + 1]
    print(json.dumps(backtest(frm), indent=1))
