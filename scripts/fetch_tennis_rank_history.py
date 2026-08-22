#!/usr/bin/env python3
"""
fetch_tennis_rank_history.py — archive POINT-IN-TIME ATP/WTA rankings.

Why this exists: `data/all_ratings.json` holds ONE current snapshot, so any
backtest that scores past matches with it is lookahead. That invalidated the
tennis win-prob backtest outright — its bias flipped sign between adjacent years
because it was measuring how far the snapshot post-dated the match, not the
model (global rule 22). Without point-in-time ranks the model that prices every
tennis moneyline simply cannot be measured.

ESPN's core API exposes weekly ranking snapshots, but only a ROLLING WINDOW —
verified 2026-08-21: ATP/WTA weeks 11-32 of the current season resolve, week 10
and every 2025 week are already 404. So history cannot be back-filled; it has to
be ACCUMULATED. This archives what is reachable today and merges on every run,
so the file grows into the history the backtest needs. Run it weekly (the same
cron that refreshes ranks).

Output: data/tennis_rank_history.json
  {"tours": {"atp": {"2026-32": {"date": ..., "players": {name: {rank, points}}}}}}

Athlete names cost one request each, so they are cached across weeks and across
runs — ~300 unique players instead of 5,000 lookups.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "tennis_rank_history.json"
BASE = "https://sports.core.api.espn.com/v2/sports/tennis/leagues"
TOURS = ("atp", "wta")
TIMEOUT = 25


def _get(url: str) -> dict:
    # No browser User-Agent — ESPN's edge refuses spoofed ones.
    req = urllib.request.Request(url.replace("http://", "https://"))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def load_history() -> dict:
    try:
        return json.loads(OUT.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"tours": {}, "athlete_names": {}}


def ranking_id(tour: str, season: int, week: int) -> str | None:
    """DISCOVER the ranking id for this tour — never hardcode it.

    ATP is id 1 and WTA is id 2. Requesting `/rankings/1` under the WTA league
    path returns HTTP 200 with the ATP ranking, so a hardcoded 1 silently filled
    the WTA archive with men's players (found 2026-08-21 when the WTA backtest
    could not resolve a single player). A 200 is not proof you got what you asked
    for.
    """
    try:
        idx = _get(f"{BASE}/{tour}/seasons/{season}/types/2/weeks/{week}/rankings")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    items = idx.get("items") or []
    if not items:
        return None
    return items[0]["$ref"].rsplit("/rankings/", 1)[-1].split("?")[0]


def week_snapshot(tour: str, season: int, week: int,
                  name_cache: dict) -> dict | None:
    """One week's ranking, or None when ESPN has aged it out."""
    rid = ranking_id(tour, season, week)
    if not rid:
        return None
    url = f"{BASE}/{tour}/seasons/{season}/types/2/weeks/{week}/rankings/{rid}"
    try:
        page = _get(url)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    # Guard the corruption directly: the payload names its own tour.
    got = str(page.get("shortName") or page.get("name") or "").upper()
    if got and tour.upper() not in got:
        raise RuntimeError(
            f"tour mismatch: asked {tour.upper()} week {week}, got {got!r} "
            f"(ranking id {rid}) — refusing to archive the wrong tour")

    ranks = [r for r in page.get("ranks", [])
             if r.get("current") and (r.get("athlete") or {}).get("$ref")]
    if not ranks:
        return None

    # Resolve only athletes we have never seen — names do not change.
    unknown = [r for r in ranks
               if r["athlete"]["$ref"].rsplit("/", 1)[-1].split("?")[0] not in name_cache]
    if unknown:
        def fetch_name(r):
            aid = r["athlete"]["$ref"].rsplit("/", 1)[-1].split("?")[0]
            try:
                a = _get(r["athlete"]["$ref"])
                return aid, a.get("displayName") or a.get("fullName")
            except Exception:
                return aid, None
        with ThreadPoolExecutor(max_workers=8) as pool:
            for aid, nm in pool.map(fetch_name, unknown):
                if nm:
                    name_cache[aid] = nm

    players = {}
    for r in ranks:
        aid = r["athlete"]["$ref"].rsplit("/", 1)[-1].split("?")[0]
        nm = name_cache.get(aid)
        if nm:
            players[nm] = {"rank": float(r["current"]), "points": r.get("points")}
    if not players:
        return None
    return {"date": page.get("lastUpdated") or page.get("season", {}).get("startDate"),
            "week": week, "season": season, "players": players}


def archive(season: int, weeks: range, tours: tuple = TOURS) -> dict:
    """Fetch every reachable week and MERGE into the existing history."""
    hist = load_history()
    names = hist.setdefault("athlete_names", {})
    added = 0
    for tour in tours:
        store = hist.setdefault("tours", {}).setdefault(tour, {})
        for wk in weeks:
            key = f"{season}-{wk:02d}"
            if key in store:               # already archived — never re-fetch
                continue
            snap = week_snapshot(tour, season, wk, names)
            if snap:
                store[key] = snap
                added += 1
    hist["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hist["note"] = ("ESPN serves only a rolling window of weeks; history is "
                    "ACCUMULATED by running this weekly, never back-fillable")
    OUT.write_text(json.dumps(hist))
    return {"added_weeks": added,
            "total_weeks": {t: len(hist["tours"].get(t, {})) for t in tours},
            "known_athletes": len(names), "file": str(OUT)}


def ranking_as_of(tour: str, when: str, hist: dict | None = None) -> dict | None:
    """The most recent archived ranking at or before an ISO date.

    This is the whole point: a backtest must ask "what did we know THEN".
    Returns None when the archive does not reach back that far — which is an
    honest "cannot measure", not a licence to fall back on current ranks.
    """
    hist = hist or load_history()
    store = (hist.get("tours") or {}).get(tour.lower()) or {}
    best = None
    for _key, snap in store.items():
        d = str(snap.get("date") or "")[:10]
        if d and d <= when[:10] and (best is None or d > str(best.get("date"))[:10]):
            best = snap
    return best


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--from-week", type=int, default=1)
    ap.add_argument("--to-week", type=int, default=53)
    a = ap.parse_args()
    print(json.dumps(archive(a.season, range(a.from_week, a.to_week + 1)), indent=1))
