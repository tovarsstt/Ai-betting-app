#!/usr/bin/env python3
"""
fetch_cfb_data.py — college football week board from ESPN (free, no key).

CFB has no local model (rule 30 precedent: NHL — sharp-anchor only), so the
profile layer needs REAL context per game: AP rank, record, and the embedded
DraftKings line ESPN ships per scheduled event. Zero Odds-API quota.

Writes data/cfb_board.json. Run: python3 scripts/fetch_cfb_data.py [--week N]
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "cfb_board.json"
SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/"
              "college-football/scoreboard?groups=80&limit=200")
TIMEOUT = 25


def _get(url: str) -> dict:
    req = urllib.request.Request(url)  # default UA — ESPN 403s Mozilla UAs
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def parse_event(ev: dict) -> dict | None:
    """One scoreboard event -> board row. Returns None on malformed events."""
    comp = (ev.get("competitions") or [{}])[0]
    sides: dict[str, dict] = {}
    for c in comp.get("competitors", []):
        team = (c.get("team") or {}).get("displayName")
        if not team:
            return None
        rank = (c.get("curatedRank") or {}).get("current")
        recs = c.get("records") or []
        sides[c.get("homeAway", "?")] = {
            "team": team,
            "rank": rank if rank is not None and rank <= 25 else None,
            "record": recs[0].get("summary") if recs else None,
            "score": c.get("score"),
        }
    if "home" not in sides or "away" not in sides:
        return None
    odds_raw = (comp.get("odds") or [{}])[0]
    odds = None
    if odds_raw.get("details"):
        odds = {
            "provider": (odds_raw.get("provider") or {}).get("name"),
            "details": odds_raw.get("details"),        # e.g. "OSU -3.5"
            "over_under": odds_raw.get("overUnder"),
        }
        ml = odds_raw.get("moneyline") or {}
        for side in ("home", "away"):
            price = ((ml.get(side) or {}).get("close") or {}).get("odds")
            if price is not None:
                odds[f"{side}_ml"] = price
    return {
        "name": ev.get("name"),
        "date": ev.get("date"),
        "status": ((ev.get("status") or {}).get("type") or {}).get("description"),
        "home": sides["home"],
        "away": sides["away"],
        "odds": odds,
    }


def fetch(week: int | None = None) -> dict:
    url = SCOREBOARD + (f"&week={week}" if week else "")
    board = _get(url)
    games = [g for g in (parse_event(e) for e in board.get("events", [])) if g]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ESPN college-football scoreboard (free)",
        "week": (board.get("week") or {}).get("number"),
        "n_games": len(games),
        "games": games,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="print the board as JSON (server mode)")
    args = ap.parse_args()
    result = fetch(args.week)
    OUT.write_text(json.dumps(result, indent=1))
    if args.json:
        print(json.dumps(result))
        return
    ranked = sum(1 for g in result["games"] if g["home"]["rank"] or g["away"]["rank"])
    priced = sum(1 for g in result["games"] if g["odds"])
    print(f"week {result['week']}: {result['n_games']} games "
          f"({ranked} with ranked teams, {priced} with a DK line) -> {OUT}")


if __name__ == "__main__":
    main()
