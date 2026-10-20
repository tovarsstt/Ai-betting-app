"""
fetch_nba_detail.py — per-game NBA detail from ESPN's public summary endpoint (box score, play-by-play, shot coordinates).
Runs on GitHub Actions only (the cloud sandbox has no route to ESPN). The sandbox only parses the files it pushes.

    python3 scripts/fetch_nba_detail.py probe <game_id> [<game_id> ...]   # saves raw summary JSON under data/nba/probe/
    python3 scripts/fetch_nba_detail.py full <season> [<season> ...]       # parses every game of data/nba_games_2526.csv / nba_halves.csv for those seasons
"""
from __future__ import annotations

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fetch_europe_data as fe
import nba_detail as nd

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


def game_ids(seasons: set[str]) -> list[str]:
    ids: dict[str, str] = {}
    for f in (DATA.parent / "nba_halves.csv", DATA.parent / "nba_games_2526.csv"):
        if f.exists():
            for r in csv.DictReader(open(f)):
                if r["season"] in seasons:
                    ids[r["game_id"]] = r["date"]
    return [g for g, _ in sorted(ids.items(), key=lambda kv: kv[1])]


def one(gid: str) -> dict | None:
    try:
        return nd.parse_summary(fetch_summary(gid))
    except Exception as e:                                           # a failed game is skipped and counted, never invented
        print(f"  {gid}: skip ({type(e).__name__}: {e})")
        return None


def full(seasons: set[str], workers: int = 6) -> None:
    ids = game_ids(seasons)
    print(f"{len(ids)} games for seasons {sorted(seasons)}")
    with ThreadPoolExecutor(workers) as ex:
        parsed = [p for p in ex.map(one, ids) if p]
    tag = "_".join(sorted(seasons))
    for key in ("team", "player", "shot", "onoff"):
        rows = [r for p in parsed for r in p[key]]
        if rows:
            fe.write_csv(rows, DATA / f"{key}_{tag}.csv", list(rows[0]))
    ok = sum(p["lineup_ok"] for p in parsed)
    print(f"parsed {len(parsed)}/{len(ids)} games; lineup_ok {ok} ({ok / max(len(parsed), 1):.1%})")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "probe":
        probe(sys.argv[2:])
    elif len(sys.argv) > 2 and sys.argv[1] == "full":
        full(set(sys.argv[2:]))
    else:
        print(__doc__)
