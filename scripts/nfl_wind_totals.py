#!/usr/bin/env python3
"""
nfl_wind_totals.py — retrain how wind moves NFL totals vs the closing line, on the RECORDED-wind scale, choosing the functional form OUT OF SAMPLE.

Candidates for E[total - closing line | recorded wind]: linear, hinge max(0, w - t) for t in {6, 8, 10, 12, 15}, sigmoid(0.25 (w - 15)).
Walk-forward by season (train on all earlier seasons >= 1990, predict the next season), score = MSE of (total - line); a form must beat
"no wind effect" (predict the training mean). The winner is stored in data/nfl_wind_totals_model.json and used by engine_all.analyze_game().
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

KG = Path("/tmp/kg")
DATA = Path(__file__).parent.parent / "data"


def load() -> pd.DataFrame:
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    d = d[(d.schedule_season >= 1990) & d.over_under_line.notna() & d.score_home.notna()].copy()
    d["ou"] = pd.to_numeric(d.over_under_line, errors="coerce")
    indoor = d.weather_detail.fillna("").str.contains("indoor|retractable \\(closed", case=False) | d.stadium.fillna("").str.contains("dome", case=False)
    d["wind"] = pd.to_numeric(d.weather_wind_mph, errors="coerce")
    d = d[~indoor].dropna(subset=["wind", "ou"])
    d["res"] = d.score_home + d.score_away - d.ou
    return d[["schedule_season", "wind", "res"]].rename(columns={"schedule_season": "season"}).reset_index(drop=True)


FORMS = {"linear": lambda w: w, "hinge6": lambda w: np.maximum(0, w - 6), "hinge8": lambda w: np.maximum(0, w - 8), "hinge10": lambda w: np.maximum(0, w - 10),
         "hinge12": lambda w: np.maximum(0, w - 12), "hinge15": lambda w: np.maximum(0, w - 15), "sigmoid15": lambda w: 1 / (1 + np.exp(-0.25 * (w - 15)))}


def walk_forward(d: pd.DataFrame, first_test: int = 2005) -> dict:
    out = {k: [] for k in FORMS}
    base = []
    for s in range(first_test, int(d.season.max()) + 1):
        tr, te = d[d.season < s], d[d.season == s]
        if len(te) < 30:
            continue
        base.append(np.mean((te.res - tr.res.mean()) ** 2))
        for k, f in FORMS.items():
            m = sm.OLS(tr.res, sm.add_constant(f(tr.wind.values))).fit()
            pred = m.params.iloc[0] + m.params.iloc[1] * f(te.wind.values)
            out[k].append(np.mean((te.res - pred) ** 2))
    n_seasons = len(base)
    return {k: {"mse_gain_pct": float(100 * (np.mean(base) - np.mean(v)) / np.mean(base)), "seasons_better_than_null": int(sum(a < b for a, b in zip(v, base))), "n_seasons": n_seasons} for k, v in out.items()}


def main():
    d = load()
    res = walk_forward(d)
    print(f"{len(d):,} outdoor games with recorded wind, walk-forward from 2005:")
    for k, v in sorted(res.items(), key=lambda kv: -kv[1]["mse_gain_pct"]):
        print(f"  {k:<10} held-out MSE gain {v['mse_gain_pct']:+.3f}%   beats the no-wind baseline in {v['seasons_better_than_null']}/{v['n_seasons']} seasons")
    best = max(res, key=lambda k: res[k]["mse_gain_pct"])
    f = FORMS[best]
    m = sm.OLS(d.res, sm.add_constant(f(d.wind.values))).fit(cov_type="HC1")
    recent = d[d.season >= 2017]
    mr = sm.OLS(recent.res, sm.add_constant(f(recent.wind.values))).fit(cov_type="HC1")
    model = {"form": best, "intercept": float(m.params.iloc[0]), "coef_pts_per_unit": float(m.params.iloc[1]), "se": float(m.bse.iloc[1]), "p": float(m.pvalues.iloc[1]),
             "coef_2017_plus": float(mr.params.iloc[1]), "p_2017_plus": float(mr.pvalues.iloc[1]), "n": int(len(d)), "walk_forward": res,
             "scale": "RECORDED wind (stadium/NFL weather feed). Convert Open-Meteo with recorded ~= 2.41 + 0.74 * open_meteo (data/wind_scale_map.json)"}
    (DATA / "nfl_wind_totals_model.json").write_text(json.dumps(model, indent=1))
    print(f"\nBEST: {best}: {model['coef_pts_per_unit']:+.3f} pts per unit (se {model['se']:.3f}, p={model['p']:.4f}); since 2017: {model['coef_2017_plus']:+.3f} (p={model['p_2017_plus']:.3f})")
    for w in (5, 10, 15, 20, 25):
        print(f"   recorded wind {w:>2} mph -> total shift {model['coef_pts_per_unit'] * float(f(np.array(w, float))):+.2f} pts")


if __name__ == "__main__":
    main()
