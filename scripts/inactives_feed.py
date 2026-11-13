#!/usr/bin/env python3
"""inactives_feed.py — official NFL game-day inactives, parsed with Scrapling's Selector (adopted from D4Vinci/Scrapling, BSD-3) instead of regex on HTML.

  python3 scripts/inactives_feed.py                 print {team: [(pos, name)]} as posted right now (Rotowire, ~90 min before kickoff)
  python3 scripts/inactives_feed.py --save DATE     merge into data/inactives_DATE.json as {"AWAY@HOME": [names]} for the slate runner

Why: ESPN's game page often shows only the injury report until kickoff; the official list reaches Rotowire first (BUF@MIN, WAS@NYG 2026-11).
Plain HTTP GET of a public page with a normal client; no stealth browser, no anti-bot bypass. If the page layout changes, the parser falls back to
the text sequence (team header followed by POS|Name pairs) that the regex version used.
"""
from __future__ import annotations
import json, re, sys, argparse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.rotowire.com/football/inactives.php"
TEAMS = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
         "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
         "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV",
         "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN", "New England Patriots": "NE",
         "New Orleans Saints": "NO", "New York Giants": "NYG", "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
         "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}
POS = {"QB", "RB", "FB", "WR", "TE", "OT", "OG", "OL", "C", "G", "T", "DT", "DE", "DL", "NT", "LB", "OLB", "ILB", "CB", "S", "FS", "SS", "DB", "K", "P", "LS", "EDGE"}


def fetch(url=URL) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"}), timeout=25).read().decode("utf8", "ignore")


def parse(html: str) -> dict:
    """{abbr: [(pos, name), ...]} from the inactives page."""
    try:
        from scrapling.parser import Selector
        page = Selector(html)
        tokens = [t.strip() for t in page.css("main *::text, body *::text").getall() if t and t.strip()]
    except Exception:  # noqa: BLE001  — scrapling missing: same token stream via regex
        t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
        tokens = [x.strip() for x in re.sub(r"<[^>]+>", "\n", t).split("\n") if x.strip()]
    out, cur, i = {}, None, 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in TEAMS:
            cur = TEAMS[tok]; out.setdefault(cur, []); i += 1; continue
        if tok.startswith("RotoWire's NFL inactives"):
            cur = None
        if cur and tok in POS and i + 1 < len(tokens) and tokens[i + 1] not in POS and tokens[i + 1] not in TEAMS:
            out[cur].append((tok, tokens[i + 1])); i += 2; continue
        i += 1
    return {k: v for k, v in out.items() if v}


def save(date: str, posted: dict) -> Path:
    import urllib.request as u
    sb = json.load(u.urlopen(u.Request(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date}"), timeout=25))
    fix = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}; path = ROOT / "data" / f"inactives_{date}.json"
    cur = json.loads(path.read_text()) if path.exists() else {}
    for e in sb["events"]:
        c = e["competitions"][0]; a = next(x for x in c["competitors"] if x["homeAway"] == "away"); h = next(x for x in c["competitors"] if x["homeAway"] == "home")
        aw, hm = fix.get(a["team"]["abbreviation"], a["team"]["abbreviation"]), fix.get(h["team"]["abbreviation"], h["team"]["abbreviation"])
        names = [n for t in (aw, hm) for _, n in posted.get(t, [])]
        if names: cur[f"{aw}@{hm}"] = sorted(set(cur.get(f"{aw}@{hm}", [])) | set(names))
    cur["_source"] = "Rotowire official inactives via scripts/inactives_feed.py"
    path.write_text(json.dumps(cur, indent=1)); return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--save"); ap.add_argument("--html", help="parse a saved page instead of fetching")
    a = ap.parse_args()
    posted = parse(Path(a.html).read_text() if a.html else fetch())
    print(json.dumps(posted, indent=1) if posted else "no inactives posted right now")
    if a.save and posted: print("saved", save(a.save, posted))
