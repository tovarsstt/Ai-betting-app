#!/usr/bin/env python3
"""
data_freshness.py — one audit for every sport's data age + season boundaries.

Why: the Badosa fade happened because ONE of tennis's three data files silently
rotted for 17 days. With club soccer, NFL and NBA seasons approaching, the same
trap scales: last-season ratings feeding models at season start look exactly
like fresh data unless something checks. This reads each sport's own embedded
stamp (file mtime as fallback), compares against per-sport staleness budgets
and season windows, and returns a status per sport:

  OK              — inside budget
  STALE           — in season and older than the sport's budget
  OFFSEASON       — sport not in season; age is informational
  SEASON_BOUNDARY — in season (or <30d before start) but the data predates the
                    season start: rosters/promotions/transfers make last
                    season's fit a hazard, not a prior

Wired into edge_api /health so every card build sees it. Pure reads, no network.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# (month, day) season windows; spanning new year = start > end
SEASONS = {
    "mlb": ((3, 20), (11, 5)),
    "nba": ((10, 20), (6, 20)),
    "wnba": ((5, 15), (10, 20)),
    "nfl": ((9, 4), (2, 15)),
    "soccer_club": ((8, 8), (5, 31)),
    "soccer_intl": ((1, 1), (12, 31)),     # internationals run year-round (WC now)
    "tennis": ((1, 1), (11, 25)),
    "volleyball": ((5, 1), (10, 15)),      # VNL + worlds window
    "cricket": ((1, 1), (12, 31)),
    "lmb": ((4, 15), (9, 15)),
}
# max data age in days while IN season
BUDGET = {"mlb": 2, "nba": 4, "wnba": 4, "nfl": 8, "soccer_club": 8,
          "soccer_intl": 21, "tennis": 8, "volleyball": 30, "cricket": 30, "lmb": 3}

# sport -> (file, dotted path to its embedded ISO stamp; None = use file mtime)
SOURCES = {
    "mlb": ("mlb_game_data.json", "meta.fetched_at"),
    "tennis": ("ratings_meta.json", "tennis.updated"),
    "tennis_form": ("tennis_form.json", "built"),
    "tennis_serve": ("tennis_serve.json", "built"),
    "soccer_club": ("soccer/club_ratings.json", "generated_at"),
    "soccer_intl": ("soccer/international_ratings.json", "generated_at"),
    "volleyball": ("volleyball_ratings.json", "meta.fetched_at"),
    "cricket": ("cricket_ratings.json", "meta.fetched_at"),
    "lmb": ("lmb_ratings.json", "meta.fetched_at"),
    "nba": ("all_ratings.json", None),
    "wnba": ("all_ratings.json", None),
    "nfl": ("all_ratings.json", None),
}
# aliases whose season/budget follow another sport
FOLLOWS = {"tennis_form": "tennis", "tennis_serve": "tennis"}


def _dig(doc: dict, dotted: str):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _stamp(path: Path, dotted: str | None):
    if not path.exists():
        return None
    if dotted:
        try:
            v = _dig(json.loads(path.read_text()), dotted)
            if v:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def in_season(sport: str, today: date) -> bool:
    (sm, sd), (em, ed) = SEASONS[sport]
    start, end = (sm, sd), (em, ed)
    t = (today.month, today.day)
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end          # wraps the new year (NBA/NFL)


def season_start(sport: str, today: date) -> date:
    (sm, sd), (em, ed) = SEASONS[sport]
    start = date(today.year, sm, sd)
    if (sm, sd) <= (em, ed):               # same-year season
        return start
    # wrapping season: if we're in the Jan-end tail, the season started last year
    return start if (today.month, today.day) >= (sm, sd) else start.replace(year=today.year - 1)


def status_for(sport: str, stamp: datetime | None, today: date) -> dict:
    key = FOLLOWS.get(sport, sport)
    if stamp is None:
        return {"status": "MISSING", "note": "data file not found"}
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    # Age is measured against the caller's reference date `today`, not the wall
    # clock — otherwise age and the season checks below use two different "now"s,
    # and STALE fires days early (non-deterministic, untestable).
    age = (today - stamp.date()).days
    out = {"stamp": stamp.date().isoformat(), "age_days": age}
    season = in_season(key, today)
    starts = season_start(key, today)
    days_to_start = (starts - today).days
    if not season and days_to_start < 0:      # wrapped sport between seasons:
        starts = starts.replace(year=starts.year + 1)   # next season's start
        days_to_start = (starts - today).days
    if (season or 0 < days_to_start <= 30) and stamp.date() < starts:
        return {**out, "status": "SEASON_BOUNDARY",
                "note": f"data predates {key} season start {starts} — "
                        f"rosters/promotions changed; refit before trusting"}
    if not season:
        return {**out, "status": "OFFSEASON"}
    if age > BUDGET[key]:
        return {**out, "status": "STALE",
                "note": f"{age}d old, budget {BUDGET[key]}d in season — refresh"}
    return {**out, "status": "OK"}


def audit(today: date | None = None) -> dict:
    today = today or date.today()
    report = {}
    for sport, (fname, dotted) in SOURCES.items():
        report[sport] = status_for(sport, _stamp(DATA / fname, dotted), today)
    worst = ("MISSING" if any(r["status"] == "MISSING" for r in report.values())
             else "SEASON_BOUNDARY" if any(r["status"] == "SEASON_BOUNDARY" for r in report.values())
             else "STALE" if any(r["status"] == "STALE" for r in report.values())
             else "OK")
    return {"as_of": today.isoformat(), "worst": worst, "sports": report}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=1))
