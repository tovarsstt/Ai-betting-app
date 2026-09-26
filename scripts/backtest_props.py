#!/usr/bin/env python3
"""
backtest_props.py — walk-forward calibration of the Slip Check prop model on
real NFL play-by-play (nflverse 2025 + 2026).

Free data has no bookmaker prop lines, so each player-game gets the lines a book
would hang from what was known BEFORE kickoff: the 25th / 50th / 75th percentile
of the player's prior games (rounded to .5). Pass TDs use 1.5, anytime TD 0.5.
The opponent-defense factor is also built only from earlier weeks.

Scored with log-loss and Brier against "climatology" (always predict the base
rate). A model that can't beat climatology has no business pricing a leg.

  python3 scripts/backtest_props.py                 # score the production model
  python3 scripts/backtest_props.py --grid          # research: search yardage settings
  python3 scripts/backtest_props.py --out data/benchmarks/props_backtest.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import slip_pricer as sp  # noqa: E402

MIN_HISTORY = 4
QUANTILES = (0.25, 0.5, 0.75)
# (label, id column, value column | None = count TD rows, fixed lines | None = quantile lines)
STATS = [
    ("pass_yds", "passer_player_id", "passing_yards", None),
    ("rush_yds", "rusher_player_id", "rushing_yards", None),
    ("rec_yds", "receiver_player_id", "receiving_yards", None),
    ("receptions", "receiver_player_id", "complete_pass", None),
    ("pass_td", "passer_player_id", "pass_touchdown", (1.5,)),
    ("anytime_td", "td_player_id", None, (0.5,)),
]


def opp_factor_table(logs: pd.DataFrame) -> dict:
    """Walk-forward: (season, week, defense) -> (allowed per player-game / league, games), prior weeks only."""
    by = logs.groupby(["season", "week", "defteam"]).v.agg(["sum", "count"]).reset_index()
    out = {}
    for s, w in sorted(set(zip(by.season, by.week))):
        past = by[((by.season < s) | ((by.season == s) & (by.week < w))) & (by.season >= s - 1)]
        if past.empty:
            continue
        league = past["sum"].sum() / past["count"].sum()
        g = past.groupby("defteam")[["sum", "count"]].sum()
        for team, r in g.iterrows():
            out[(s, w, team)] = ((r["sum"] / r["count"]) / league if league > 0 else 1.0, int(r["count"]))
    return out


def samples(logs: pd.DataFrame, fixed, val) -> list:
    """(history, line, outcome, (season, week, opponent)) for every qualifying player-game."""
    out, floor = [], sp.VOLUME_FLOOR.get(val, 0.0)
    for _, g in logs.groupby("pid", sort=False):
        v = g.v.to_numpy()
        keys = list(zip(g.season, g.week, g.defteam))
        for i in range(MIN_HISTORY, len(v)):
            hist = v[:i]
            if hist.mean() < floor:
                continue
            lines = fixed or sorted({np.floor(np.quantile(hist, q)) + 0.5 for q in QUANTILES})
            out.extend((hist, ln, v[i] > ln, keys[i]) for ln in lines)
    return out


def score(ps: np.ndarray, ys: np.ndarray) -> dict:
    p = np.clip(ps, 1e-4, 1 - 1e-4)
    return {"n": int(len(p)), "logloss": round(float(-np.mean(ys * np.log(p) + (1 - ys) * np.log(1 - p))), 4),
            "brier": round(float(np.mean((p - ys) ** 2)), 4)}


def predict_production(smp, idc, val, opp) -> np.ndarray:
    return np.array([sp.prop_estimate(h, ln, True, idc, val, opp.get(key, (1.0, 0))) for h, ln, _, key in smp])


def calibration(ps: np.ndarray, ys: np.ndarray) -> list:
    bins = np.array([0, .2, .35, .45, .55, .65, .8, 1.0001])
    idx = np.digitize(ps, bins) - 1
    return [{"bin": f"{bins[b]:.2f}-{min(bins[b + 1], 1):.2f}", "n": int((idx == b).sum()),
             "pred": round(float(ps[idx == b].mean()), 3), "actual": round(float(ys[idx == b].mean()), 3)}
            for b in range(len(bins) - 1) if (idx == b).sum() >= 30]


def grid_search(smp, ys, opp, count) -> list:
    rows = []
    for hl, pk, cv, ok in itertools.product((8, 12), (8, 12, 16, 24), (0.3, 0.45, 0.6, 0.8), (None, 16.0)):
        ps = []
        for h, ln, _, key in smp:
            if ok and key in opp:
                f, n = opp[key]
                h = h * (1 + (f - 1) * n / (n + ok))
            ps.append(sp.prop_prob(h, ln, True, count, hl, pk, cv))
        rows.append({"halflife": hl, "prior_k": pk, "min_cv": cv, "opp_k": ok, **score(np.array(ps), ys)})
    return sorted(rows, key=lambda r: r["logloss"])[:5]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    report = {"method": "walk-forward, lines from pre-game player quantiles; see module docstring",
              "stats": {}}
    for label, idc, val, fixed in STATS:
        logs = sp.stat_logs(idc, val)
        smp = samples(logs, fixed, val)
        ys = np.array([s[2] for s in smp], float)
        opp = opp_factor_table(logs)
        clim = score(np.full(len(ys), ys.mean()), ys)
        ps = predict_production(smp, idc, val, opp)
        prod = score(ps, ys)
        row = {"samples": len(ys), "base_rate": round(float(ys.mean()), 3), "climatology": clim,
               "production": prod, "beats_climatology": prod["logloss"] < clim["logloss"],
               "params": dict(sp.PROP_PARAMS.get(val, {})), "calibration": calibration(ps, ys)}
        if a.grid and val not in sp.TD_STATS:
            row["grid_top5"] = grid_search(smp, ys, opp, val in sp.COUNT_STATS)
        report["stats"][label] = row
        print(f"{label:11s} n={len(ys):5d} base {ys.mean():.3f} | climatology LL {clim['logloss']:.4f} | "
              f"model LL {prod['logloss']:.4f} | {'BEATS' if row['beats_climatology'] else 'LOSES TO'} base rate")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
