"""
fetch_nba_detail.py — per-game NBA detail from ESPN's public summary endpoint (box score, play-by-play, shot coordinates).
Runs on GitHub Actions only (the cloud sandbox has no route to ESPN). The sandbox only parses the files it pushes.

    python3 scripts/fetch_nba_detail.py probe <game_id> [<game_id> ...]   # saves raw summary JSON under data/nba/probe/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fetch_europe_data as fe

DATA = Path(__file__).parent.parent / "data" / "nba"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={}"


def fetch_summary(game_id: str) -> dict:
    return json.loads(fe._get(SUMMARY.format(game_id), timeout=30))


def probe(ids: list[str]) -> None:
    out = DATA / "probe"
    out.mkdir(parents=True, exist_ok=True)
    for gid in ids:
        d = fetch_summary(gid)
        (out / f"{gid}.json").write_text(json.dumps(d))
        print(gid, "keys:", sorted(d), "| plays:", len(d.get("plays", [])), "| box teams:", len(d.get("boxscore", {}).get("teams", [])))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "probe":
        probe(sys.argv[2:])
    else:
        print(__doc__)
