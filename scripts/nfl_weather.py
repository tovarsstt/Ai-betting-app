#!/usr/bin/env python3
"""nfl_weather.py — weather/roof layer for the NFL drive sim (the sim never saw wind, rain or a roof before 2026-11-12).

  python3 scripts/nfl_weather.py fit                 refit from /tmp/kg/nflverse/pbp_2023..2026 -> data/nfl_weather_effect.json (with out-of-sample check)
  python3 scripts/nfl_weather.py game AWAY@HOME      tonight's forecast (Open-Meteo at the ESPN venue) and the total shift the sim will apply

Measured on 2023-26 regular-season games (target = real total minus the two teams' season scoring averages, so team strength is out of it):
wind and precipitation lower totals outdoors, a roof raises them. The shift is applied to the simulated games by exponential tilt on the total
(same mechanism as nfl_slate_box.tilt), after shrinking the fitted effect (SHRINK) because the estimates are only ~2.5-3 standard errors from zero.
It moves the TOTAL only; it is not evidence of an edge against a line that already prices the forecast.
"""
from __future__ import annotations
import json, sys, argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
EFFECT = ROOT / "data" / "nfl_weather_effect.json"
NFLV = Path("/tmp/kg/nflverse")
SHRINK = 0.7
CAP = 6.0
WET = "rain|shower|drizzle|snow|sleet|storm"


def _games(years=(2023, 2024, 2025, 2026)):
    import pandas as pd
    cols = ["game_id", "season", "season_type", "home_team", "away_team", "total_home_score", "total_away_score", "total_line", "wind", "roof", "weather"]
    fr = []
    for y in years:
        f = NFLV / f"pbp_{y}.csv.gz"
        if not f.exists(): continue
        d = pd.read_csv(f, usecols=cols, low_memory=False, compression="gzip"); d = d[d.season_type == "REG"]
        fr.append(d.groupby("game_id").agg(season=("season", "first"), home=("home_team", "first"), away=("away_team", "first"), hs=("total_home_score", "max"), as_=("total_away_score", "max"),
                                           tl=("total_line", "first"), wind=("wind", "first"), roof=("roof", "first"), weather=("weather", "first")).reset_index())
    G = pd.concat(fr); G["tot"] = G.hs + G.as_
    long = pd.concat([G.rename(columns={"home": "t", "hs": "pf", "as_": "pa"})[["season", "t", "pf", "pa"]], G.rename(columns={"away": "t", "as_": "pf", "hs": "pa"})[["season", "t", "pf", "pa"]]])
    avg = long.groupby(["season", "t"]).agg(pf=("pf", "mean"), pa=("pa", "mean"))
    G["base"] = [(avg.loc[(r.season, r.home)].pf + avg.loc[(r.season, r.away)].pa + avg.loc[(r.season, r.away)].pf + avg.loc[(r.season, r.home)].pa) / 2 for r in G.itertuples()]
    G["res"] = G.tot - G.base
    G["outdoor"] = G.roof.isin(["outdoors", "open"]); G["wet"] = G.weather.astype(str).str.contains(WET, case=False)
    return G


def _ols(X, y):
    b = np.linalg.lstsq(X, y, rcond=None)[0]; r = y - X @ b
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * r.var(ddof=X.shape[1])); return b, se


def fit(verbose=True):
    G = _games(); out = G[G.outdoor & G.wind.notna()]; ind = G[~G.outdoor]
    X = np.c_[np.ones(len(out)), out.wind.values, out.wet.values.astype(float)]
    b, se = _ols(X, out.res.values)
    # out-of-sample: fit 2023-24, apply (shrunk) to 2025-26 outdoor games
    tr, te = out[out.season <= 2024], out[out.season >= 2025]
    bt, _ = _ols(np.c_[np.ones(len(tr)), tr.wind.values, tr.wet.values.astype(float)], tr.res.values)
    pred = SHRINK * (np.c_[np.ones(len(te)), te.wind.values, te.wet.values.astype(float)] @ bt)
    oos = {"n_test": int(len(te)), "rmse_no_weather": float(np.sqrt(np.mean(te.res.values ** 2))), "rmse_with_weather": float(np.sqrt(np.mean((te.res.values - pred) ** 2))),
           "corr_pred_actual": float(np.corrcoef(pred, te.res.values)[0, 1]), "coef_2023_24": [float(x) for x in bt]}
    mk = out.dropna(subset=["tl"]); bm, sem = _ols(np.c_[np.ones(len(mk)), mk.wind.values, mk.wet.values.astype(float)], (mk.tot - mk.tl).values)
    eff = {"built": str(__import__("datetime").date.today()), "n_outdoor": int(len(out)), "n_indoor": int(len(ind)), "intercept": float(b[0]), "wind_per_mph": float(b[1]), "wet": float(b[2]),
           "se": [float(x) for x in se], "indoor": float(ind.res.mean()), "indoor_se": float(ind.res.std() / np.sqrt(len(ind))), "shrink": SHRINK, "cap": CAP, "oos": oos,
           "vs_market_line": {"wind_per_mph": float(bm[1]), "wet": float(bm[2]), "se": [float(x) for x in sem], "note": "residual vs the closing total; not significant = the market already prices most of it"}}
    EFFECT.write_text(json.dumps(eff, indent=1))
    if verbose:
        print(f"outdoor n={len(out)}: total = base {b[0]:+.2f} {b[1]:+.3f}/mph wind {b[2]:+.2f} if rain/snow  (se {se[0]:.2f}, {se[1]:.3f}, {se[2]:.2f}) | indoor {eff['indoor']:+.2f} (se {eff['indoor_se']:.2f}, n={len(ind)})")
        print(f"out-of-sample 2025-26 (n={oos['n_test']}): RMSE {oos['rmse_no_weather']:.2f} -> {oos['rmse_with_weather']:.2f} with weather, corr(pred, actual) {oos['corr_pred_actual']:+.3f}")
        print(f"vs closing total: wind {bm[1]:+.3f}/mph (se {sem[1]:.3f}), rain {bm[2]:+.2f} (se {sem[2]:.2f})")
    return eff


def effect():
    return json.loads(EFFECT.read_text()) if EFFECT.exists() else None


def shift_for(indoor: bool, wind_mph: float | None = None, precip_pct: float | None = None) -> float:
    """Expected change of the game total (points) vs an average game, shrunk and capped."""
    e = effect()
    if not e: return 0.0
    if indoor: raw = e["indoor"]
    elif wind_mph is None: return 0.0
    else: raw = e["intercept"] + e["wind_per_mph"] * float(wind_mph) + e["wet"] * min(max((precip_pct or 0) / 100.0, 0.0), 1.0)
    return float(np.clip(e["shrink"] * raw, -e["cap"], e["cap"]))


def game_shift(event_id: str) -> dict:
    """Forecast at the ESPN venue for this event -> {'shift','indoor','wind_mph','precip_pct','temp_f'}; shift 0 when nothing is known."""
    import urllib.request
    import game_weather as gw
    d = json.load(urllib.request.urlopen(urllib.request.Request(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"), timeout=25))
    venue = d["gameInfo"]["venue"]; ko = d["header"]["competitions"][0]["date"]
    w = gw.game_weather(venue, ko); wx = w.get("weather") or {}
    out = {"venue": w.get("name"), "indoor": bool(w.get("indoor")), "wind_mph": wx.get("wind_mph"), "precip_pct": wx.get("precip_pct"), "temp_f": wx.get("temp_f")}
    out["shift"] = shift_for(out["indoor"], out["wind_mph"], out["precip_pct"])
    return out


def tilt_total(X: np.ndarray, shift: float, seed: int = 778) -> np.ndarray:
    """Re-weight simulated games (exponential tilt on the total) so the mean total moves by `shift`; rows are resampled so every stat column stays consistent."""
    if abs(shift) < 0.05: return X
    T = X[:, 0] + X[:, 1]; Tc = T - T.mean(); lo, hi = -0.5, 0.5
    for _ in range(60):
        lam = (lo + hi) / 2; w = np.exp(lam * Tc); m = float((w * Tc).sum() / w.sum()); lo, hi = (lam, hi) if m < shift else (lo, lam)
    w = np.exp(lam * Tc); w /= w.sum()
    return X[np.random.default_rng(seed).choice(len(X), size=len(X), p=w)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fit"); g = sub.add_parser("game"); g.add_argument("game")
    a = ap.parse_args()
    if a.cmd == "fit": fit()
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        import nfl_gameday as G
        sb = G.scoreboard(); print(json.dumps(game_shift(sb[a.game]["id"]), indent=1))
