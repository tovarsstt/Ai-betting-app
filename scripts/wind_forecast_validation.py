#!/usr/bin/env python3
"""
wind_forecast_validation.py — the NFL wind->Under rule was validated with the wind RECORDED at the game. A bettor only has the FORECAST.
Open-Meteo's historical-forecast API (model forecasts as issued, since 2022) gives the kickoff-hour forecast; the archive gives what happened.
Outdoor games 2022-2025 (closing totals from spreadspoke / ESPN closing files), Under at -110, tested at several wind thresholds for both.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import qb_effects_nfl as Q  # noqa: E402

CITY = {"Arizona Cardinals": "Glendale", "Atlanta Falcons": "Atlanta", "Baltimore Ravens": "Baltimore", "Buffalo Bills": "Orchard Park", "Carolina Panthers": "Charlotte",
        "Chicago Bears": "Chicago", "Cincinnati Bengals": "Cincinnati", "Cleveland Browns": "Cleveland", "Dallas Cowboys": "Arlington", "Denver Broncos": "Denver",
        "Detroit Lions": "Detroit", "Green Bay Packers": "Green Bay", "Houston Texans": "Houston", "Indianapolis Colts": "Indianapolis", "Jacksonville Jaguars": "Jacksonville",
        "Kansas City Chiefs": "Kansas City", "Las Vegas Raiders": "Las Vegas", "Los Angeles Chargers": "Inglewood", "Los Angeles Rams": "Inglewood", "Miami Dolphins": "Miami Gardens",
        "Minnesota Vikings": "Minneapolis", "New England Patriots": "Foxborough", "New Orleans Saints": "New Orleans", "New York Giants": "East Rutherford", "New York Jets": "East Rutherford",
        "Philadelphia Eagles": "Philadelphia", "Pittsburgh Steelers": "Pittsburgh", "San Francisco 49ers": "Santa Clara", "Seattle Seahawks": "Seattle", "Tampa Bay Buccaneers": "Tampa",
        "Tennessee Titans": "Nashville", "Washington Commanders": "Landover", "Washington Football Team": "Landover", "Oakland Raiders": "Oakland", "San Diego Chargers": "San Diego",
        "St. Louis Rams": "St. Louis"}
DOMES = {"Arizona Cardinals", "Atlanta Falcons", "Dallas Cowboys", "Detroit Lions", "Houston Texans", "Indianapolis Colts", "Las Vegas Raiders", "Los Angeles Chargers",
         "Los Angeles Rams", "Minnesota Vikings", "New Orleans Saints"}
_geo: dict = {}


def j(u):
    return json.load(urllib.request.urlopen(u, timeout=40))


def geo(city):
    if city not in _geo:
        r = j("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=5&country_code=US" % urllib.parse.quote(city))["results"][0]
        _geo[city] = (r["latitude"], r["longitude"])
    return _geo[city]


def wind(api: str, team: str, utc: pd.Timestamp):
    try:
        lat, lon = geo(CITY[team])
        day = utc.strftime("%Y-%m-%d")
        u = f"https://{api}.open-meteo.com/v1/{'archive' if api.startswith('archive') else 'forecast'}?latitude={lat}&longitude={lon}&start_date={day}&end_date={day}&hourly=wind_speed_10m&wind_speed_unit=mph&timezone=UTC"
        w = j(u)["hourly"]
        i = [k for k, x in enumerate(w["time"]) if x[:13] == utc.strftime("%Y-%m-%dT%H")]
        return w["wind_speed_10m"][i[0]] if i else None
    except Exception:
        return None


def main():
    g = Q.games()
    g = g[(g.schedule_season >= 2022) & g.ou.notna() & ~g.hn.isin(DOMES) & g.hn.isin(CITY)].copy()
    g["total"] = g.hp + g.ap
    g = g[g.total != g.ou].reset_index(drop=True)
    print(f"{len(g)} outdoor games 2022-25 with closing totals", flush=True)
    for city in {CITY[t] for t in g.hn.unique()}:
        geo(city)
    def both(row):
        t = pd.Timestamp(row.utc).tz_convert("UTC") if pd.Timestamp(row.utc).tzinfo else pd.Timestamp(row.utc, tz="UTC")
        return wind("archive-api", row.hn, t), wind("historical-forecast-api", row.hn, t)
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(both, g.itertuples()))
    g["w_act"], g["w_fc"] = [r[0] for r in res], [r[1] for r in res]
    g = g.dropna(subset=["w_act", "w_fc"])
    g["under"] = (g.total < g.ou).astype(float)
    print(f"{len(g)} games with both wind numbers | corr(actual, forecast) = {np.corrcoef(g.w_act, g.w_fc)[0, 1]:.2f} | forecast bias {np.mean(g.w_fc - g.w_act):+.1f} mph, MAE {np.mean(np.abs(g.w_fc - g.w_act)):.1f} mph")
    out = {"n": len(g), "corr": float(np.corrcoef(g.w_act, g.w_fc)[0, 1])}
    for thr in (10, 12, 15, 18):
        for col, nm in (("w_act", "ACTUAL"), ("w_fc", "FORECAST")):
            x = g[g[col] >= thr]
            if len(x) < 20:
                continue
            k, n = int(x.under.sum()), len(x)
            p = stats.binomtest(k, n, 0.5238, alternative="greater").pvalue
            roi = (k / n * (100 / 110) - (1 - k / n)) * 100
            print(f"  wind>={thr:>2} mph {nm:<8} n={n:4d} Under {k / n * 100:5.1f}% ROI@-110 {roi:+5.1f}% one-sided p={p:.3f}")
            out[f"{nm}_{thr}"] = {"n": n, "under": k / n, "roi": roi, "p": p}
    Path(__file__).parent.parent.joinpath("data", "wind_forecast_validation.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
