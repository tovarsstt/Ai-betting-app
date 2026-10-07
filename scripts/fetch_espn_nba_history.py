#!/usr/bin/env python3
"""Collect ESPN NBA regular-season event ids (+date, teams, scores) by scoreboard day, then box scores.
   python3 scripts/fetch_espn_nba_history.py 2021-10-19 2024-04-15 /tmp/kg/espn_nba_hist_events.jsonl"""
import json, sys, datetime, urllib.request, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

def day(d):
    u = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d.strftime('%Y%m%d')}&limit=50"
    for t in range(4):
        try:
            j = json.load(urllib.request.urlopen(u, timeout=40)); break
        except Exception:
            time.sleep(1.5 * (t + 1))
    else:
        return []
    out = []
    for e in j.get("events", []):
        c = e["competitions"][0]
        if (e.get("season") or {}).get("type") != 2 or c["status"]["type"]["name"] != "STATUS_FINAL":
            continue
        tm = {x["homeAway"]: x for x in c["competitors"]}
        out.append({"id": int(e["id"]), "utc": e["date"], "home": tm["home"]["team"]["abbreviation"], "away": tm["away"]["team"]["abbreviation"],
                    "hn": tm["home"]["team"]["displayName"], "an": tm["away"]["team"]["displayName"], "hp": int(tm["home"]["score"]), "ap": int(tm["away"]["score"])})
    return out

if __name__ == "__main__":
    a, b, outp = sys.argv[1:4]
    d0, d1 = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    days = [d0 + datetime.timedelta(i) for i in range((d1 - d0).days + 1)]
    n = 0
    with ThreadPoolExecutor(8) as ex, Path(outp).open("w") as fh:
        for res in ex.map(day, days):
            for r in res:
                fh.write(json.dumps(r) + "\n"); n += 1
    print("events", n)
