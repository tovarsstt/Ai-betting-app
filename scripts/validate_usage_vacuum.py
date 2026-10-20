"""
validate_usage_vacuum.py — out-of-sample check of the vacated-usage formula on REAL 2025-26 box scores.

Train rates on games before the split date, then for every later team-game predict each rotation player's share of his team's
points from (who actually played, who started) and compare with the naive baseline "his usual share when playing".
Reported separately for games where a rotation player (>= 20 mpg in train) was absent — the case this model exists for.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

import usage_vacuum as uv

DATA = Path(__file__).parent.parent / "data" / "nba"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    p = pd.read_csv(DATA / "player_2025.csv", dtype={"athlete_id": str})
    t = pd.read_csv(DATA / "team_2025.csv")
    real = t.groupby("team").size()
    t = t[t.team.isin(real[real >= 50].index)].copy()
    t["reb"] = t.oreb + t.dreb
    tt = t[["game_id", "team_id", "date", "pts", "ast", "reb", "fg3m"]].rename(columns={c: f"{c}_t" for c in ("pts", "ast", "reb", "fg3m")})
    p = p[(p.dnp == 0) & (p["min"] >= 8)].merge(tt, on=["game_id", "team_id"])
    return p, t


def main() -> None:
    p, t = load()
    cut = p.date.sort_values().iloc[int(len(p) * 0.5)]
    tr, te = p[p.date < cut], p[p.date >= cut]
    rates = uv.build_rates(tr, tr[["game_id", "team_id"] + [c for c in tr.columns if c.endswith("_t")]].drop_duplicates(["game_id", "team_id"]))
    rot = set(rates[(rates.mpg >= 15) & (rates.n >= 15)].index)
    big = set(rates[(rates.mpg >= 20) & (rates.n >= 15)].index)
    cover = float((p[p.date < cut].groupby(["game_id", "team_id"]).pts.sum() / p[p.date < cut].groupby(["game_id", "team_id"]).pts_t.first()).mean())
    p = p.sort_values("date")
    recent = {tid: g.groupby("date").athlete_id.apply(set).sort_index() for tid, g in p.groupby("team_id")}
    rows = []
    for (gid, tid), g in te.groupby(["game_id", "team_id"]):
        avail = list(g.athlete_id)
        starters = set(g[g.starter == 1].athlete_id)
        dte = g.date.iloc[0]
        prior = recent[tid][recent[tid].index < dte].tail(10)                 # who really belonged to the team over its last 10 games
        team_pool = set().union(*prior) & big if len(prior) else set()
        absent_big = len(team_pool - set(avail))
        r = uv.roles(avail, starters, rates)
        for _, x in g.iterrows():
            a = x.athlete_id
            if a not in rot:
                continue
            actual = x.pts / x.pts_t
            base = float(rates.share_pts.get(a, np.nan))
            pred = r[a]["pts_share"] * cover
            rows.append({"absent_big": absent_big, "actual": actual, "base": base, "pred": pred, "ast_a": x.ast / max(x.ast_t, 1), "ast_b": float(rates.share_ast.get(a, np.nan)), "ast_p": r[a]["ast_share"] * cover})
    d = pd.DataFrame(rows).dropna()
    print(f"coverage of rotation players (>=8 min) in team points: {cover:.3f}")
    print(f"train < {cut}: {len(tr)} player-games; test {len(d)} rotation player-games")
    for lab, m in (("all games", d.absent_big >= 0), ("no rotation player absent", d.absent_big == 0), ("1+ rotation player absent", d.absent_big >= 1), ("2+ absent", d.absent_big >= 2)):
        x = d[m]
        if len(x) < 30:
            continue
        mae_b, mae_p = (x.actual - x.base).abs().mean(), (x.actual - x.pred).abs().mean()
        print(f"  {lab:28s} n={len(x):5d}  pts-share MAE baseline {mae_b*100:.2f} pts | vacuum model {mae_p*100:.2f} pts | ast-share MAE {((x.ast_a-x.ast_b).abs().mean())*100:.2f} -> {((x.ast_a-x.ast_p).abs().mean())*100:.2f}")
    x = d[d.absent_big >= 1]
    print(f"  bias when a rotation player is absent: actual {x.actual.mean()*100:.2f}% | baseline {x.base.mean()*100:.2f}% | vacuum {x.pred.mean()*100:.2f}%")
    print(f"  correlation of (actual-base) with (pred-base) in absence games: {np.corrcoef(x.actual - x.base, x.pred - x.base)[0,1]:.3f}")


if __name__ == "__main__":
    main()
