#!/usr/bin/env python3
"""
fetch_period_scores.py — real per-period scoring, for quarter/half/OT markets.

Why this exists: the engine could only price FULL-GAME markets. Period markets
(a 1st-quarter spread, a 1st-half total) were refused because the only mechanism
available was an independent-increments proxy — halve the margin, divide sigma by
root two — which is fine for basketball and wrong for football, where game script
couples the periods hard: a team leading by three scores runs the ball and the
4th quarter goes quiet; a team trailing throws and it does not.

Rather than model that coupling, this harvests the REAL thing. ESPN publishes a
`linescores` array per competitor on every finished game — the actual points
scored in each period. `period_model.py` then resamples whole historical games,
which carries the correlation for free because it never takes periods apart.

Output: data/period_scores.json
  {"nfl": {"n_games": 1234, "games": [{"date","home","away","home_periods":[..],
                                       "away_periods":[..],"ot":bool}]}}

Free, no key, no quota. Sends no User-Agent — ESPN's edge refuses spoofed ones.

Run: python3 scripts/fetch_period_scores.py --sport nfl --seasons 2024 2025
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "period_scores.json"

# sport key -> (ESPN path, regulation periods)
SPORTS = {
    "nfl": ("football/nfl", 4),
    "nba": ("basketball/nba", 4),
    "nhl": ("hockey/nhl", 3),
    "wnba": ("basketball/wnba", 4),
}

# Rough season windows so we only ask for days that can have games.
WINDOWS = {
    "nfl": ((9, 1), (2, 15)),
    "nba": ((10, 15), (6, 25)),
    "nhl": ((10, 1), (6, 25)),
    "wnba": ((5, 10), (10, 25)),
}
TIMEOUT = 20


def _get(url: str) -> dict:
    req = urllib.request.Request(url)          # no UA on purpose
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _days(sport: str, season: int) -> list[str]:
    (m1, d1), (m2, d2) = WINDOWS[sport]
    start = date(season, m1, d1)
    end = date(season + 1, m2, d2) if m2 < m1 else date(season, m2, d2)
    out, cur = [], start
    while cur <= end:
        out.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return out


def _scrape_day(path: str, day: str, regulation: int) -> list[dict]:
    try:
        d = _get(f"https://site.api.espn.com/apis/site/v2/sports/{path}"
                 f"/scoreboard?dates={day}&limit=100")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return []
    games = []
    for ev in d.get("events", []):
        st = (ev.get("status") or {}).get("type") or {}
        if not st.get("completed"):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        sides = {}
        for c in comp.get("competitors", []):
            ls = c.get("linescores") or []
            vals = []
            ok = True
            for i in ls:
                try:
                    vals.append(float(i.get("value")))
                except (TypeError, ValueError):
                    ok = False
                    break
            if not ok or not vals:
                continue
            sides[c.get("homeAway")] = {"team": (c.get("team") or {}).get("displayName"),
                                        "periods": vals}
        if "home" not in sides or "away" not in sides:
            continue
        hp, ap = sides["home"]["periods"], sides["away"]["periods"]
        if len(hp) != len(ap) or len(hp) < regulation:
            continue                       # malformed or abandoned
        games.append({
            "date": ev.get("date", "")[:10],
            "home": sides["home"]["team"], "away": sides["away"]["team"],
            "home_periods": hp, "away_periods": ap,
            # Anything beyond regulation is overtime — kept so OT markets can be
            # priced off the real frequency instead of a guess.
            "ot": len(hp) > regulation,
        })
    return games


def harvest(sport: str, seasons: list[int]) -> dict:
    path, regulation = SPORTS[sport]
    days: list[str] = []
    for s in seasons:
        days.extend(_days(sport, s))

    games: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(lambda d: _scrape_day(path, d, regulation), days):
            games.extend(chunk)

    # De-duplicate: the same fixture can appear on two calendar days in UTC.
    seen, uniq = set(), []
    for g in games:
        key = (g["date"], g["home"], g["away"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(g)

    store = {}
    if OUT.exists():
        try:
            store = json.loads(OUT.read_text())
        except (OSError, json.JSONDecodeError):
            store = {}
    prev = {(g["date"], g["home"], g["away"]): g
            for g in (store.get(sport) or {}).get("games", [])}
    for g in uniq:
        prev[(g["date"], g["home"], g["away"])] = g
    merged = sorted(prev.values(), key=lambda g: g["date"])

    store[sport] = {
        "regulation_periods": regulation,
        "n_games": len(merged),
        "ot_rate": round(sum(1 for g in merged if g["ot"]) / len(merged), 4)
        if merged else None,
        "seasons_harvested": sorted(set((store.get(sport) or {}).get(
            "seasons_harvested", []) + seasons)),
        "games": merged,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(store))
    return {k: v for k, v in store[sport].items() if k != "games"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", choices=sorted(SPORTS), default="nfl")
    ap.add_argument("--seasons", type=int, nargs="+", default=[2025])
    a = ap.parse_args()
    print(json.dumps(harvest(a.sport, a.seasons), indent=1))
