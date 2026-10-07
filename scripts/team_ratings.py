#!/usr/bin/env python3
"""
team_ratings.py — offence / defence / venue / weather ratings for ANY league, tested against that league's closing line.

Model (per sport, refit monthly, time-decayed ridge — a hierarchical-shrinkage model: every team effect is pulled to 0):
    score_home = c + hfa [+ h_i (team-specific venue/home edge)] + o_home - d_away [+ context]
    score_away = c            + o_away - d_home
  o_i = offence, d_i = defence (higher = concedes less), h_i = team-specific home advantage (stadium, altitude,
  surface, crowd all land here), context = weather (NFL wind/cold/dome) on the total. Pace appears as the sum
  o+d: a high-total team raises both its own and its opponents' scores.

The ONLY question that matters: does model - closing line predict (result - closing line)?  slope 0 = the line
already contains everything the ratings know; slope > 0 = information beyond the price.  Out-of-sample, monthly
walk-forward, last 40% of games.  Also reports MSE of line / model / 50-50 blend.
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
sig = lambda x: 1 / (1 + np.exp(-x))


# ── data per sport: date, home, away, hs, as, line_margin (expected home margin), line_total, ctx ──
def nfl() -> pd.DataFrame:
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    teams = pd.read_csv(KG / "nfl_spreadspoke/nfl_teams.csv")
    idmap = dict(zip(teams.team_name, teams.team_id))
    d = d[(d.schedule_season >= 1990) & d.spread_favorite.notna() & d.score_home.notna() & (d.team_favorite_id != "PICK") & d.team_favorite_id.notna()].copy()
    hf = d.team_favorite_id == d.team_home.map(idmap)
    indoor = d.weather_detail.fillna("").str.contains("indoor|retractable \\(closed", case=False) | d.stadium.fillna("").str.contains("dome", case=False)
    wind = pd.to_numeric(d.weather_wind_mph, errors="coerce").where(~indoor, 0.0)
    temp = pd.to_numeric(d.weather_temperature, errors="coerce").where(~indoor, 70.0)
    out = pd.DataFrame({"date": pd.to_datetime(d.schedule_date, format="%m/%d/%Y"), "home": d.team_home, "away": d.team_away, "hs": d.score_home, "as_": d.score_away,
                        "line_margin": np.where(hf, -d.spread_favorite, d.spread_favorite), "line_total": pd.to_numeric(d.over_under_line, errors="coerce"),
                        "wind_sig": sig(0.25 * (wind - 15.0)).fillna(0.0), "cold_sig": sig(-0.2 * (temp - 28.0)).fillna(0.0), "neutral": d.stadium_neutral.astype(str).str.upper().eq("TRUE").astype(float)})
    return out.dropna(subset=["line_total"]).sort_values("date").reset_index(drop=True)


def nba() -> pd.DataFrame:
    d = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
    d = d[d.regular == True].dropna(subset=["spread", "total", "score_home", "score_away"]).copy()
    exp = np.where(d.whos_favored == "home", d.spread, -d.spread)
    return pd.DataFrame({"date": pd.to_datetime(d.date), "home": d.home, "away": d.away, "hs": d.score_home, "as_": d.score_away, "line_margin": exp, "line_total": d.total}).sort_values("date").reset_index(drop=True)


def soccer_league(code: str) -> pd.DataFrame:
    fr = [pd.read_csv(f, encoding="latin1", on_bad_lines="skip", low_memory=False) for f in sorted((KG / "ext/fd").glob(f"{code}_*.csv"))]
    s = pd.concat(fr, ignore_index=True).dropna(subset=["FTHG", "FTAG", "AHCh", "PC>2.5", "PC<2.5"]).copy()
    po, pu = 1 / s["PC>2.5"], 1 / s["PC<2.5"]
    grid = np.linspace(0.4, 7.0, 4000)
    lam = np.interp((po / (po + pu)).clip(0.03, 0.97).values, stats.poisson.sf(2, grid), grid)
    return pd.DataFrame({"date": pd.to_datetime(s.Date, dayfirst=True, errors="coerce"), "home": s.HomeTeam, "away": s.AwayTeam, "hs": s.FTHG, "as_": s.FTAG,
                         "line_margin": -s.AHCh, "line_total": lam}).dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


# ── rating fit ──────────────────────────────────────────────────────────────────────
def fit(train: pd.DataFrame, teams: list, now: pd.Timestamp, half_life_days: float, lam: float, lam_h: float, venue: bool, weather: bool):
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    n = len(train)
    age = (now - train.date).dt.days.values
    w = 0.5 ** (age / half_life_days)
    # two equations per game, parameters: c, hfa, o[T], d[T], (h[T]), (wind, cold coefficients on both scores)
    P = 2 + 2 * T + (T if venue else 0) + (2 if weather else 0)
    X = np.zeros((2 * n, P))
    y = np.concatenate([train.hs.values, train.as_.values]).astype(float)
    ih, ia = train.home.map(idx).values, train.away.map(idx).values
    r = np.arange(n)
    X[:, 0] = 1
    X[r, 1] = 1                                      # home equation carries hfa
    X[r, 2 + ih] = 1                                 # o_home
    X[r, 2 + T + ia] = -1                            # -d_away
    X[n + r, 2 + ia] = 1                             # o_away
    X[n + r, 2 + T + ih] = -1                        # -d_home
    k = 2 + 2 * T
    if venue:
        X[r, k + ih] = 1
        k += T
    if weather:
        wsg, csg = train.wind_sig.values, train.cold_sig.values
        X[:, k], X[:, k + 1] = np.concatenate([wsg, wsg]), np.concatenate([csg, csg])
    ww = np.concatenate([w, w])
    reg = np.zeros(P)
    reg[2:2 + 2 * T] = lam
    if venue:
        reg[2 + 2 * T:2 + 2 * T + T] = lam_h
    A = X.T @ (X * ww[:, None]) + np.diag(reg + 1e-9)
    return np.linalg.solve(A, X.T @ (ww * y)), idx, T


def predict(beta, idx, T, g: pd.DataFrame, venue: bool, weather: bool):
    ih = g.home.map(idx).values
    ia = g.away.map(idx).values
    ok = ~(pd.isna(ih) | pd.isna(ia))
    ih2, ia2 = np.where(ok, ih, 0).astype(int), np.where(ok, ia, 0).astype(int)
    c, hfa, o, d = beta[0], beta[1], beta[2:2 + T], beta[2 + T:2 + 2 * T]
    k = 2 + 2 * T
    hv = beta[k:k + T][ih2] if venue else 0.0
    ctx = 0.0
    if weather:
        kk = k + (T if venue else 0)
        ctx = beta[kk] * g.wind_sig.values + beta[kk + 1] * g.cold_sig.values
    sh = c + hfa + hv + o[ih2] - d[ia2] + ctx
    sa = c + o[ia2] - d[ih2] + ctx
    return np.where(ok, sh - sa, np.nan), np.where(ok, sh + sa, np.nan)


def walk_forward(df: pd.DataFrame, half_life: float, lam: float, lam_h: float, venue: bool, weather: bool, test_frac: float = 0.4, step_days: int = 28) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    cut = df.date.iloc[int(len(df) * (1 - test_frac))]
    teams = sorted(set(df.home) | set(df.away))
    out = []
    t0 = cut
    while t0 <= df.date.max():
        t1 = t0 + pd.Timedelta(days=step_days)
        tr = df[(df.date < t0) & (df.date >= t0 - pd.Timedelta(days=int(half_life * 5)))]
        te = df[(df.date >= t0) & (df.date < t1)]
        if len(tr) > 150 and len(te):
            beta, idx, T = fit(tr, teams, t0, half_life, lam, lam_h, venue, weather)
            pm, pt = predict(beta, idx, T, te, venue, weather)
            out.append(te.assign(m_model=pm, t_model=pt))
        t0 = t1
    return pd.concat(out)


def evaluate(r: pd.DataFrame, name: str) -> dict:
    r = r.dropna(subset=["m_model", "line_margin"])
    res = {"n": len(r)}
    for what, line, mod, act in (("margin", r.line_margin.values, r.m_model.values, (r.hs - r.as_).values), ("total", r.line_total.values, r.t_model.values, (r.hs + r.as_).values)):
        ok = ~np.isnan(line) & ~np.isnan(mod)
        line, mod, act = line[ok], mod[ok], act[ok]
        m = sm.OLS(act - line, sm.add_constant(mod - line)).fit(cov_type="HC1")
        res[what] = {"mse_line": float(np.mean((act - line) ** 2)), "mse_model": float(np.mean((act - mod) ** 2)), "mse_blend": float(np.mean((act - (line + mod) / 2) ** 2)),
                     "slope_resid_on_model_minus_line": float(m.params[1]), "se": float(m.bse[1]), "t": float(m.tvalues[1]), "p": float(m.pvalues[1]), "sd_model_minus_line": float(np.std(mod - line))}
    return res


def tune_and_run(df: pd.DataFrame, name: str, grid_hl, grid_lam, venue_opts=(False, True), weather=False) -> dict:
    best = None
    for hl in grid_hl:
        for lam in grid_lam:
            r = walk_forward(df, hl, lam, lam * 4, False, False, test_frac=0.4)
            e = evaluate(r, name)["margin"]["mse_model"]
            if best is None or e < best[0]:
                best = (e, hl, lam)
    _, hl, lam = best
    out = {"half_life_days": hl, "ridge": lam, "variants": {}}
    for venue in venue_opts:
        for wx in ([False, True] if weather else [False]):
            r = walk_forward(df, hl, lam, lam * 4, venue, wx)
            out["variants"][f"venue={venue},weather={wx}"] = evaluate(r, name)
    return out


if __name__ == "__main__":
    res = {}
    specs = {"nfl": (nfl(), (365, 730), (3.0, 10.0, 30.0), True), "nba": (nba(), (120, 240, 480), (3.0, 10.0, 30.0), False)}
    for code in ("E0", "SP1", "D1", "I1", "F1"):
        specs[f"soccer_{code}"] = (soccer_league(code), (240, 480), (3.0, 10.0, 30.0), False)
    for name, (df, hls, lams, wx) in specs.items():
        res[name] = tune_and_run(df, name, hls, lams, weather=wx)
        r = res[name]
        print(f"\n== {name} (half-life {r['half_life_days']}d, ridge {r['ridge']}) ==")
        for v, e in r["variants"].items():
            m, t = e["margin"], e["total"]
            print(f"  [{v}] n={e['n']:,} MARGIN mse line {m['mse_line']:.2f} model {m['mse_model']:.2f} blend {m['mse_blend']:.2f} | slope {m['slope_resid_on_model_minus_line']:+.3f} (t={m['t']:+.2f}) "
                  f"|| TOTAL mse line {t['mse_line']:.2f} model {t['mse_model']:.2f} blend {t['mse_blend']:.2f} | slope {t['slope_resid_on_model_minus_line']:+.3f} (t={t['t']:+.2f})")
    (DATA / "team_ratings_results.json").write_text(json.dumps(res, indent=1, default=float))
