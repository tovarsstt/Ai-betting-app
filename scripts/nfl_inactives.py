"""Official game-day inactives (ESPN core roster `active` flag) for every game on a date, flagged against who actually carries the offense.

The injury report says Questionable; the inactives list (posted ~90 min before kickoff) is the truth. This pulls it for the whole slate and marks the
players that matter to the props (top receivers/rushers/QB by 2026 play-by-play volume), so the slate sim can be re-run with real availability.

Usage: python3 scripts/nfl_inactives.py [YYYYMMDD]      (free ESPN endpoints, default UA)
"""
import sys, json, urllib.request
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_slate_props as sp

CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{e}/competitors/{t}/roster"
SCORE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d}"


def _get(url: str):
    return json.load(urllib.request.urlopen(urllib.request.Request(url), timeout=20))


def roster_status(event_id: str, team_id: str) -> dict:
    """{'posted': bool, 'inactive': [names], 'active_n': int}. Before the list is posted every row is not flagged inactive -> posted False."""
    rows = _get(CORE.format(e=event_id, t=team_id)).get("entries", [])
    inactive = [r.get("displayName") or str(r.get("playerId")) for r in rows if r.get("active") is False]
    active = [r for r in rows if r.get("active")]
    return {"posted": 40 <= len(active) <= 53 and len(rows) > 0, "inactive": inactive, "active_n": len(active), "rows": len(rows)}


def key_players(d: pd.DataFrame, team: str) -> set:
    tb = sp.team_tables(d, team)
    names = set(list(tb["rec"].sort_values(ascending=False).index[:6]) + list(tb["car"].sort_values(ascending=False).index[:3]) + list(tb["qb"].index[:1]))
    return {sp.sig(n) for n in names}


def slate_inactives(date: str) -> list:
    d = sp.load_pbp()
    out = []
    for e in _get(SCORE.format(d=date))["events"]:
        comp = e["competitions"][0]
        for c in comp["competitors"]:
            team = c["team"]["abbreviation"]
            team = {"LAR": "LA", "WSH": "WAS"}.get(team, team)
            st = roster_status(e["id"], c["team"]["id"])
            keys = key_players(d, team)
            st["key_out"] = [n for n in st["inactive"] if sp.sig(n) in keys]
            out.append({"game": e["shortName"], "team": team, **{k: v for k, v in st.items() if k != "rows"}})
    return out


if __name__ == "__main__":
    for r in slate_inactives(sys.argv[1] if len(sys.argv) > 1 else "20261101"):
        if not r["posted"]:                      # before ~90 min pre-kick ESPN flags every roster row inactive: the list means nothing yet
            print(f"{r['game']:12s} {r['team']:4s} not posted yet")
            continue
        print(f"{r['game']:12s} {r['team']:4s} POSTED   active={r['active_n']:2d} KEY OUT: {r['key_out'] or '-'}  all out: {len(r['inactive'])}")
