#!/usr/bin/env python3
"""
team_off_def.py — offensive + defensive ratings for TEAMS in every sport.

Why: the app had one power number per team (all_ratings.json) — it knew who
was better, not HOW. Off/def splits answer the questions picks actually hang
on: does this game go over? can a weak offense crack a top defense? Soccer
already has the gold standard (Poisson attack/defense fits — fit_soccer_
ratings.py / fit_club_ratings.py); this adds the same lens to the rest, on
one uniform scale, from real season data.

Ratings (per team):
  scored_pg   what the team scores per game
  allowed_pg  what it concedes per game
  off_rating  scored_pg / league_avg   (1.10 = offense 10% above average)
  def_rating  allowed_pg / league_avg  (0.90 = concedes 10% BELOW avg = strong D)

Sources (ESPN, free, cached to data/team_off_def.json):
  nba/wnba  core API avgPoints / avgPointsAllowed per team
  nhl       core API avgGoals / avgGoalsAgainst per team
  mlb       core API batting.runs & pitching.runs (allowed) per game
  nfl       season scoreboard crawl -> points for/against per game
  soccer    WC 2026 scoreboard -> tournament GF/GA per team (club +
            international Poisson fits already live elsewhere — not duplicated)

CLI:  python3 scripts/team_off_def.py --build all      # or one sport
      python3 scripts/team_off_def.py --show wnba
"""
from __future__ import annotations

import argparse
import datetime
import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import fetch_wc_player_stats as wc_fetch

OUT = Path(__file__).parent.parent / "data" / "team_off_def.json"
_UA = {"User-Agent": "Mozilla/5.0"}

CORE = ("https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{lg}/"
        "seasons/{yr}/types/2/teams/{tid}/statistics")
TEAMS = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{lg}/teams"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d}"

SPORTS = ("nba", "wnba", "nfl", "mlb", "nhl", "soccer")


def _get(url: str, timeout: int = 15) -> Optional[dict]:
    for attempt in range(3):  # ESPN throttles bulk crawls — retry, don't drop
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


# ── Pure: stat extraction per sport family ───────────────────────────────────
def _stat_index(stats_json: dict) -> dict:
    """{category_name: {stat_name: value}} from a core statistics payload."""
    out: dict = {}
    for cat in (stats_json.get("splits") or {}).get("categories", []):
        slot = out.setdefault(cat.get("name") or "?", {})
        for s in cat.get("stats", []):
            slot[s.get("name")] = s.get("value")
    return out


def extract_basketball(stats_json: dict) -> Optional[dict]:
    idx = _stat_index(stats_json)
    merged = {k: v for cat in idx.values() for k, v in cat.items()}
    if not merged.get("avgPoints") or not merged.get("avgPointsAllowed"):
        return None
    return {"scored_pg": float(merged["avgPoints"]),
            "allowed_pg": float(merged["avgPointsAllowed"]),
            "games": int(merged.get("gamesPlayed") or 0)}


def extract_nhl(stats_json: dict) -> Optional[dict]:
    idx = _stat_index(stats_json)
    merged = {k: v for cat in idx.values() for k, v in cat.items()}
    if not merged.get("avgGoals") or not merged.get("avgGoalsAgainst"):
        return None
    avg_goals = float(merged["avgGoals"])
    # NHL core stats carry no gamesPlayed — derive from totals
    games = int(merged.get("gamesPlayed") or
                round(float(merged.get("goals") or 0) / avg_goals))
    return {"scored_pg": avg_goals,
            "allowed_pg": float(merged["avgGoalsAgainst"]),
            "games": games}


def extract_mlb(stats_json: dict) -> Optional[dict]:
    idx = _stat_index(stats_json)
    bat, pit = idx.get("batting") or {}, idx.get("pitching") or {}
    gp = bat.get("gamesPlayed") or pit.get("gamesPlayed")
    if not gp or bat.get("runs") is None or pit.get("runs") is None:
        return None
    return {"scored_pg": float(bat["runs"]) / float(gp),
            "allowed_pg": float(pit["runs"]) / float(gp),
            "games": int(gp)}


CORE_SPORTS = {
    "wnba": ("basketball", "wnba", extract_basketball),
    "nhl":  ("hockey", "nhl", extract_nhl),
    "mlb":  ("baseball", "mlb", extract_mlb),
}

STANDINGS = "https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/standings?season={yr}"


def build_from_standings(espn_sport: str, lg: str, season: Optional[int] = None) -> dict:
    """One-request path: league standings carry avgPointsFor/Against.
    (NBA core team stats have no 'allowed' column — WNBA does. ESPN.)"""
    season = season or datetime.date.today().year
    data = _get(STANDINGS.format(sport=espn_sport, lg=lg, yr=season))
    teams = {}
    for group in (data or {}).get("children", []):
        for e in (group.get("standings") or {}).get("entries", []):
            name = (e.get("team") or {}).get("displayName") or ""
            stats = {s.get("name"): s.get("value") for s in e.get("stats", [])}
            pf, pa = stats.get("avgPointsFor"), stats.get("avgPointsAgainst")
            if not name or not pf or pa is None:
                continue
            # standings entries carry no gamesPlayed — derive it from totals
            games = int(stats.get("gamesPlayed") or
                        round(float(stats.get("pointsFor") or 0) / float(pf)))
            teams[wc_fetch.norm_name(name)] = {
                "display": name, "games": games,
                "scored_pg": float(pf), "allowed_pg": float(pa)}
    return finish_table(teams, season)


# ── Builders ─────────────────────────────────────────────────────────────────
def build_core_sport(sport: str, season: Optional[int] = None) -> dict:
    """Per-team core-statistics fetch for nba/wnba/nhl/mlb."""
    espn_sport, lg, extract = CORE_SPORTS[sport]
    season = season or datetime.date.today().year
    teams_raw = _get(TEAMS.format(sport=espn_sport, lg=lg))
    teams = (teams_raw or {}).get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    out = {}
    for t in teams:
        tid, name = t["team"]["id"], t["team"]["displayName"]
        stats = _get(CORE.format(sport=espn_sport, lg=lg, yr=season, tid=tid))
        row = extract(stats) if stats else None
        if row:
            out[wc_fetch.norm_name(name)] = {"display": name, **row}
        time.sleep(0.15)
    return finish_table(out, season)


def scores_from_scoreboard(path: str, dates: list[str]) -> dict:
    """Crawl scoreboards -> {team: {games, scored, allowed}} from final scores."""
    acc: dict = {}
    for d in dates:
        sb = _get(SCOREBOARD.format(path=path, d=d))
        if sb is None:
            continue
        for ev in sb.get("events", []):
            state = ((ev.get("status") or {}).get("type") or {}).get("state")
            if state != "post":
                continue
            comp = (ev.get("competitions") or [{}])[0]
            sides = []
            for c in comp.get("competitors", []):
                name = (c.get("team") or {}).get("displayName")
                try:
                    score = float(c.get("score"))
                except (TypeError, ValueError):
                    name = None
                if name:
                    sides.append((name, score))
            if len(sides) != 2:
                continue
            for (me, mine), (_, theirs) in ((sides[0], sides[1]), (sides[1], sides[0])):
                slot = acc.setdefault(wc_fetch.norm_name(me),
                                      {"display": me, "games": 0, "scored": 0.0, "allowed": 0.0})
                slot["games"] += 1
                slot["scored"] += mine
                slot["allowed"] += theirs
        time.sleep(0.2)
    return acc


def build_nfl(season: int = 2025) -> dict:
    """Points for/against from the season's weekly scoreboards (~26 calls)."""
    dates = [f"{season}&seasontype=2&week={w}" for w in range(1, 19)]
    dates += [f"{season}&seasontype=3&week={w}" for w in range(1, 6)]
    acc = scores_from_scoreboard("football/nfl", dates)
    teams = {k: {"display": v["display"], "games": v["games"],
                 "scored_pg": v["scored"] / v["games"],
                 "allowed_pg": v["allowed"] / v["games"]}
             for k, v in acc.items() if v["games"] > 0}
    return finish_table(teams, season)


def build_soccer_wc(start: datetime.date = datetime.date(2026, 6, 11)) -> dict:
    """WC 2026 tournament GF/GA per team from daily scoreboards."""
    today = datetime.date.today()
    dates = [(start + datetime.timedelta(days=i)).strftime("%Y%m%d")
             for i in range((today - start).days + 1)]
    acc = scores_from_scoreboard("soccer/fifa.world", dates)
    teams = {k: {"display": v["display"], "games": v["games"],
                 "scored_pg": v["scored"] / v["games"],
                 "allowed_pg": v["allowed"] / v["games"]}
             for k, v in acc.items() if v["games"] > 0}
    return finish_table(teams, 2026)


def finish_table(teams: dict, season: int) -> dict:
    """Pure: normalize scored/allowed into off/def ratings vs league average."""
    if not teams:
        return {"season": season, "league_avg": 0.0, "teams": {}}
    total_games = sum(t["games"] for t in teams.values())
    if total_games > 0:
        league_avg = (sum(t["scored_pg"] * t["games"] for t in teams.values())
                      / total_games)
    else:  # no games metadata anywhere — unweighted mean beats an empty table
        league_avg = sum(t["scored_pg"] for t in teams.values()) / len(teams)
    for t in teams.values():
        t["scored_pg"] = round(t["scored_pg"], 2)
        t["allowed_pg"] = round(t["allowed_pg"], 2)
        t["off_rating"] = round(t["scored_pg"] / league_avg, 3)
        t["def_rating"] = round(t["allowed_pg"] / league_avg, 3)
    return {"season": season, "league_avg": round(league_avg, 2), "teams": teams}


# ── Cache I/O ────────────────────────────────────────────────────────────────
def load_all() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text())
        except Exception:
            pass
    return {}


def build(sport: str) -> dict:
    if sport == "nba":
        table = build_from_standings("basketball", "nba")
    elif sport in CORE_SPORTS:
        table = build_core_sport(sport)
    elif sport == "nfl":
        table = build_nfl()
    elif sport == "soccer":
        table = build_soccer_wc()
    else:
        raise ValueError(f"no off/def builder for '{sport}'")
    table["fetched"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data = load_all()
    data[sport] = table
    OUT.write_text(json.dumps(data))
    return table


def get_table(sport: str, max_age_hours: float = 24.0) -> dict:
    """Serve from disk; rebuild only when stale/missing (in-season drift)."""
    data = load_all()
    table = data.get(sport)
    if table:
        try:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(table["fetched"])).total_seconds() / 3600
            if age < max_age_hours:
                return table
        except (KeyError, ValueError):
            pass
    return build(sport)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build/inspect team off/def ratings")
    ap.add_argument("--build", metavar="SPORT", help="one of %s or 'all'" % (SPORTS,))
    ap.add_argument("--show", metavar="SPORT")
    args = ap.parse_args()
    if args.build:
        for s in (SPORTS if args.build == "all" else [args.build]):
            t = build(s)
            print(f"{s}: {len(t['teams'])} teams, league avg {t['league_avg']}")
    if args.show:
        t = load_all().get(args.show) or {}
        rows = sorted((t.get("teams") or {}).values(), key=lambda x: -x["off_rating"])
        for r in rows:
            print(f"{r['display']:<28} off {r['off_rating']:>6}  def {r['def_rating']:>6}"
                  f"  ({r['scored_pg']}-{r['allowed_pg']} pg, {r['games']} gp)")
