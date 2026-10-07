#!/usr/bin/env python3
"""
recalibrate.py — keep every calibrated number current ("adapt always") and say when one drifts.

    python3 scripts/recalibrate.py --refresh          # re-download the open datasets first (Kaggle anonymous API, football-data)
    python3 scripts/recalibrate.py --quick            # per-sport score math only (a minute)
    python3 scripts/recalibrate.py                    # + tennis & team-sport context tests + team ratings (long)

It snapshots the stored calibration files, re-runs the fits, and prints a DRIFT report: every key parameter old -> new,
flagged when it moved more than its tolerance. A parameter that drifts is a signal to re-read that sport's registry
entry (engine_all.py registry) before trusting yesterday's edge.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
KG = Path("/tmp/kg")

DATASETS = {   # slug -> folder (Kaggle anonymous download works without a token)
    "alimoh89/tennis-results-and-betting-odds-20142025": "tennis_odds",
    "cviaxmiwnptr/nba-betting-data-october-2007-to-june-2024": "nba_odds",
    "jonathanncoletti/nhl-historical-game-data": "nhl_hist",
    "tobycrabtree/nfl-scores-and-betting-data": "nfl_spreadspoke",
    "robbypeery/closing-odds": "closing_odds",
    "eddieglush/market-calibration-dataset": "mc",
}
FOOTBALL = {"leagues": ("E0", "SP1", "D1", "I1", "F1"), "seasons": ("2223", "2324", "2425", "2526", "2627")}

TRACK = {   # file -> [(label, path-in-json, tolerance)]
    "sport_math_calibration.json": [("MLB NB shape r", ["mlb", "families", "nb", "param"], 1.0), ("NBA sigma margin", ["nba", "sigma_margin"], 0.4), ("NBA sigma total", ["nba", "sigma_total"], 0.8),
                                    ("NFL sigma margin", ["nfl", "sigma_margin"], 0.5)],
    "tennis_context_coefficients.json": [("tennis rest logit/day", ["rest_days_logit_per_day"], 0.01), ("tennis load7", ["load7_logit_per_10_games"], 0.006), ("tennis altitude games", ["altitude_500m_total_games"], 0.25)],
    "engine_v2_calibration.json": [("tennis day sd", ["day_sd"], 0.01)],
}


def get(d, path):
    for p in path:
        d = d.get(p, {}) if isinstance(d, dict) else {}
    return d if isinstance(d, (int, float)) else None


def snapshot() -> dict:
    return {f: json.loads((DATA / f).read_text()) for f in TRACK if (DATA / f).exists()}


def refresh() -> None:
    KG.mkdir(parents=True, exist_ok=True)
    for slug, folder in DATASETS.items():
        z = KG / f"{folder}.zip"
        subprocess.run(["curl", "-sSL", "-m", "300", "-o", str(z), f"https://www.kaggle.com/api/v1/datasets/download/{slug}"], check=False)
        subprocess.run(["unzip", "-qo", str(z), "-d", str(KG / folder)], check=False)
        print("refreshed", folder)
    fd = KG / "ext" / "fd"
    fd.mkdir(parents=True, exist_ok=True)
    for s in FOOTBALL["seasons"]:
        for lg in FOOTBALL["leagues"]:
            subprocess.run(["curl", "-sSL", "-m", "60", "-o", str(fd / f"{lg}_{s}.csv"), f"https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv"], check=False)
    print("football-data refreshed")


def run(script: str) -> None:
    print(f"\n>>> {script}", flush=True)
    try:
        subprocess.run([sys.executable, str(HERE / script)], check=True)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    before = snapshot()
    if a.refresh:
        refresh()
    run("sport_math.py")
    if not a.quick:
        for s in ("context_effects_tennis.py", "context_effects_sports.py", "heuristic_calibration.py", "team_ratings.py"):
            run(s)
    after = snapshot()
    print("\n=== DRIFT REPORT (old -> new) ===")
    flagged = 0
    for f, items in TRACK.items():
        for label, path, tol in items:
            o, n = get(before.get(f, {}), path), get(after.get(f, {}), path)
            if o is None or n is None:
                continue
            flag = abs(n - o) > tol
            flagged += flag
            print(f"  {label:<26} {o:>9.4f} -> {n:>9.4f}  {'** DRIFT **' if flag else 'ok'}")
    print(f"\n{flagged} parameter(s) drifted beyond tolerance." if flagged else "\nall tracked parameters stable.")
