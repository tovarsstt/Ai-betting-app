#!/usr/bin/env python3
"""
tennis_winprob_backtest.py — is the tennis MATCH probability calibrated?

The base number everything else rides on. `expected_total_games` calibrates its
level to it, the market ladder derives every handicap and set market from it,
and every EV in the app is computed against it. If it is off, everything is off.

Suspicion that motivated this (2026-08-19): on a live Cincinnati board, ALL SIX
favourites priced BELOW the market's implied probability — Sabalenka 87% vs 90%,
Fritz 83.9% vs 91.7%. Six independent "edges" all pointing the same way is not
six findings, it is one bias. This measures whether the model systematically
under-rates favourites.

LEAKAGE GUARD — the reason this file is careful: tennis-data.co.uk stores rows as
Winner/Loser. Asking the model about "the winner" every time makes the actual
result 100% by construction and the calibration meaningless. Players are ordered
DETERMINISTICALLY (alphabetically) before prediction, so the model never learns
which side won from the ordering.

⚠️ **RESULTS FROM THIS SCRIPT ARE NOT A VALID CALIBRATION READ — READ THIS.**

`data/all_ratings.json` holds ONE snapshot of ranking points (currently stamped
2026-08-19). Scoring a 2025 or January-2026 match with August-2026 points is
LOOKAHEAD: a player who climbed during 2026 is over-rated for every earlier
match they played, and one who fell is under-rated.

The symptom is unmistakable in the output — the bias FLIPS sign by year:

    atp/2025  n=573  Brier 0.2581  favourite gap  +9.9   (over-confident)
    atp/2026  n=534  Brier 0.2106  favourite gap  +0.0   (perfect)
    wta/2025  n=446  Brier 0.2313  favourite gap  +6.5   (over-confident)
    wta/2026  n=550  Brier 0.1928  favourite gap  -7.0   (under-confident)

A real model property does not reverse between two adjacent years on ~500
matches each. What is actually being measured is how much the ratings snapshot
post-dates the match. **Do not act on these numbers.**

To make this valid you need POINT-IN-TIME rankings — the ATP/WTA ranking as it
stood on each match date. ESPN's core API exposes weekly ranking snapshots
(`.../rankings/{id}` per season/week), so it is buildable; until someone builds
that history, this file measures the snapshot, not the model.

Kept in the tree because the harness is right and the leakage guard below is
worth preserving — only the ratings input is wrong.

Run: python3 scripts/tennis_winprob_backtest.py [--tour atp] [--year 2026]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402
from tennis_totals_backtest import load_matches  # noqa: E402

BUCKETS = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7),
           (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
MIN_BUCKET = 20    # below this a bucket's hit rate is noise, not a reading


def backtest(tour: str = "atp", year: int = 2026, limit: int = 600,
             best_of: int = 3) -> dict:
    matches = [m for m in load_matches(tour, year) if m["best_of"] == best_of]
    preds, outcomes = [], []
    skipped = 0

    for m in matches[:limit]:
        # Deterministic ordering — NEVER winner-first (see leakage guard above).
        a, b = sorted((m["winner"], m["loser"]))
        a_won = 1 if a == m["winner"] else 0
        try:
            d = tgm.predict(a, b, best_of=best_of)
        except Exception:
            skipped += 1
            continue
        if not isinstance(d, dict) or "match_prob" not in d:
            skipped += 1
            continue
        preds.append(d["match_prob"][d["player_a"]])
        outcomes.append(a_won)

    if not preds:
        return {"error": "NO_MATCHES_PRICED", "skipped": skipped}

    n = len(preds)
    rows = []
    for lo, hi in BUCKETS:
        idx = [i for i, p in enumerate(preds) if lo <= p < hi]
        if len(idx) < MIN_BUCKET:
            continue
        pred = statistics.fmean(preds[i] for i in idx)
        act = statistics.fmean(outcomes[i] for i in idx)
        rows.append({
            "bucket": f"{lo:.0%}-{hi:.0%}",
            "n": len(idx),
            "predicted": round(pred, 4),
            "actual": round(act, 4),
            # Positive gap = model OVER-confident; negative = UNDER-confident.
            "gap": round(pred - act, 4),
        })

    # Brier score: mean squared error of the probability. Lower is better;
    # 0.25 is what you get by saying 50% to everything.
    brier = statistics.fmean((p - o) ** 2 for p, o in zip(preds, outcomes))
    # Overall favourite-side check: when the model picks a side, how often right?
    fav_calls = [(max(p, 1 - p), o if p >= 0.5 else 1 - o)
                 for p, o in zip(preds, outcomes)]
    fav_pred = statistics.fmean(p for p, _ in fav_calls)
    fav_act = statistics.fmean(o for _, o in fav_calls)

    gaps = [r["gap"] for r in rows]
    mean_gap = statistics.fmean(gaps) if gaps else 0.0
    return {
        "tour": tour, "year": year, "best_of": best_of,
        "n_matches": n, "skipped_no_stats": skipped,
        "brier": round(brier, 4),
        "coin_flip_brier": 0.25,
        "favourite_side": {"predicted": round(fav_pred, 4),
                           "actual": round(fav_act, 4),
                           "gap": round(fav_pred - fav_act, 4)},
        "buckets": rows,
        "mean_bucket_gap": round(mean_gap, 4),
        "verdict": ("OVER-confident — model's favourites win less than it says"
                    if mean_gap > 0.03 else
                    "UNDER-confident — model's favourites win MORE than it says"
                    if mean_gap < -0.03 else
                    "calibrated within 3 points"),
        "note": "players ordered alphabetically before prediction — no result leakage",
        "INVALID": "ratings are a single CURRENT snapshot applied to past matches "
                   "(lookahead). Bias flips sign by year, which is the tell. "
                   "Needs point-in-time rankings — do not act on these numbers.",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--best-of", type=int, choices=(3, 5), default=3)
    a = ap.parse_args()
    print(json.dumps(backtest(a.tour, a.year, a.limit, a.best_of), indent=1))
