#!/usr/bin/env python3
"""
heuristic_calibration.py — which context heuristics does REAL data justify?

For every heuristic the engine could inject (wind/rain/cold on scoring, rest / back-to-back on
margins and totals) regress the CLOSING-LINE RESIDUAL — actual minus what the market already
priced — on the heuristic, fit on the earlier seasons and judged on the later ones. A heuristic
that doesn't explain the residual is already in the price; injecting it would double count.

  NFL  spreadspoke (closing spread / total, temp, wind, humidity, roof, weather) 1979-2025
  NBA  closing spread / total 2008-2026, rest days from the schedule itself
  NHL  closing total 2004-2025 with the dataset's own rest_days

Only coefficients that pass (|t|>=2.6 on train AND lower held-out MSE AND same sign on test) are
written to data/heuristic_coefficients.json as 'calibrated'; everything else stays 'null' and the
engine treats it as 0 (rule 13: an effect nobody measured is an effect that doesn't exist).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "heuristic_coefficients.json"
KG = Path("/tmp/kg")


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def ols(y, X, train, test):
    """fit on train; return beta/se/t on train, held-out MSE with vs without X, test beta sign."""
    Xtr, ytr, Xte, yte = X[train], y[train], X[test], y[test]
    m = sm.OLS(ytr, sm.add_constant(Xtr)).fit(cov_type="HC1")
    pred = m.predict(sm.add_constant(Xte, has_constant="add"))
    base = ytr.mean()
    mse_with, mse_base = float(np.mean((yte - pred) ** 2)), float(np.mean((yte - base) ** 2))
    mt = sm.OLS(yte, sm.add_constant(Xte)).fit(cov_type="HC1")
    return {"beta": m.params[1:].tolist(), "se": m.bse[1:].tolist(), "t": m.tvalues[1:].tolist(),
            "test_beta": mt.params[1:].tolist(), "test_t": mt.tvalues[1:].tolist(),
            "mse_gain_pct": 100 * (mse_base - mse_with) / mse_base, "n_train": int(train.sum()), "n_test": int(test.sum())}


def nfl():
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    d = d[(d.schedule_season >= 1990) & d.over_under_line.notna()].copy()
    d["over_under_line"] = pd.to_numeric(d.over_under_line, errors="coerce")
    d["total"] = d.score_home + d.score_away
    d["resid"] = d.total - d.over_under_line
    indoor = d.weather_detail.fillna("").str.contains("indoor|retractable \\(closed", case=False) | d.stadium.fillna("").str.contains("dome", case=False)
    wind = pd.to_numeric(d.weather_wind_mph, errors="coerce").where(~indoor, 0.0)
    temp = pd.to_numeric(d.weather_temperature, errors="coerce").where(~indoor, 70.0)
    d["wind_sig"] = sigmoid(0.25 * (wind - 15.0))                 # critical threshold ~15 mph (~24 km/h)
    d["wind_lin"] = wind
    d["cold_sig"] = sigmoid(-0.2 * (temp - 28.0))
    det = d.weather_detail.fillna("").str.lower()
    d["precip"] = det.str.contains("rain|snow").astype(float)
    d = d.dropna(subset=["wind_sig", "cold_sig"])
    train = (d.schedule_season <= 2016).values
    test = ~train
    res = {}
    for name, cols in {"wind_sigmoid": ["wind_sig"], "wind_linear": ["wind_lin"], "cold_sigmoid": ["cold_sig"], "precip": ["precip"],
                       "all_weather": ["wind_sig", "cold_sig", "precip"]}.items():
        r = ols(d.resid.values, d[cols].values, train, test)
        r["mean_total"] = float(d.total.mean())
        res[name] = r
    return res


def _rest_frame(sched: pd.DataFrame) -> pd.DataFrame:
    """sched: date, home, away -> days since each team's previous game (cap 7)."""
    long = pd.concat([sched[["date", "home"]].rename(columns={"home": "team"}).assign(side="home", idx=sched.index),
                      sched[["date", "away"]].rename(columns={"away": "team"}).assign(side="away", idx=sched.index)]).sort_values(["team", "date"])
    long["rest"] = long.groupby("team").date.diff().dt.days.clip(upper=7)
    piv = long.pivot_table(index="idx", columns="side", values="rest")
    return piv.rename(columns={"home": "rest_h", "away": "rest_a"})


def nba():
    d = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
    d = d[d.regular == True].copy()
    d["date"] = pd.to_datetime(d.date)
    d = d.dropna(subset=["spread", "total", "score_home", "score_away"]).reset_index(drop=True)
    d = d.join(_rest_frame(d.rename(columns={"home": "home", "away": "away"})[["date", "home", "away"]]))
    d = d.dropna(subset=["rest_h", "rest_a"])
    exp_home = np.where(d.whos_favored == "home", d.spread, -d.spread)
    d["ats"] = (d.score_home - d.score_away) - exp_home
    d["tot_resid"] = d.score_home + d.score_away - d.total
    d["b2b_h"], d["b2b_a"] = (d.rest_h <= 1).astype(float), (d.rest_a <= 1).astype(float)
    d["rest_diff"] = (d.rest_h.clip(upper=4) - d.rest_a.clip(upper=4))
    train = (d.season <= 2018).values
    test = ~train
    res = {"ats_b2b_home": ols(d.ats.values, d[["b2b_h", "b2b_a"]].values, train, test),
           "ats_rest_diff": ols(d.ats.values, d[["rest_diff"]].values, train, test),
           "total_b2b": ols(d.tot_resid.values, d[["b2b_h", "b2b_a"]].values, train, test)}
    res["_n"] = len(d)
    return res


def nhl():
    d = pd.read_csv(KG / "nhl_hist/nhl_data_extensive.csv", usecols=["game_id", "date", "season", "is_home", "goals_for", "goals_against", "over_under", "rest_days"])
    g = d.groupby("game_id")
    h = d[d.is_home == 1].set_index("game_id")
    a = d[d.is_home == 0].set_index("game_id")
    x = h[["season", "goals_for", "goals_against", "over_under", "rest_days"]].join(a[["rest_days"]], rsuffix="_a", how="inner").dropna()
    x["tot_resid"] = x.goals_for + x.goals_against - x.over_under
    x["b2b_h"], x["b2b_a"] = (x.rest_days <= 1).astype(float), (x.rest_days_a <= 1).astype(float)
    x = x[x.over_under > 3]
    train = (x.season <= 2018).values
    test = ~train
    return {"total_b2b": ols(x.tot_resid.values, x[["b2b_h", "b2b_a"]].values, train, test), "_n": len(x)}


def passes(r: dict, idx: int = 0) -> bool:
    return abs(r["t"][idx]) >= 2.6 and r["mse_gain_pct"] > 0 and np.sign(r["beta"][idx]) == np.sign(r["test_beta"][idx])


if __name__ == "__main__":
    out = {"nfl": nfl(), "nba": nba(), "nhl": nhl()}
    coefs = {}
    for sport, block in out.items():
        print(f"\n== {sport.upper()} ==")
        for k, r in block.items():
            if k.startswith("_"):
                print("  n =", r)
                continue
            ok = passes(r)
            print(f"  {k:<16} beta {np.round(r['beta'], 3).tolist()}  t {np.round(r['t'], 1).tolist()} | test beta {np.round(r['test_beta'], 3).tolist()} t {np.round(r['test_t'], 1).tolist()}"
                  f" | held-out MSE gain {r['mse_gain_pct']:+.3f}%  -> {'CALIBRATED' if ok else 'not supported (already priced / noise)'}")
    w = out["nfl"]["wind_sigmoid"]
    coefs["wind_scoring"] = ({"value": -w["beta"][0] / w["mean_total"], "n": w["n_train"], "n0": 400, "status": "calibrated",
                              "note": "NFL log scoring multiplier per unit sigmoid(0.25*(wind_mph-15)); fit on closing-total residual"}
                             if passes(w) else {"value": 0.0, "status": "uncalibrated", "note": "NFL wind residual not significant out of sample"})
    for name in ("wind_serve_logit", "rain_serve_logit", "wind_sd", "rain_sd", "heat_fatigue", "altitude_fatigue", "press_sd",
                 "birthday_sd", "special_day_sd", "personal_goal_sd"):
        coefs[name] = {"value": 0.0, "status": "uncalibrated", "note": "no outcome data available — effect set to 0 rather than invented"}
    OUT.write_text(json.dumps(coefs, indent=1))
    (DATA / "context_effects_report.json").write_text(json.dumps(out, indent=1, default=float))
    print("\nwrote", OUT)
