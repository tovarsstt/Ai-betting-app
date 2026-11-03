"""Drive-level history of FBS teams from ESPN (free): every completed 2026 game of each team and of the opponents it faced, with each drive's outcome,
plays and yards plus the team box score. Feeds cfb_box_sim.py. Usage: python3 scripts/cfb_box_fetch.py TEAM_ID [TEAM_ID ...]"""
import sys, json, time, urllib.request
from pathlib import Path

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
CACHE = Path(__file__).resolve().parent.parent / "data" / "cfb_box_cache.json"


def _get(url: str, tries: int = 4):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(url, timeout=25))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def completed_event_ids(team_id: str, season: int = 2026) -> list:
    sch = _get(f"{SITE}/teams/{team_id}/schedule?season={season}")
    return [e["id"] for e in sch["events"] if e["competitions"][0]["status"]["type"]["completed"]]


def parse_game(eid: str) -> dict:
    s = _get(f"{SITE}/summary?event={eid}")
    comp = s["header"]["competitions"][0]
    teams = {c["team"]["id"]: {"name": c["team"]["displayName"], "score": int(c.get("score") or 0), "home": c["homeAway"] == "home"} for c in comp["competitors"]}
    for t in s["boxscore"]["teams"]:
        teams[t["team"]["id"]]["box"] = {x["name"]: x["displayValue"] for x in t["statistics"]}
    drives = [{"team": d["team"]["id"], "result": d.get("displayResult") or d.get("result"), "yards": d.get("yards", 0), "plays": d.get("offensivePlays", 0)}
              for d in s.get("drives", {}).get("previous", [])]
    return {"id": eid, "date": comp.get("date", "")[:10], "teams": teams, "drives": drives}


def fetch(team_ids: list) -> dict:
    games = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for tid in team_ids:
        for eid in completed_event_ids(tid):
            if eid not in games:
                games[eid] = parse_game(eid)
    CACHE.write_text(json.dumps(games))
    return games


if __name__ == "__main__":
    g = fetch(sys.argv[1:])
    print(len(g), "games cached")
