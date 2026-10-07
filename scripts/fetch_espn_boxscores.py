#!/usr/bin/env python3
"""
fetch_espn_boxscores.py — per-game player minutes / stats / pre-game injury list from ESPN's free summary API.
(ESPN 403s Mozilla user-agents; urllib's default UA works.)  Output: one trimmed JSON line per game.

    python3 scripts/fetch_espn_boxscores.py nba /tmp/kg/espn_nba.jsonl "/tmp/kg/closing_odds/NBA 24-25.xlsx" "/tmp/kg/closing_odds/NBA 25-26.xlsx"
Game ids come from the closing-odds files (their game_id IS the ESPN event id), so every box score joins to a closing line.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

SPORT = {"nba": "basketball/nba", "nfl": "football/nfl", "nhl": "hockey/nhl", "mlb": "baseball/mlb"}


def fetch(sport: str, gid: int, tries: int = 4) -> dict | None:
    u = f"https://site.api.espn.com/apis/site/v2/sports/{SPORT[sport]}/summary?event={gid}"
    for t in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=40))
            break
        except Exception:
            time.sleep(1.5 * (t + 1))
    else:
        return None
    try:
        return _parse(gid, d)
    except Exception:
        return None


def _parse(gid, d):
    out = {"id": gid, "teams": [], "injuries": []}
    for tm in d.get("boxscore", {}).get("players", []):
        rec = {"team": tm["team"]["displayName"], "abbr": tm["team"].get("abbreviation"), "players": []}
        for grp in tm.get("statistics", []):
            keys = grp.get("keys", [])
            for a in grp.get("athletes", []):
                st = dict(zip(keys, a.get("stats", [])))
                ath = a.get("athlete") or {}
                rec["players"].append({"group": grp.get("name"), "id": ath.get("id") or ath.get("displayName"), "name": ath.get("displayName", "?"), "pos": (ath.get("position") or {}).get("abbreviation"),
                                       "starter": a.get("starter"), "dnp": a.get("didNotPlay"), "reason": a.get("reason"), "active": a.get("active"), "stats": st})
        out["teams"].append(rec)
    for inj in d.get("injuries", []):
        out["injuries"].append({"team": inj["team"]["displayName"], "list": [{"name": (x.get("athlete") or {}).get("displayName"), "status": x.get("status"), "type": (x.get("type") or {}).get("description")} for x in inj.get("injuries", [])]})
    pc = (d.get("pickcenter") or [{}])[0]                       # posted line of the finished game (provider priority 1)
    out["pick"] = {"provider": (pc.get("provider") or {}).get("name"), "spread": pc.get("spread"), "ou": pc.get("overUnder"), "over_odds": pc.get("overOdds"), "under_odds": pc.get("underOdds"),
                   "home_spread_odds": (pc.get("homeTeamOdds") or {}).get("spreadOdds"), "away_spread_odds": (pc.get("awayTeamOdds") or {}).get("spreadOdds")}
    gi = d.get("gameInfo", {}).get("venue", {})
    out["venue"] = {"city": (gi.get("address") or {}).get("city"), "indoor": gi.get("indoor")}
    hd = d.get("header", {}).get("competitions", [{}])[0]
    out["score"] = [(c["team"]["displayName"], c.get("score"), c.get("homeAway")) for c in hd.get("competitors", [])]
    return out


if __name__ == "__main__":
    sport, outp, *files = sys.argv[1:]
    ids = []
    for f in files:
        ids += [json.loads(l)["id"] for l in open(f)] if f.endswith(".jsonl") else pd.read_excel(f).game_id.tolist()
    ids = list(dict.fromkeys(ids))
    done = set()
    p = Path(outp)
    if p.exists():
        done = {json.loads(l)["id"] for l in p.open()}
    todo = [i for i in ids if i not in done]
    print(f"{len(ids)} games, {len(todo)} to fetch", flush=True)
    n = 0
    with ThreadPoolExecutor(8) as ex, p.open("a") as fh:
        for r in ex.map(lambda g: fetch(sport, g), todo):
            if r:
                fh.write(json.dumps(r) + "\n")
                n += 1
                if n % 200 == 0:
                    print(n, "fetched", flush=True)
    print("done", n)
