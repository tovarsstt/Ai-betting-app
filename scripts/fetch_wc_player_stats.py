#!/usr/bin/env python3
"""
fetch_wc_player_stats.py — World Cup 2026 per-player per-match stat cache.

Why: prop picks died blind on WC player legs (Diaz 1+ SOT, Messi 2+ SOT...)
and the tournament itself is short — a handful of games per player. ESPN's
per-athlete gamelog API 500s for fifa.world, but every match SUMMARY carries
the full player boxscore (totalShots, shotsOnTarget, goals, assists, fouls,
cards). So: walk the tournament's completed matches once, cache every
player's line per match, refresh incrementally (only unseen matches).

Source: ESPN public API (free, no key, no quota).
Output data/wc_player_stats.json:
  { "fetched": iso, "event_ids": [..],
    "players": { norm_name: { "display": str, "team": str,
        "games": [ {date, event_id, opponent, shots, shots_on_target,
                    goals, assists, fouls, yellow_cards, red_cards} ] } } }

CLI:  python3 scripts/fetch_wc_player_stats.py          # refresh cache
"""
from __future__ import annotations

import datetime
import json
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Optional

OUT = Path(__file__).parent.parent / "data" / "wc_player_stats.json"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={d}"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={eid}"
WC_START = datetime.date(2026, 6, 11)
_UA = {"User-Agent": "Mozilla/5.0"}

# ESPN roster stat name -> our stat key
STAT_MAP = {
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "totalGoals": "goals",
    "goalAssists": "assists",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
}


def _get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def norm_name(name: str) -> str:
    """Accent-insensitive, lowercase key: 'Luis Díaz' -> 'luis diaz'."""
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def completed_events(start: datetime.date, end: datetime.date) -> list[dict]:
    """[{id, date}] for every finished WC match in the window."""
    out = []
    d = start
    while d <= end:
        try:
            sb = _get(SCOREBOARD.format(d=d.strftime("%Y%m%d")))
        except Exception:
            d += datetime.timedelta(days=1)
            continue
        for ev in sb.get("events", []):
            state = ((ev.get("status") or {}).get("type") or {}).get("state")
            if state == "post":
                out.append({"id": str(ev.get("id")), "date": ev.get("date", "")})
        d += datetime.timedelta(days=1)
        time.sleep(0.2)
    return out


def parse_summary_rosters(summary: dict, event_id: str, date: str) -> list[dict]:
    """Pure: one match summary -> player rows (only players who appeared)."""
    rows = []
    rosters = summary.get("rosters") or []
    team_names = {r.get("homeAway"): ((r.get("team") or {}).get("displayName") or "")
                  for r in rosters}
    for side in rosters:
        opponent = team_names.get("away" if side.get("homeAway") == "home" else "home", "")
        for p in side.get("roster") or []:
            stats = {s.get("name"): s.get("value") for s in (p.get("stats") or [])}
            if not stats or not stats.get("appearances"):
                continue  # didn't play — a DNP is not a 0-shot game
            athlete = p.get("athlete") or {}
            name = athlete.get("displayName") or ""
            if not name:
                continue
            row = {"player": name,
                   "team": (side.get("team") or {}).get("displayName") or "",
                   "event_id": event_id, "date": date, "opponent": opponent}
            for espn_key, our_key in STAT_MAP.items():
                row[our_key] = float(stats.get(espn_key) or 0.0)
            rows.append(row)
    return rows


def load_cache() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text())
        except Exception:
            pass
    return {"fetched": None, "event_ids": [], "players": {}}


def refresh(cache: Optional[dict] = None) -> dict:
    """Incremental: fetch only matches not already in the cache."""
    cache = cache if cache is not None else load_cache()
    seen = set(cache.get("event_ids") or [])
    today = datetime.date.today()
    # First run walks the whole tournament; refreshes only rescan the last few
    # days (already-cached event ids are skipped regardless).
    start = max(WC_START, today - datetime.timedelta(days=3)) if seen else WC_START
    new_events = [e for e in completed_events(start, today) if e["id"] not in seen]
    for ev in new_events:
        try:
            summary = _get(SUMMARY.format(eid=ev["id"]))
        except Exception:
            continue
        for row in parse_summary_rosters(summary, ev["id"], ev["date"]):
            display = row.pop("player")
            key = norm_name(display)
            slot = cache["players"].setdefault(key, {"display": display, "team": "", "games": []})
            slot["team"] = row.pop("team") or slot["team"]
            slot["games"].append(row)
        seen.add(ev["id"])
        time.sleep(0.3)
    for slot in cache["players"].values():
        slot["games"].sort(key=lambda g: g["date"], reverse=True)
    cache["event_ids"] = sorted(seen)
    cache["fetched"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache))
    return cache


def ensure_fresh(max_age_hours: float = 12.0) -> dict:
    """Load the cache, refreshing first when stale/missing. Network only when
    stale — cheap on repeat calls, safe to call per real prop request."""
    cache = load_cache()
    fetched = cache.get("fetched")
    if fetched:
        try:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(fetched)).total_seconds() / 3600
            if age < max_age_hours:
                return cache
        except ValueError:
            pass
    return refresh(cache)


if __name__ == "__main__":
    c = refresh()
    n_games = sum(len(p["games"]) for p in c["players"].values())
    print(f"WC cache: {len(c['event_ids'])} matches, {len(c['players'])} players, "
          f"{n_games} player-game rows -> {OUT}")
