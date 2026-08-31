"""game_weather.py — venue + weather context for outdoor games (NFL, CFB).

Wind, cold and precipitation move passing/kicking totals in ways a Poisson or
sharp-anchor model never sees — this is a CONTEXT flag, not an invented
probability shift (soccer_skill.md / market_validation precedent: real
numbers cited, never fabricated adjustments). A dome short-circuits the whole
pipeline — no geocode, no forecast call, no ambiguity.

Sources (both free, no key):
  ESPN scoreboard `competitions[].venue`  -> city/state/indoor flag
  Open-Meteo geocoding + forecast API     -> lat/lon -> hourly temp/wind/precip

CLI: python3 scripts/game_weather.py "Seattle" "WA" --kickoff 2026-09-07T18:00Z
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15

HIGH_WIND_MPH = 20
MODERATE_WIND_MPH = 15
COLD_F = 25
FREEZING_F = 32
HEAVY_PRECIP_PCT = 60
MODERATE_PRECIP_PCT = 30


def venue_from_espn(venue: dict) -> dict:
    """Extract city/state/indoor from an ESPN `competitions[].venue` block."""
    address = venue["address"]
    return {
        "name": venue.get("fullName"),
        "city": address["city"],
        "state": address.get("state"),
        "indoor": bool(venue.get("indoor", False)),
    }


def geocode(city: str, state: str | None = None) -> tuple[float, float] | None:
    """City/state -> (lat, lon) via Open-Meteo geocoding. None on no match."""
    query = f"{city}, {state}" if state else city
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode({'name': query, 'count': 1, 'format': 'json'})}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            doc = json.load(r)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    results = doc.get("results") or []
    if not results:
        return None
    return results[0]["latitude"], results[0]["longitude"]


def fetch_hourly(lat: float, lon: float, forecast_days: int = 10) -> dict | None:
    """Raw Open-Meteo hourly block for a location."""
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,wind_speed_10m,precipitation_probability",
        "forecast_days": forecast_days,
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    }
    url = f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return json.load(r).get("hourly")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def weather_from_forecast(hourly: dict | None, kickoff_iso: str) -> dict | None:
    """Nearest-hour temp/wind/precip to kickoff. None if out of window or no data."""
    if not hourly:
        return None
    kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    times = hourly.get("time") or []
    best_i, best_diff = None, None
    for i, t in enumerate(times):
        ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        diff = abs((ts - kickoff).total_seconds())
        if best_diff is None or diff < best_diff:
            best_i, best_diff = i, diff
    if best_i is None or best_diff > 6 * 3600:  # forecast window exhausted
        return None
    return {
        "temp_f": hourly["temperature_2m"][best_i],
        "wind_mph": hourly["wind_speed_10m"][best_i],
        "precip_pct": hourly["precipitation_probability"][best_i],
    }


def classify_impact(weather: dict) -> dict:
    """Qualitative flag for the pick-report layer — never a probability shift."""
    if weather.get("indoor"):
        return {"level": "NONE", "note": "Dome/indoor — no weather impact."}

    wind, temp, precip = weather.get("wind_mph"), weather.get("temp_f"), weather.get("precip_pct")
    if wind is None or temp is None or precip is None:
        return {"level": "UNKNOWN", "note": "No forecast available for kickoff — do not assume calm."}

    flags = []
    level = "NONE"
    if wind >= HIGH_WIND_MPH:
        flags.append(f"wind {wind:.0f}mph — kicking range and deep passing degrade")
        level = "HIGH"
    elif wind >= MODERATE_WIND_MPH:
        flags.append(f"wind {wind:.0f}mph — mild passing/kicking headwind")
        level = "MODERATE"
    if temp <= COLD_F:
        flags.append(f"cold {temp:.0f}F — ball handling and kicking distance drop")
        level = "HIGH"
    elif temp <= FREEZING_F and level == "NONE":
        level = "MODERATE"
        flags.append(f"cold {temp:.0f}F — near-freezing, minor grip/kicking effect")
    if precip >= HEAVY_PRECIP_PCT:
        flags.append(f"precip {precip:.0f}% — fumble/turnover risk up, favors Under")
        level = "HIGH"
    elif precip >= MODERATE_PRECIP_PCT and level == "NONE":
        level = "MODERATE"
        flags.append(f"precip {precip:.0f}% — some ball-security risk")

    note = "; ".join(flags) if flags else "Calm conditions — no material weather edge."
    return {"level": level, "note": note}


def game_weather(venue: dict, kickoff_iso: str) -> dict:
    """Full pipeline: ESPN venue -> geocode -> forecast -> impact classification."""
    v = venue_from_espn(venue)
    if v["indoor"]:
        impact = classify_impact({"indoor": True})
        return {**v, "weather": None, "impact": impact}
    coords = geocode(v["city"], v["state"])
    weather = None
    if coords:
        hourly = fetch_hourly(*coords)
        weather = weather_from_forecast(hourly, kickoff_iso)
    impact_input = {"indoor": False, **(weather or {})}
    if weather is None:
        impact_input = {"indoor": False, "wind_mph": None, "temp_f": None, "precip_pct": None}
    return {**v, "weather": weather, "impact": classify_impact(impact_input)}


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("city")
    ap.add_argument("state", nargs="?", default=None)
    ap.add_argument("--kickoff", required=True)
    ap.add_argument("--indoor", action="store_true")
    args = ap.parse_args()
    result = game_weather(
        {"fullName": None, "address": {"city": args.city, "state": args.state}, "indoor": args.indoor},
        args.kickoff,
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    _main()
