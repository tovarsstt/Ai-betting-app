#!/usr/bin/env python3
"""
heterogeneity_tests.py — "the Steelers don't play the Ravens like they play the Bucs".

A pooled test ("is the rest effect != 0 on average?") can say NO while team- and matchup-specific effects are
real but cancel out. So test heterogeneity directly, always PAST-ONLY (each game is predicted from earlier games):

  A. TEAM persistence   does a team's past mean result-vs-closing-line (own team, home/away oriented) predict its next one?
  B. MATCHUP persistence does the past mean result-vs-line of THIS pair (oriented) predict the next meeting? (style /
                         rivalry / defence-vs-offence collisions). Same for TOTALS (pace and defence matchups).
  C. CONTEXT x OPPONENT  does the rest / short-week effect change with strength gap, divisional rivalry, favourite status?

If the market already knows each team and each matchup, every slope is 0. A positive, significant slope is a
team/pair-level edge the engine can use through shrinkage:  adj = slope * n/(n+k) * past_mean.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

KG = Path("/tmp/kg")
DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "heterogeneity_results.json"


def frames() -> dict:
    out = {}
    # NFL
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    teams = pd.read_csv(KG / "nfl_spreadspoke/nfl_teams.csv")
    idmap, div = dict(zip(teams.team_name, teams.team_id)), dict(zip(teams.team_name, teams.team_division))
    d = d[(d.schedule_season >= 1990) & d.spread_favorite.notna() & d.score_home.notna() & (d.team_favorite_id != "PICK") & d.team_favorite_id.notna()].copy()
    d["date"] = pd.to_datetime(d.schedule_date, format="%m/%d/%Y")
    hf = d.team_favorite_id == d.team_home.map(idmap)
    d["res"] = (d.score_home - d.score_away) - np.where(hf, -d.spread_favorite, d.spread_favorite)
    d["tres"] = (d.score_home + d.score_away) - pd.to_numeric(d.over_under_line, errors="coerce")
    d["exp_margin"] = np.where(hf, -d.spread_favorite, d.spread_favorite)
    d["div"] = (d.team_home.map(div) == d.team_away.map(div)).astype(float)
    out["nfl"] = d.rename(columns={"team_home": "home", "team_away": "away"})[["date", "home", "away", "res", "tres", "exp_margin", "div"]].dropna(subset=["res"]).sort_values("date").reset_index(drop=True)
    # NBA
    n = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
    n = n[n.regular == True].dropna(subset=["spread", "total", "score_home", "score_away"]).copy()
    n["date"] = pd.to_datetime(n.date)
    exp = np.where(n.whos_favored == "home", n.spread, -n.spread)
    n["res"], n["tres"], n["exp_margin"], n["div"] = (n.score_home - n.score_away) - exp, n.score_home + n.score_away - n.total, exp, 0.0
    out["nba"] = n[["date", "home", "away", "res", "tres", "exp_margin", "div"]].sort_values("date").reset_index(drop=True)
    # Soccer (5 leagues)
    fr = [pd.read_csv(f, encoding="latin1", on_bad_lines="skip", low_memory=False) for f in sorted((KG / "ext/fd").glob("*.csv"))]
    s = pd.concat(fr, ignore_index=True).dropna(subset=["FTHG", "FTAG", "HomeTeam", "AwayTeam", "AHCh", "PC>2.5", "PC<2.5"]).copy()
    s["date"] = pd.to_datetime(s.Date, dayfirst=True, errors="coerce")
    po, pu = 1 / s["PC>2.5"], 1 / s["PC<2.5"]
    grid = np.linspace(0.4, 7.0, 4000)
    lam = np.interp((po / (po + pu)).clip(0.03, 0.97).values, stats.poisson.sf(2, grid), grid)
    s["res"], s["tres"], s["exp_margin"], s["div"] = (s.FTHG - s.FTAG) + s.AHCh, (s.FTHG + s.FTAG) - lam, -s.AHCh, 0.0
    out["soccer"] = s.rename(columns={"HomeTeam": "home", "AwayTeam": "away"})[["date", "home", "away", "res", "tres", "exp_margin", "div"]].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out


def past_mean(df: pd.DataFrame, key: pd.Series, val: str, sign: pd.Series | None = None, min_n: int = 3):
    """Expanding mean of `val` over EARLIER rows with the same key (oriented by `sign`); returns (mean, count)."""
    v = df[val] * (sign if sign is not None else 1.0)
    g = v.groupby(key)
    cs = g.cumsum() - v                                       # excludes the current row
    n = g.cumcount()
    m = (cs / n.replace(0, np.nan)) * (sign if sign is not None else 1.0)   # re-orient to the current row's perspective
    return m.where(n >= min_n), n


def slope(y: np.ndarray, x: np.ndarray, label: str) -> dict:
    ok = ~np.isnan(x) & ~np.isnan(y)
    if ok.sum() < 300:
        return {"n": int(ok.sum()), "note": "too few"}
    m = sm.OLS(y[ok], sm.add_constant(x[ok])).fit(cov_type="HC1")
    # time-split replication: first half vs second half of the eligible rows
    idx = np.where(ok)[0]
    h = len(idx) // 2
    a, b = idx[:h], idx[h:]
    m1 = sm.OLS(y[a], sm.add_constant(x[a])).fit(cov_type="HC1")
    m2 = sm.OLS(y[b], sm.add_constant(x[b])).fit(cov_type="HC1")
    return {"n": int(ok.sum()), "slope": float(m.params[1]), "se": float(m.bse[1]), "t": float(m.tvalues[1]), "p": float(m.pvalues[1]),
            "slope_first_half": float(m1.params[1]), "p_first": float(m1.pvalues[1]), "slope_second_half": float(m2.params[1]), "p_second": float(m2.pvalues[1]),
            "replicates": bool(m.pvalues[1] < 0.05 and m1.pvalues[1] < 0.10 and m2.pvalues[1] < 0.10 and np.sign(m1.params[1]) == np.sign(m2.params[1]))}


def run() -> dict:
    res = {}
    for sport, d in frames().items():
        r = {"n_games": len(d)}
        d = d.copy()
        a, b = d.home.astype(str), d.away.astype(str)
        first = a < b
        pair = np.where(first, a + "|" + b, b + "|" + a)
        sgn = pd.Series(np.where(first, 1.0, -1.0), index=d.index)           # orientation of the pair's "first" team
        d["pair"] = pair
        # B. matchup persistence (margin residual oriented to the pair's first team; totals unoriented)
        pm, pn = past_mean(d, d.pair, "res", sgn, min_n=3)
        r["matchup_margin"] = slope(d.res.values * sgn.values, (pm * sgn).values, "pair margin")
        pt, _ = past_mean(d, d.pair, "tres", None, min_n=3)
        r["matchup_total"] = slope(d.tres.values, pt.values, "pair total")
        # A. team persistence — each team's own past residual (home/away oriented to that team), predict next game for the same team
        long = pd.concat([pd.DataFrame({"date": d.date, "team": d.home, "res": d.res, "tres": d.tres, "row": d.index, "side": "h"}),
                          pd.DataFrame({"date": d.date, "team": d.away, "res": -d.res, "tres": d.tres, "row": d.index, "side": "a"})]).sort_values(["team", "date"]).reset_index(drop=True)
        tm, tn = past_mean(long, long.team, "res", None, min_n=20)
        r["team_margin"] = slope(long.res.values, tm.values, "team margin")
        tt, _ = past_mean(long, long.team, "tres", None, min_n=20)
        r["team_total"] = slope(long.tres.values, tt.values, "team total")
        # C. context x opponent: favourite status & strength gap vs the residual (does the market under/over-react to big favourites?)
        r["favourite_size_vs_resid"] = slope(d.res.values, d.exp_margin.values, "fav size")
        if d["div"].sum() > 0:
            r["divisional_x_favourite"] = slope(d.res.values, (d["div"] * d.exp_margin).values, "div x fav")
        res[sport] = r
    return res


if __name__ == "__main__":
    out = run()
    OUT.write_text(json.dumps(out, indent=1))
    for sp, r in out.items():
        print(f"\n===== {sp.upper()} ({r['n_games']:,} games) =====")
        for k, v in r.items():
            if k == "n_games":
                continue
            if "slope" not in v:
                print(f"  {k:<26} {v}")
                continue
            print(f"  {k:<26} n={v['n']:>6,} slope {v['slope']:+.3f} (t={v['t']:+.2f}, p={v['p']:.3f}) | halves {v['slope_first_half']:+.3f}/{v['slope_second_half']:+.3f}  -> {'REPLICATES' if v['replicates'] else 'no'}")
