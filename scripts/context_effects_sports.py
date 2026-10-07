#!/usr/bin/env python3
"""
context_effects_sports.py — niche variables per sport, tested against each sport's own CLOSING line.

Same discipline as context_effects_tennis.py: frozen hypothesis list per sport, features from earlier games only,
effects measured on (result - what the closing line already says), fit on the early seasons / replicate on the
late ones, Holm correction within each sport. An effect is ACCEPTED only if significant in BOTH periods with the same sign.

  SOCCER (5 leagues, 2022-26)  rest days (home - away), short rest (<=3d) home/away, referee tendency (rolling, past only)
  NFL    (1990-2025)           rest diff, short week (<=5d), bye (>=11d), divisional, Thursday, dome vs outdoor
  NBA    (2008-2026)           Denver/Utah altitude home, road 2nd night of a back-to-back, 3-in-4 for either side
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
OUT = DATA / "sport_context_coefficients.json"


def holm(ps: dict) -> dict:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def test_family(y: np.ndarray, X: pd.DataFrame, train: np.ndarray, label: str) -> dict:
    """OLS of residual y on each feature separately; train/test replication; Holm over the family."""
    res, rawp = {}, {}
    for c in X.columns:
        x = X[c].values.astype(float)
        ok = ~np.isnan(x) & ~np.isnan(y)
        a, b = ok & train, ok & ~train
        if a.sum() < 200 or b.sum() < 100 or np.nanstd(x[a]) == 0 or np.nanstd(x[b]) == 0:   # constant in one period -> untestable
            continue
        m = sm.OLS(y[a], sm.add_constant(x[a])).fit(cov_type="HC1")
        mt = sm.OLS(y[b], sm.add_constant(x[b])).fit(cov_type="HC1")
        res[c] = {"beta": float(m.params[1]), "se": float(m.bse[1]), "p_train": float(m.pvalues[1]), "n_train": int(a.sum()),
                  "beta_test": float(mt.params[1]), "se_test": float(mt.bse[1]), "p_test": float(mt.pvalues[1]), "n_test": int(b.sum()),
                  "x_sd": float(np.nanstd(x[ok]))}
        rawp[c] = res[c]["p_train"]
    adj = holm(rawp)
    for c, r in res.items():
        r["p_holm"] = adj[c]
        r["accepted"] = bool(adj[c] < 0.05 and np.sign(r["beta"]) == np.sign(r["beta_test"]) and r["p_test"] < 0.05)
        w1, w2 = 1 / r["se"] ** 2, 1 / r["se_test"] ** 2
        bc, sec = (r["beta"] * w1 + r["beta_test"] * w2) / (w1 + w2), (w1 + w2) ** -0.5
        z = abs(bc) / sec
        r["beta_final"] = float(bc * max(0.0, 1 - 1 / z ** 2)) if r["accepted"] else 0.0
        r["ci95"] = [float(bc - 1.96 * sec), float(bc + 1.96 * sec)]
    return res


def rest_days(df: pd.DataFrame, home: str, away: str, date: str, cap: float = 14.0) -> pd.DataFrame:
    long = pd.concat([df[[date, home]].rename(columns={home: "team"}).assign(side="h", i=df.index),
                      df[[date, away]].rename(columns={away: "team"}).assign(side="a", i=df.index)]).sort_values(["team", date])
    long["rest"] = long.groupby("team")[date].diff().dt.days.clip(upper=cap)
    p = long.pivot_table(index="i", columns="side", values="rest")
    return p.rename(columns={"h": "rest_h", "a": "rest_a"})


def soccer() -> dict:
    fr = []
    for f in sorted((KG / "ext/fd").glob("*.csv")):
        d = pd.read_csv(f, encoding="latin1", on_bad_lines="skip", low_memory=False)
        fr.append(d.assign(league=f.name[:2]))
    d = pd.concat(fr, ignore_index=True).dropna(subset=["FTHG", "FTAG", "HomeTeam", "AwayTeam", "AHCh", "PC>2.5", "PC<2.5"]).copy()
    d["date"] = pd.to_datetime(d.Date, dayfirst=True, errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    d = d.join(rest_days(d, "HomeTeam", "AwayTeam", "date"))
    d["ah_resid"] = (d.FTHG - d.FTAG) + d.AHCh                       # >0: home beat the closing handicap
    po, pu = 1 / d["PC>2.5"], 1 / d["PC<2.5"]
    pov = (po / (po + pu)).clip(0.03, 0.97)
    grid = np.linspace(0.4, 7.0, 4000)
    lam = np.interp(pov.values, stats.poisson.sf(2, grid), grid)
    d["tot_resid"] = (d.FTHG + d.FTAG) - lam
    # referee tendency from PAST matches only (expanding mean, shifted), min 15 prior games
    d["ref"] = d.get("Referee")
    d["ref_prior_tot"] = d.groupby("ref").tot_resid.transform(lambda s: s.shift(1).expanding(min_periods=15).mean())
    d["ref_prior_n"] = d.groupby("ref").tot_resid.transform(lambda s: s.shift(1).expanding().count())
    X = pd.DataFrame({"rest_diff": (d.rest_h.clip(upper=8) - d.rest_a.clip(upper=8)), "home_short_rest": (d.rest_h <= 3).astype(float),
                      "away_short_rest": (d.rest_a <= 3).astype(float), "ref_prior_total_resid": d.ref_prior_tot})
    train = (d.date < "2025-01-01").values
    return {"asian_handicap_resid": test_family(d.ah_resid.values, X[["rest_diff", "home_short_rest", "away_short_rest"]], train, "ah"),
            "total_goals_resid": test_family(d.tot_resid.values, X, train, "tot"), "n": len(d)}


def nfl() -> dict:
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    teams = pd.read_csv(KG / "nfl_spreadspoke/nfl_teams.csv")
    idmap, div = dict(zip(teams.team_name, teams.team_id)), dict(zip(teams.team_name, teams.team_division))
    d = d[(d.schedule_season >= 1990) & d.spread_favorite.notna() & d.score_home.notna() & (d.team_favorite_id != "PICK") & d.team_favorite_id.notna()].copy()
    d["date"] = pd.to_datetime(d.schedule_date, format="%m/%d/%Y")
    d = d.sort_values("date").reset_index(drop=True)
    d = d.join(rest_days(d, "team_home", "team_away", "date", cap=21))
    home_fav = d.team_favorite_id == d.team_home.map(idmap)
    d["res"] = (d.score_home - d.score_away) - np.where(home_fav, -d.spread_favorite, d.spread_favorite)
    d["tot_res"] = (d.score_home + d.score_away) - pd.to_numeric(d.over_under_line, errors="coerce")
    dv = d.team_home.map(div) == d.team_away.map(div)
    indoor = d.weather_detail.fillna("").str.contains("indoor|retractable \\(closed", case=False) | d.stadium.fillna("").str.contains("dome", case=False)
    X = pd.DataFrame({"rest_diff": d.rest_h.clip(upper=14) - d.rest_a.clip(upper=14), "home_short_week": (d.rest_h <= 5).astype(float),
                      "away_short_week": (d.rest_a <= 5).astype(float), "home_bye": (d.rest_h >= 11).astype(float), "away_bye": (d.rest_a >= 11).astype(float),
                      "divisional": dv.astype(float), "thursday": (d.date.dt.dayofweek == 3).astype(float)})
    X2 = pd.DataFrame({"dome": indoor.astype(float), "divisional": dv.astype(float), "thursday": (d.date.dt.dayofweek == 3).astype(float),
                       "short_week_any": ((d.rest_h <= 5) | (d.rest_a <= 5)).astype(float)})
    train = (d.schedule_season <= 2016).values
    return {"spread_resid": test_family(d.res.values, X, train, "spread"), "total_resid": test_family(d.tot_res.values, X2, train, "total"), "n": len(d)}


def nba() -> dict:
    d = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
    d = d[d.regular == True].dropna(subset=["spread", "total", "score_home", "score_away"]).copy()
    d["date"] = pd.to_datetime(d.date)
    d = d.sort_values("date").reset_index(drop=True)
    d = d.join(rest_days(d, "home", "away", "date", cap=7))
    exp = np.where(d.whos_favored == "home", d.spread, -d.spread)
    d["res"] = (d.score_home - d.score_away) - exp
    d["tot_res"] = d.score_home + d.score_away - d.total
    # 3 games in 4 nights: count team games in the previous 3 days
    long = pd.concat([d[["date", "home"]].rename(columns={"home": "team"}).assign(side="h", i=d.index), d[["date", "away"]].rename(columns={"away": "team"}).assign(side="a", i=d.index)]).sort_values(["team", "date"])
    long["g3"] = long.groupby("team").date.transform(lambda s: s.diff().dt.days.le(1).astype(float).rolling(2, min_periods=1).sum().shift(0))
    g3 = long.pivot_table(index="i", columns="side", values="g3")
    X = pd.DataFrame({"denver_home": (d.home == "den").astype(float), "utah_home": (d.home == "utah").astype(float), "road_b2b": (d.rest_a <= 1).astype(float),
                      "home_b2b": (d.rest_h <= 1).astype(float), "road_3in4": (g3["a"] >= 2).astype(float), "home_3in4": (g3["h"] >= 2).astype(float),
                      "road_b2b_at_altitude": ((d.rest_a <= 1) & d.home.isin(["den", "utah"])).astype(float)})
    train = (d.season <= 2018).values
    return {"ats_resid": test_family(d.res.values, X, train, "ats"), "total_resid": test_family(d.tot_res.values, X[["denver_home", "utah_home", "road_b2b", "home_b2b"]], train, "tot"), "n": len(d)}


if __name__ == "__main__":
    out = {"soccer": soccer(), "nfl": nfl(), "nba": nba()}
    OUT.write_text(json.dumps(out, indent=1))
    for sport, blocks in out.items():
        print(f"\n===== {sport.upper()} (n={blocks['n']:,}) =====")
        for bname, fam in blocks.items():
            if bname == "n":
                continue
            print(f" [{bname}]")
            for k, r in fam.items():
                print(f"   {k:<24} beta {r['beta']:+.3f} (t={r['beta']/r['se']:+.1f}) p_holm {r['p_holm']:.3f} | test beta {r['beta_test']:+.3f} p {r['p_test']:.3f} | {'ACCEPTED final %+.3f' % r['beta_final'] if r['accepted'] else 'not supported  CI[%+.2f,%+.2f]' % tuple(r['ci95'])}")
