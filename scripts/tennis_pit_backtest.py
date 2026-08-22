#!/usr/bin/env python3
"""
tennis_pit_backtest.py — POINT-IN-TIME calibration of the tennis rank model.

The valid replacement for tennis_winprob_backtest.py, which is stamped INVALID
because it scored past matches with a single CURRENT ratings snapshot and its
bias flipped sign between adjacent years (global rule 22).

Here every match is priced with the ranking that stood **on or before the day it
was played**, read from data/tennis_rank_history.json
(fetch_tennis_rank_history.py). No lookahead. Matches outside the archived window
are SKIPPED rather than falling back to current ranks — a smaller honest sample
beats a large dishonest one.

Model under test: the points logistic edge_api prices every tennis moneyline on —
`logit = (ln(points_a) - ln(points_b)) * 0.9`, rank-difference fallback.

Leakage guard: results rows are Winner/Loser, so the two sides are ordered
DETERMINISTICALLY (alphabetically) before predicting.

Run: python3 scripts/tennis_pit_backtest.py [--tour atp] [--best-of 3]
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
from tennis_totals_backtest import load_matches  # noqa: E402

SCALE = 0.9        # must mirror edge_api's tennis logit
BUCKETS = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7),
           (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
MIN_BUCKET = 20


def _resolve(name: str, players: dict) -> dict | None:
    """Match tennis-data's "Sinner J." to the archive's "Jannik Sinner".

    Same rule as edge_api.get_ratings: exact, then surname + first initial in
    EITHER name order, and only on a UNIQUE hit — "Wang X." matches both
    Wang Xinyu and Wang Xiyu, and guessing between them would attach the wrong
    player's ranking to a result.
    """
    if name in players:
        return players[name]
    toks = [t for t in name.lower().replace(",", " ").replace(".", " ").split() if t]
    if len(toks) < 2 or len(toks[-1]) != 1:
        return None
    surname, initial = " ".join(toks[:-1]), toks[-1]
    hits = []
    for pname, rec in players.items():
        parts = pname.lower().split()
        if len(parts) < 2:
            continue
        if (" ".join(parts[1:]) == surname and parts[0][:1] == initial) or \
           (parts[0] == surname and parts[1][:1] == initial):
            hits.append(rec)
    return hits[0] if len(hits) == 1 else None


def _prob(ra: dict, rb: dict) -> float:
    pa, pb = float(ra.get("points") or 0), float(rb.get("points") or 0)
    if pa > 0 and pb > 0:
        logit = (math.log(pa) - math.log(pb)) * SCALE
    else:
        logit = (float(rb.get("rank", 100)) - float(ra.get("rank", 100))) * 0.010
    return 1.0 / (1.0 + math.exp(-logit))


def backtest(tour: str = "atp", year: int = 2026, best_of: int = 3) -> dict:
    hist = load_history()
    matches = [m for m in load_matches(tour, year)
               if m["best_of"] == best_of and m.get("date")]

    preds, outs = [], []
    skipped_no_snapshot = skipped_no_player = 0
    for m in matches:
        snap = ranking_as_of(tour, m["date"], hist)
        if not snap:
            skipped_no_snapshot += 1
            continue
        a, b = sorted((m["winner"], m["loser"]))
        ra, rb = _resolve(a, snap["players"]), _resolve(b, snap["players"])
        if not ra or not rb:
            skipped_no_player += 1
            continue
        preds.append(_prob(ra, rb))
        outs.append(1 if a == m["winner"] else 0)

    if len(preds) < 50:
        return {"error": "TOO_FEW_MATCHES", "n": len(preds),
                "skipped_no_snapshot": skipped_no_snapshot,
                "skipped_no_player": skipped_no_player,
                "note": "archive does not cover enough of this season yet — "
                        "run fetch_tennis_rank_history.py weekly to accumulate"}

    rows = []
    for lo, hi in BUCKETS:
        idx = [i for i, p in enumerate(preds) if lo <= p < hi]
        if len(idx) < MIN_BUCKET:
            continue
        pr = statistics.fmean(preds[i] for i in idx)
        ac = statistics.fmean(outs[i] for i in idx)
        # Significance, so a thin bucket cannot masquerade as a finding.
        # Binomial SE on the PREDICTED rate; |gap| > 1.96 SE = real at 95%.
        se = math.sqrt(max(pr * (1 - pr), 1e-9) / len(idx))
        z = (pr - ac) / se if se else 0.0
        rows.append({"bucket": f"{lo:.0%}-{hi:.0%}", "n": len(idx),
                     "predicted": round(pr, 4), "actual": round(ac, 4),
                     "gap": round(pr - ac, 4),
                     "z": round(z, 2), "significant": abs(z) > 1.96,
                     # Shrink the correction toward zero by how noisy it is:
                     # a 2-SE effect keeps half its size, a 4-SE effect nearly
                     # all of it. Stops a 24-match bucket moving prices as hard
                     # as a 700-match one.
                     "shrunk_correction": round(-(pr - ac) * (z ** 2 / (z ** 2 + 4))
                                                if se else 0.0, 4)})

    # MULTIPLE COMPARISONS. Twelve buckets are tested across the two tours, so
    # at a=0.05 roughly one "significant" result is expected from noise alone.
    # A per-bucket z is therefore not enough to justify moving real prices —
    # Bonferroni raises the bar to a/12, i.e. |z| > 2.87. Reported honestly so a
    # finding that does not clear it cannot be quoted as if it had.
    n_tests = 12
    z_bonf = 2.87
    for r in rows:
        r["survives_bonferroni"] = abs(r["z"]) > z_bonf
        if not r["survives_bonferroni"]:
            r["shrunk_correction"] = 0.0     # do not move prices on it

    brier = statistics.fmean((p - o) ** 2 for p, o in zip(preds, outs))
    fav = [(max(p, 1 - p), o if p >= 0.5 else 1 - o) for p, o in zip(preds, outs)]
    fp = statistics.fmean(p for p, _ in fav)
    fa = statistics.fmean(o for _, o in fav)
    gap = fp - fa
    return {
        "tour": tour, "year": year, "best_of": best_of,
        "n_matches": len(preds),
        "skipped_no_snapshot": skipped_no_snapshot,
        "skipped_no_player": skipped_no_player,
        "window": {"from": min(m["date"] for m in matches if m.get("date")),
                   "archive_weeks": len((hist.get("tours") or {}).get(tour, {}))},
        "brier": round(brier, 4),
        "coin_flip_brier": 0.25,
        "favourite_side": {"predicted": round(fp, 4), "actual": round(fa, 4),
                           "gap": round(gap, 4)},
        "buckets": rows,
        "verdict": ("OVER-confident — favourites win LESS than the model says"
                    if gap > 0.03 else
                    "UNDER-confident — favourites win MORE than the model says"
                    if gap < -0.03 else "calibrated within 3 points"),
        "point_in_time": True,
        "multiple_comparisons": {
            "tests_across_tours": n_tests,
            "bonferroni_z": z_bonf,
            "any_bucket_survives": any(r["survives_bonferroni"] for r in rows),
            "note": "corrections are ZEROED unless a bucket clears the corrected "
                    "threshold — one nominally-significant result in twelve is "
                    "what noise looks like",
        },
        "note": "ranking as of each match date; alphabetical ordering (no leakage)",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--best-of", type=int, choices=(3, 5), default=3)
    a = ap.parse_args()
    print(json.dumps(backtest(a.tour, a.year, a.best_of), indent=1))
