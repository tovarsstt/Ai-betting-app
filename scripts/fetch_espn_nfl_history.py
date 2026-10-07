#!/usr/bin/env python3
"""ESPN NFL regular-season events by scoreboard day (2012-2025) -> /tmp/kg/espn_nfl_events.jsonl, then box scores via fetch_espn_boxscores.py.
   python3 scripts/fetch_espn_nfl_history.py 2012 2025 /tmp/kg/espn_nfl_events.jsonl"""
import json, sys, datetime, urllib.request, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

def day(d):
    u = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d.strftime('%Y%m%d')}&limit=50"
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
        out.append({"id": int(e["id"]), "utc": e["date"], "hn": tm["home"]["team"]["displayName"], "an": tm["away"]["team"]["displayName"],
                    "hp": int(tm["home"]["score"]), "ap": int(tm["away"]["score"]), "neutral": bool(c.get("neutralSite"))})
    return out

if __name__ == "__main__":
    y0, y1, outp = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    days = []
    for y in range(y0, y1 + 1):
        d = datetime.date(y, 9, 1)
        while d <= datetime.date(y + 1, 1, 12):
            days.append(d); d += datetime.timedelta(1)
    n = 0
    with ThreadPoolExecutor(8) as ex, Path(outp).open("w") as fh:
        for res in ex.map(day, days):
            for r in res:
                fh.write(json.dumps(r) + "\n"); n += 1
    print("events", n)
