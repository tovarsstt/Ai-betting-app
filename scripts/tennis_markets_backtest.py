#!/usr/bin/env python3
"""
tennis_markets_backtest.py — are the tennis GAMES/SETS markets calibrated?

Why this exists: tennis_games_model prices markets the ML model never touched —
set handicap (-1.5 = 2-0), "wins a set", games handicap ladder, set-1 total,
match total. Only the games TOTAL had ever been measured (tennis_totals_backtest).
Every other market was an unvalidated simulation, and 2026-10-07 the sim disagreed
with Stake's set-handicap prices by ~12 points. A disagreement that size is either
an edge or a model bug, and there was no way to tell which.

Method (point-in-time on the MARKET side, honest about the rest):
  * real completed bo3 matches + per-set scores + Pinnacle closing ML
    (tennis-data.co.uk, same source as tennis_totals_backtest)
  * orient each match to a RANDOM side A (seeded) — orienting to the winner would
    bake selection bias into every probability
  * level-calibrate the sim to the devigged Pinnacle price for A, then read every
    market off the simulation — so the ML is held fixed and only the STRUCTURE
    (how matches are won: straight sets vs three, margins, set-1 length) is tested
  * compare predicted probability to what actually happened: mean predicted vs
    mean actual, Brier vs a base-rate baseline, and a reliability table

KNOWN LIMITATION (same as tennis_totals_backtest, stated not buried): serve stats
are a CURRENT snapshot applied to past matches. The market side is point-in-time.
What this CANNOT test: handicap/total PRICES — tennis-data has no closing lines for
those markets. So this proves the probabilities are calibrated (or not); it does
not prove Stake's price is beatable. A calibrated model is necessary, not
sufficient.

Run: python3 scripts/tennis_markets_backtest.py [--limit 300] [--tour atp|wta|both]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402
import tennis_totals_backtest as ttb  # noqa: E402

OUT = Path(__file__).parent.parent / "data" / "tennis_markets_validation.json"
MARGIN_LINES = (1.5, 2.5, 3.5, 4.5, 5.5)
TOTAL_LINES = (20.5, 21.5, 22.5, 23.5)
CAL_SIMS, FINAL_SIMS = 1000, 3000


def load_with_sets(tour: str, year: int) -> list[dict]:
    """ttb.load_matches drops the per-set scores — re-read them from the cached
    workbook (load_matches has already downloaded/cached it)."""
    base = ttb.load_matches(tour, year)     # populates the cache file
    import openpyxl
    shared = Path(f"/tmp/tdform_{year}_{'m' if tour == 'atp' else 'w'}.xlsx")
    path = shared if shared.exists() else Path(f"/tmp/ttb_{tour}_{year}.xlsx")
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h else "" for h in next(rows)]
    ix = {h: i for i, h in enumerate(hdr)}
    out = []
    for r in rows:
        if r is None or ix["Winner"] >= len(r) or str(r[ix["Comment"]]).strip() != "Completed":
            continue
        try:
            if int(r[ix.get("Best of", 0)] or 3) != 3:
                continue
            sets = []
            for w, l in ttb.SET_COLS[:3]:
                gw, gl = r[ix[w]], r[ix[l]]
                if gw is not None and gl is not None:
                    sets.append((int(gw), int(gl)))
            pw, pl = float(r[ix["PSW"]]), float(r[ix["PSL"]])
        except (TypeError, ValueError, KeyError):
            continue
        if len(sets) not in (2, 3) or pw <= 1 or pl <= 1:
            continue
        out.append({"winner": str(r[ix["Winner"]]).strip(),
                    "loser": str(r[ix["Loser"]]).strip(),
                    "sets": sets, "ps_w": pw, "ps_l": pl})
    return out


def calibrated_sim(a: str, b: str, target_a: float):
    doc = tgm.load()["players"]
    ka, kb = tgm.player_key(a, doc), tgm.player_key(b, doc)
    if not ka or not kb:
        return None
    pa, pb = tgm.point_prob(doc[ka]), tgm.point_prob(doc[kb])
    lo, hi = -0.08, 0.08
    for _ in range(11):
        d = (lo + hi) / 2
        mp = tgm.simulate_match(pa + d, pb - d, 3, n_sims=CAL_SIMS, seed=tgm.SEED)["match_prob_a"]
        lo, hi = (d, hi) if mp < target_a else (lo, d)
    d = (lo + hi) / 2
    sim = tgm.simulate_match(pa + d, pb - d, 3, n_sims=FINAL_SIMS)
    off = tgm.totals_offset(doc[ka].get("tour") or doc[kb].get("tour") or "")
    sim["tot"] = [t + off for t in sim["totals"]]
    return sim


def predictions(sim: dict) -> dict[str, float]:
    n = len(sim["margins"])
    sc, N = sim["set_scores"], sum(sim["set_scores"].values())
    p = {"A_straight_sets": sc.get((2, 0), 0) / N,        # A -1.5 sets
         "B_straight_sets": sc.get((0, 2), 0) / N,        # A +1.5 sets loses only if this
         "set1_over_9.5": sum(g > 9.5 for g in sim["set1_games"]) / n}
    p["A_wins_a_set"] = 1 - p["B_straight_sets"]
    p["B_wins_a_set"] = 1 - p["A_straight_sets"]
    for L in MARGIN_LINES:
        p[f"A_margin_gt_{L}"] = sum(m > L for m in sim["margins"]) / n      # A -L games
        p[f"B_margin_gt_{L}"] = sum(-m > L for m in sim["margins"]) / n     # B -L games
    for L in TOTAL_LINES:
        p[f"total_over_{L}"] = sum(t > L for t in sim["tot"]) / n
    return p


def outcomes(sets: list[tuple], a_won: bool, a_is_winner: bool) -> dict[str, int]:
    """Outcomes from A's perspective. `sets` are (winner_games, loser_games)."""
    ga = sum(w if a_is_winner else l for w, l in sets)
    gb = sum(l if a_is_winner else w for w, l in sets)
    n_sets = len(sets)
    o = {"A_straight_sets": int(a_won and n_sets == 2),
         "B_straight_sets": int((not a_won) and n_sets == 2),
         "set1_over_9.5": int(sum(sets[0]) > 9.5)}
    o["A_wins_a_set"] = 1 - o["B_straight_sets"]
    o["B_wins_a_set"] = 1 - o["A_straight_sets"]
    for L in MARGIN_LINES:
        o[f"A_margin_gt_{L}"] = int(ga - gb > L)
        o[f"B_margin_gt_{L}"] = int(gb - ga > L)
    for L in TOTAL_LINES:
        o[f"total_over_{L}"] = int(ga + gb > L)
    return o


def run(tours=("atp", "wta"), years=(2025, 2026), limit=300, seed=7) -> dict:
    rng = random.Random(seed)
    rows: list[tuple[dict, dict]] = []
    skipped = 0
    for tour in tours:
        pool = []
        for y in years:
            try:
                pool += [(tour, m) for m in load_with_sets(tour, y)]
            except SystemExit as e:
                print(f"skip {tour} {y}: {e}", file=sys.stderr)
        rng.shuffle(pool)
        for _, m in pool[:limit]:
            a_is_winner = rng.random() < 0.5
            a, b = (m["winner"], m["loser"]) if a_is_winner else (m["loser"], m["winner"])
            iw, il = 1 / m["ps_w"], 1 / m["ps_l"]
            p_win = iw / (iw + il)                       # devigged Pinnacle
            sim = calibrated_sim(a, b, p_win if a_is_winner else 1 - p_win)
            if sim is None:
                skipped += 1
                continue
            rows.append((predictions(sim), outcomes(m["sets"], a_is_winner, a_is_winner)))

    report = {"n_matches": len(rows), "skipped_no_serve_stats": skipped,
              "years": list(years), "tours": list(tours), "markets": {}}
    for k in rows[0][0] if rows else []:
        ps = [r[0][k] for r in rows]
        ys = [r[1][k] for r in rows]
        base = statistics.fmean(ys)
        brier = statistics.fmean((p - y) ** 2 for p, y in zip(ps, ys))
        brier_base = statistics.fmean((base - y) ** 2 for y in ys)
        bins = {}
        for lo, hi in ((0, .3), (.3, .45), (.45, .55), (.55, .7), (.7, 1.01)):
            sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
            if len(sel) >= 15:
                bins[f"{lo:.2f}-{min(hi, 1):.2f}"] = {
                    "n": len(sel),
                    "predicted": round(statistics.fmean(p for p, _ in sel), 3),
                    "actual": round(statistics.fmean(y for _, y in sel), 3)}
        gap = statistics.fmean(ps) - base
        report["markets"][k] = {
            "mean_predicted": round(statistics.fmean(ps), 3), "mean_actual": round(base, 3),
            "bias_pts": round(gap * 100, 1), "brier": round(brier, 4),
            "brier_baseline": round(brier_base, 4),
            "beats_baseline": brier < brier_base, "reliability": bins,
            "verdict": ("OK" if abs(gap) <= 0.03 else
                        "MODEL OVERSTATES" if gap > 0 else "MODEL UNDERSTATES")}
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300, help="matches per tour")
    ap.add_argument("--tour", choices=("atp", "wta", "both"), default="both")
    a = ap.parse_args()
    tours = ("atp", "wta") if a.tour == "both" else (a.tour,)
    rep = run(tours, limit=a.limit)
    OUT.write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: (v if k != "markets" else
                          {m: (d["mean_predicted"], d["mean_actual"], d["bias_pts"], d["verdict"])
                           for m, d in v.items()}) for k, v in rep.items()}, indent=1))
