#!/usr/bin/env python3
"""
fetch_match_stats.py — the match detail the results pipeline was discarding.

`club_results.csv` keeps date, teams, score, league. The SAME football-data file
also carries shots, shots on target, fouls, corners, yellows, reds, half-time
score, the REFEREE'S NAME, and closing odds — and all of it was being dropped on
import. Style, tempo, referee tendency and derby intensity are not things that
need inventing; they are sitting in columns nobody read.

What this enables, all COUNTED rather than asserted:
  * team style — shots and shots-on-target per game, conversion, corners,
    discipline, and how a side splits its goals between the halves
  * referee profile — cards and fouls per game, and fouls-per-card, which is
    the number that separates a strict whistle from a lenient one
  * derby intensity — cards and fouls in a specific fixture against each side's
    own baseline, so "this one is spicy" becomes a measurement
  * closing odds (B365) — the first real CLV reference this project has had

Output: data/soccer/match_stats.csv, one row per match, superset of the columns.

Free, no key. Sends the project's normal fetch headers, not a spoofed browser UA.

Run: python3 scripts/fetch_match_stats.py [--seasons 2526 2425]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "soccer"
OUT = DATA / "match_stats.csv"

LEAGUES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
           "D1": "Bundesliga", "F1": "Ligue 1"}

# Source column -> our name. Anything missing in a given season is left blank
# rather than defaulted, so a zero always means a real zero.
COLS = {
    "Date": "date", "HomeTeam": "home_team", "AwayTeam": "away_team",
    "FTHG": "home_goals", "FTAG": "away_goals",
    "HTHG": "ht_home_goals", "HTAG": "ht_away_goals",
    "Referee": "referee",
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_sot", "AST": "away_sot",
    "HF": "home_fouls", "AF": "away_fouls",
    "HC": "home_corners", "AC": "away_corners",
    "HY": "home_yellow", "AY": "away_yellow",
    "HR": "home_red", "AR": "away_red",
    # Closing odds — a real reference price, which CLV has been missing.
    "B365H": "close_home", "B365D": "close_draw", "B365A": "close_away",
}
FIELDS = ["date", "league", "home_team", "away_team", "home_goals", "away_goals",
          "ht_home_goals", "ht_away_goals", "referee",
          "home_shots", "away_shots", "home_sot", "away_sot",
          "home_fouls", "away_fouls", "home_corners", "away_corners",
          "home_yellow", "away_yellow", "home_red", "away_red",
          "close_home", "close_draw", "close_away"]


def _season_codes(n: int = 3) -> list[str]:
    today = datetime.now()
    start = today.year if today.month >= 7 else today.year - 1
    return [f"{str(y)[2:]}{str(y + 1)[2:]}" for y in range(start, start - n, -1)]


def _iso(d: str) -> str:
    """football-data writes dd/mm/yy or dd/mm/yyyy."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def fetch_one(div: str, season: str, timeout: int = 30) -> list[dict]:
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "caveman-locks/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("latin-1")
    rd = csv.DictReader(io.StringIO(text))
    out = []
    for row in rd:
        # The first header can carry a BOM; match on the stripped name.
        clean = {(k or "").strip().lstrip("﻿"): v for k, v in row.items()}
        date = _iso(clean.get("Date", ""))
        if not date or not clean.get("HomeTeam"):
            continue
        rec = {"league": LEAGUES[div]}
        for src, dst in COLS.items():
            v = (clean.get(src) or "").strip()
            rec[dst] = v
        rec["date"] = date
        out.append(rec)
    return out


def harvest(seasons: list[str] | None = None) -> dict:
    seasons = seasons or _season_codes()
    rows, skipped = [], []
    for div in LEAGUES:
        for season in seasons:
            try:
                got = fetch_one(div, season)
                rows.extend(got)
            except Exception as e:                          # noqa: BLE001
                skipped.append(f"{div}/{season}: {type(e).__name__}")
    # Merge with what is already stored; a re-fetch must not duplicate.
    existing = []
    if OUT.exists():
        with OUT.open() as f:
            existing = list(csv.DictReader(f))
    seen, merged = set(), []
    for r in existing + rows:
        k = (r.get("date"), r.get("home_team"), r.get("away_team"))
        if k in seen:
            continue
        seen.add(k)
        merged.append({c: r.get(c, "") for c in FIELDS})
    merged.sort(key=lambda r: r["date"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(merged)

    with_ref = sum(1 for r in merged if r.get("referee"))
    with_shots = sum(1 for r in merged if r.get("home_shots"))
    return {"matches": len(merged), "with_referee": with_ref,
            "with_shot_data": with_shots, "seasons": seasons,
            "unavailable": skipped, "file": str(OUT)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", default=None,
                    help="football-data codes, e.g. 2526 2425")
    a = ap.parse_args()
    print(json.dumps(harvest(a.seasons), indent=1))
