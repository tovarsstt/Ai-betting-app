#!/usr/bin/env python3
"""
fetch_wnba_form.py — WNBA comparative profile (form / rest / H2H) for the model.

WNBA only had 12 static team ratings — no form, no rest, no H2H. This builds the
sharp read from REAL game results: recent form, scoring margin, current streak,
REST / back-to-back fatigue (the single biggest WNBA edge — tired legs on a B2B),
home/road splits, and head-to-head. Never invented.

Source: ESPN WNBA scoreboard (public, free) iterated over the current season.
Output (data/wnba_form.json):
  { "teams": { name: { gp, win_rate, last10, avg_margin, recent_margin, streak,
        rest_days, b2b, home, road } },
    "h2h": { name: { opp: { n, w, l, margin, last } } } }
Re-run daily in season.
"""
import datetime
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "wnba_form.json"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={d}"
SEASON_START = datetime.date(datetime.date.today().year, 5, 1)   # WNBA opens ~May


def fetch_day(d: datetime.date) -> list:
    url = SCOREBOARD.format(d=d.strftime("%Y%m%d"))
    try:
        raw = urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
        data = json.loads(raw)
    except Exception:
        return []
    games = []
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = ((ev.get("status") or {}).get("type") or {})
        if not status.get("completed"):
            continue
        teams = {}
        for c in comp.get("competitors", []):
            t = (c.get("team") or {}).get("displayName")
            try:
                pts = int(c.get("score"))
            except (TypeError, ValueError):
                pts = None
            if t is None or pts is None:
                continue
            teams[c.get("homeAway")] = (t, pts)
        if "home" in teams and "away" in teams:
            games.append({"date": d, "home": teams["home"], "away": teams["away"]})
    return games


def build() -> None:
    today = datetime.date.today()
    rows = []
    d = SEASON_START
    while d <= today:
        rows.extend(fetch_day(d))
        d += datetime.timedelta(days=1)
        time.sleep(0.05)
    if not rows:
        raise SystemExit("no WNBA games — ESPN unreachable or off-season?")
    rows.sort(key=lambda g: g["date"])
    print(f"  {len(rows)} completed WNBA games {SEASON_START}..{today}")

    games = defaultdict(list)   # team -> chronological [(date, opp, pf, pa, is_home, win)]
    for g in rows:
        (ht, hp), (at, ap) = g["home"], g["away"]
        games[ht].append((g["date"], at, hp, ap, True, hp > ap))
        games[at].append((g["date"], ht, ap, hp, False, ap > hp))

    teams = {}
    h2h = defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "m": 0.0, "last": ""}))
    for team, gl in games.items():
        gl.sort(key=lambda x: x[0])
        gp = len(gl)
        if gp < 3:
            continue
        wins = sum(1 for x in gl if x[5])
        margins = [x[2] - x[3] for x in gl]
        last10 = gl[-10:]
        # current streak
        streak = 0
        for x in reversed(gl):
            if streak == 0:
                streak = 1 if x[5] else -1; last = x[5]
            elif x[5] == last:
                streak += 1 if x[5] else -1
            else:
                break
        # rest / back-to-back from the two most recent games
        rest_days = None
        b2b = False
        if gp >= 2:
            rest_days = (gl[-1][0] - gl[-2][0]).days
            b2b = rest_days <= 1
        home = [x for x in gl if x[4]]
        road = [x for x in gl if not x[4]]
        teams[team] = {
            "gp": gp,
            "win_rate": round(wins / gp, 3),
            "last10": f"{sum(1 for x in last10 if x[5])}-{sum(1 for x in last10 if not x[5])}",
            "avg_margin": round(sum(margins) / gp, 1),
            "recent_margin": round(sum(x[2] - x[3] for x in gl[-5:]) / min(5, gp), 1),
            "streak": (f"W{streak}" if streak > 0 else f"L{-streak}"),
            "rest_days": rest_days,
            "b2b": b2b,
            "home": f"{sum(1 for x in home if x[5])}-{sum(1 for x in home if not x[5])}",
            "road": f"{sum(1 for x in road if x[5])}-{sum(1 for x in road if not x[5])}",
        }
        for dt_, opp, pf, pa, _, win in gl:
            rec = h2h[team][opp]
            rec["n"] += 1; rec["w"] += 1 if win else 0
            rec["m"] += pf - pa; rec["last"] = f"{dt_} {pf}-{pa}"

    h2h_out = {t: {o: {"n": r["n"], "w": r["w"], "l": r["n"] - r["w"],
                       "margin": round(r["m"] / r["n"], 1), "last": r["last"]}
                  for o, r in opps.items()}
               for t, opps in h2h.items() if t in teams}

    OUT.write_text(json.dumps({"teams": teams, "h2h": h2h_out,
                               "built": today.isoformat()}, ensure_ascii=False))
    print(f"form for {len(teams)} WNBA teams -> {OUT.name}")
    print("restart edge_api (kill :8001) to load; /predict returns a `profile` for WNBA")


if __name__ == "__main__":
    build()
