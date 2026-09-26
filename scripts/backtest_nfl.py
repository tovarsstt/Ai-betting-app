#!/usr/bin/env python3
"""
backtest_nfl.py — walk-forward test of the Judge's NFL lenses on real history
(nflverse games.csv: final scores + closing lines).

For every regular-season game from week 2 on, ratings are built ONLY from
games before that week (prior season as prior + current season so far), then
compared with the result and with the closing spread. Outputs:
  * MAE / RMSE of market, ratings and the blend
  * the blend weight on ratings that minimizes error (-> Judge W_RATINGS)
  * best PRIOR_GAMES / QB_CHANGE_PRIOR
  * straight-up and ATS hit rates of the ratings lens

  python3 scripts/backtest_nfl.py [--seasons 2019-2025] [--out data/benchmarks/nfl_backtest.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import nflverse_feed as nf  # noqa: E402


def week_qbs(g: pd.DataFrame) -> dict:
    return {**dict(zip(g.home_team, g.home_qb_name)), **dict(zip(g.away_team, g.away_qb_name))}


def run(games: pd.DataFrame, seasons: list[int], prior_games: float, qb_factor: float) -> pd.DataFrame:
    nf.PRIOR_GAMES, nf.QB_CHANGE_PRIOR = prior_games, qb_factor
    rows = []
    for s in seasons:
        reg = games[(games.season == s) & (games.game_type == "REG") & games.home_score.notna()]
        for w in sorted(reg.week.unique()):
            if w < 2:
                continue
            wk = reg[reg.week == w]
            r = nf.team_ratings(s, int(w), games, current_qb=week_qbs(wk))
            for g in wk.itertuples():
                if g.home_team not in r["teams"] or g.away_team not in r["teams"] or pd.isna(g.spread_line):
                    continue
                m, _ = nf.predict(r, g.home_team, g.away_team, g.location == "Neutral")
                rows.append({"season": s, "week": w, "result": g.result, "market": g.spread_line,
                             "ratings": m})
    return pd.DataFrame(rows)


def metrics(df: pd.DataFrame) -> dict:
    out = {}
    for k in ("market", "ratings"):
        e = df.result - df[k]
        out[k] = {"mae": round(float(e.abs().mean()), 3), "rmse": round(float(np.sqrt((e ** 2).mean())), 3)}
    best = min(((w, float((df.result - ((1 - w) * df.market + w * df.ratings)).abs().mean()))
                for w in np.arange(0, 1.001, 0.05)), key=lambda x: x[1])
    blend = (1 - best[0]) * df.market + best[0] * df.ratings
    nz = df[df.result != 0]
    ats = nz[(nz.ratings - nz.market).abs() >= 3]
    ats = ats[(ats.result - ats.market) != 0]
    out["best_ratings_weight"] = round(best[0], 2)
    out["blend_mae"] = round(best[1], 3)
    out["resid_sd_blend"] = round(float((df.result - blend).std()), 2)
    out["ratings_straight_up_hit"] = round(float((np.sign(nz.ratings) == np.sign(nz.result)).mean()), 4)
    out["market_straight_up_hit"] = round(float((np.sign(nz.market) == np.sign(nz.result)).mean()), 4)
    out["ratings_ats_when_disagree_3plus"] = {
        "n": int(len(ats)),
        "hit": round(float((np.sign(ats.ratings - ats.market) == np.sign(ats.result - ats.market)).mean()), 4)
        if len(ats) else None}
    out["n_games"] = int(len(df))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2019-2025")
    ap.add_argument("--out")
    a = ap.parse_args()
    lo, hi = map(int, a.seasons.split("-"))
    seasons = list(range(lo, hi + 1))
    games = nf.load_games()
    grid = []
    for pg in (2.0, 4.0, 6.0, 8.0, 12.0):
        for qf in (1.0, 0.5, 0.25):
            m = metrics(run(games, seasons, pg, qf))
            grid.append({"prior_games": pg, "qb_change_prior": qf, **m})
            print(f"prior={pg:>4} qb={qf:<4} ratings MAE {m['ratings']['mae']:.3f} | market {m['market']['mae']:.3f} "
                  f"| best w {m['best_ratings_weight']:.2f} -> blend {m['blend_mae']:.3f} "
                  f"| SU ratings {m['ratings_straight_up_hit']:.3f} vs market {m['market_straight_up_hit']:.3f}",
                  flush=True)
    best = min(grid, key=lambda g: (g["blend_mae"], g["ratings"]["mae"]))
    report = {"seasons": a.seasons, "source": "nflverse games.csv (closing spread_line, final scores)",
              "best": best, "grid": grid}
    print(json.dumps(best, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
