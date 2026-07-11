#!/usr/bin/env python3
"""
opponent_adjust.py — "they do not play equal to all teams."

Turns the opponent into a multiplier on a player's projected stat: how much
of that stat does THIS opponent allow, relative to the league average? A
bunkered defense shrinks the mean, a sieve inflates it. Every factor is
computed from real allowed-per-game data, shrunk toward 1.0 by sample size
(n/(n+4)) and clamped to [0.6, 1.5] so a hot fortnight can't triple a
projection. No data on the opponent -> factor 1.0, labeled "no_data" —
flagged, never guessed.

Per-sport sources (free, cached on disk):
  soccer     WC 2026 player cache (data/wc_player_stats.json) aggregated into
             per-team allowed shots/SOT/goals/assists/fouls — zero new fetches.
  nba/wnba   ESPN core API avgPointsAllowed per team (data/opp_defense_*.json,
             24h cache). Full factor on points/threes; HALF factor on
             rebounds/assists/steals/blocks (points-allowed is a pace proxy
             there, and it's labeled as such).
  nfl        Season boxscore aggregation (netPassingYards / rushingYards each
             team allowed per game) -> data/opp_defense_nfl.json. Pass-D
             scales passing/receiving props, rush-D scales rushing props.
"""
from __future__ import annotations

import datetime
import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import fetch_wc_player_stats as wc_fetch

DATA = Path(__file__).parent.parent / "data"
_UA = {"User-Agent": "Mozilla/5.0"}

SHRINK_GAMES = 4                 # factor pulled toward 1.0: weight n/(n+4)
FACTOR_MIN, FACTOR_MAX = 0.6, 1.5

SOCCER_STATS = ("shots", "shots_on_target", "goals", "assists", "fouls")
# basketball: stats that scale fully with points-allowed vs half (pace proxy)
BBALL_FULL = {"points", "threes"}
BBALL_HALF = {"rebounds", "assists", "steals", "blocks"}
NFL_PASS = {"passing_yards", "receiving_yards", "receptions", "passing_tds"}
NFL_RUSH = {"rushing_yards", "rushing_attempts"}


def _get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def shrink_factor(raw: float, n_games: int) -> float:
    """Pure: shrink a raw allowed/league ratio toward 1.0 by sample size,
    then clamp. 5 WC games never swing a projection like an 82-game season."""
    k = n_games / (n_games + SHRINK_GAMES)
    return max(FACTOR_MIN, min(FACTOR_MAX, 1.0 + (raw - 1.0) * k))


# ── Soccer: allowed table straight from the WC player cache ─────────────────
def wc_defense_table(cache: dict) -> dict:
    """Pure: {"teams": {norm_team: {"games": n, "allowed": {stat: per_game}}},
    "league_avg": {stat: per_game}} — a team's ALLOWED line is what opposing
    players produced against it, summed per match."""
    per_event_team: dict = {}   # (event_id, team) -> stat totals + opponent
    for slot in cache.get("players", {}).values():
        team = slot.get("team") or ""
        for g in slot.get("games", []):
            key = (g["event_id"], team)
            acc = per_event_team.setdefault(
                key, {s: 0.0 for s in SOCCER_STATS} | {"opponent": g.get("opponent", "")})
            for s in SOCCER_STATS:
                acc[s] += float(g.get(s, 0.0))
    allowed: dict = {}
    for (_eid, _team), acc in per_event_team.items():
        opp = wc_fetch.norm_name(acc["opponent"])
        if not opp:
            continue
        slot = allowed.setdefault(opp, {"games": 0, **{s: 0.0 for s in SOCCER_STATS}})
        slot["games"] += 1
        for s in SOCCER_STATS:
            slot[s] += acc[s]
    total_games = sum(t["games"] for t in allowed.values()) or 1
    league_avg = {s: sum(t[s] for t in allowed.values()) / total_games
                  for s in SOCCER_STATS}
    teams = {name: {"games": t["games"],
                    "allowed": {s: t[s] / t["games"] for s in SOCCER_STATS}}
             for name, t in allowed.items() if t["games"] > 0}
    return {"teams": teams, "league_avg": league_avg}


def soccer_factor(opponent: str, stat: str, cache: Optional[dict] = None) -> dict:
    """Opponent multiplier for a soccer prop from the WC allowed table."""
    if stat not in SOCCER_STATS:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"'{stat}' has no allowed-table (sofascore-only stat)"}
    table = wc_defense_table(cache if cache is not None else wc_fetch.load_cache())
    team = table["teams"].get(wc_fetch.norm_name(opponent))
    avg = table["league_avg"].get(stat) or 0.0
    if not team or avg <= 0:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"'{opponent}' not in WC 2026 allowed table — unadjusted"}
    raw = team["allowed"][stat] / avg
    return {"opponent": opponent, "factor": round(shrink_factor(raw, team["games"]), 3),
            "raw_factor": round(raw, 3), "games": team["games"],
            "allowed_per_game": round(team["allowed"][stat], 2),
            "league_avg": round(avg, 2), "basis": "wc_2026_allowed"}


# ── Basketball: avgPointsAllowed per team (ESPN core API, cached 24h) ───────
def _bball_cache_path(sport: str) -> Path:
    return DATA / f"opp_defense_{sport}.json"


def fetch_basketball_defense(sport: str, season: Optional[int] = None) -> dict:
    """Network: every team's avgPointsAllowed -> disk cache."""
    season = season or datetime.date.today().year
    league = {"nba": "nba", "wnba": "wnba"}[sport]
    teams_raw = _get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/teams")
    teams = teams_raw["sports"][0]["leagues"][0]["teams"]
    out = {}
    for t in teams:
        tid, name = t["team"]["id"], t["team"]["displayName"]
        try:
            stats = _get("https://sports.core.api.espn.com/v2/sports/basketball/leagues/"
                         f"{league}/seasons/{season}/types/2/teams/{tid}/statistics")
        except Exception:
            continue
        gp, pts_allowed = None, None
        for cat in (stats.get("splits") or {}).get("categories", []):
            for s in cat.get("stats", []):
                if s.get("name") == "avgPointsAllowed":
                    pts_allowed = s.get("value")
                if s.get("name") == "gamesPlayed":
                    gp = s.get("value")
        if pts_allowed:
            out[wc_fetch.norm_name(name)] = {"display": name,
                                             "points_allowed": float(pts_allowed),
                                             "games": int(gp or 0)}
        time.sleep(0.15)
    cache = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "season": season, "teams": out}
    _bball_cache_path(sport).write_text(json.dumps(cache))
    return cache


def load_basketball_defense(sport: str, max_age_hours: float = 24.0) -> dict:
    p = _bball_cache_path(sport)
    if p.exists():
        try:
            cache = json.loads(p.read_text())
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(cache["fetched"])).total_seconds() / 3600
            if age < max_age_hours:
                return cache
        except Exception:
            pass
    return fetch_basketball_defense(sport)


def basketball_factor(sport: str, opponent: str, stat: str,
                      cache: Optional[dict] = None) -> dict:
    """Pure given a cache: points-allowed ratio; half-weight off-stat proxy."""
    if stat not in BBALL_FULL | BBALL_HALF:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"no defense-vs-{stat} feed — unadjusted"}
    cache = cache if cache is not None else load_basketball_defense(sport)
    teams = cache.get("teams", {})
    team = teams.get(wc_fetch.norm_name(opponent))
    if team is None:  # partial name ("Aces" for "Las Vegas Aces")
        want = set(wc_fetch.norm_name(opponent).split())
        team = next((v for k, v in teams.items() if want <= set(k.split())), None)
    vals = [v["points_allowed"] for v in teams.values()]
    if not team or not vals:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"'{opponent}' not in {sport.upper()} defense table — unadjusted"}
    league_avg = sum(vals) / len(vals)
    raw = team["points_allowed"] / league_avg
    factor = shrink_factor(raw, team.get("games", 0))
    basis = "points_allowed"
    if stat in BBALL_HALF:  # pace proxy only — half the effect, say so
        factor = 1.0 + (factor - 1.0) * 0.5
        basis = "points_allowed_pace_proxy_half"
    return {"opponent": team.get("display", opponent), "factor": round(factor, 3),
            "raw_factor": round(raw, 3), "games": team.get("games", 0),
            "allowed_per_game": round(team["points_allowed"], 1),
            "league_avg": round(league_avg, 1), "basis": basis}


# ── NFL: pass-D / rush-D allowed from season boxscores (built once) ─────────
NFL_CACHE = DATA / "opp_defense_nfl.json"


def parse_nfl_boxscore_teams(summary: dict) -> Optional[list[dict]]:
    """Pure: one game summary -> [{team, pass_yards, rush_yards}] both sides."""
    teams = (summary.get("boxscore") or {}).get("teams") or []
    if len(teams) != 2:
        return None
    out = []
    for t in teams:
        stats = {s.get("name"): s.get("displayValue") for s in t.get("statistics") or []}
        try:
            out.append({"team": (t.get("team") or {}).get("displayName") or "",
                        "pass_yards": float(stats["netPassingYards"]),
                        "rush_yards": float(stats["rushingYards"])})
        except (KeyError, TypeError, ValueError):
            return None
    return out


def _get_retry(url: str, tries: int = 3) -> Optional[dict]:
    """ESPN throttles bulk crawls — back off and retry instead of dropping
    the game on the floor (a silent skip starved the first table build)."""
    for attempt in range(tries):
        try:
            return _get(url)
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_nfl_defense(season: int = 2025) -> dict:
    """Network (heavy, ~285 summaries): aggregate what each team ALLOWED
    (= the other side's yards) per game. RESUMABLE — processed event ids are
    persisted, rerunning only fetches what's missing."""
    cache = {}
    if NFL_CACHE.exists():
        try:
            cache = json.loads(NFL_CACHE.read_text())
        except Exception:
            cache = {}
    if cache.get("season") != season:
        cache = {}
    seen = set(cache.get("event_ids") or [])
    raw = cache.get("raw") or {}

    weeks = [(2, w) for w in range(1, 19)] + [(3, w) for w in range(1, 6)]
    for stype, week in weeks:
        sb = _get_retry("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
                        f"scoreboard?dates={season}&seasontype={stype}&week={week}")
        if sb is None:
            continue
        for ev in sb.get("events", []):
            eid = str(ev.get("id"))
            state = ((ev.get("status") or {}).get("type") or {}).get("state")
            if state != "post" or eid in seen:
                continue
            summary = _get_retry("https://site.api.espn.com/apis/site/v2/sports/"
                                 f"football/nfl/summary?event={eid}")
            sides = parse_nfl_boxscore_teams(summary) if summary else None
            if not sides:
                continue
            for me, other in ((0, 1), (1, 0)):
                key = wc_fetch.norm_name(sides[me]["team"])
                slot = raw.setdefault(key, {"display": sides[me]["team"],
                                            "games": 0, "pass_yards": 0.0,
                                            "rush_yards": 0.0})
                slot["games"] += 1
                slot["pass_yards"] += sides[other]["pass_yards"]
                slot["rush_yards"] += sides[other]["rush_yards"]
            seen.add(eid)
            time.sleep(0.4)
    teams = {k: {"display": v["display"], "games": v["games"],
                 "pass_allowed": v["pass_yards"] / v["games"],
                 "rush_allowed": v["rush_yards"] / v["games"]}
             for k, v in raw.items() if v["games"] > 0}
    cache = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "season": season, "event_ids": sorted(seen), "raw": raw, "teams": teams}
    NFL_CACHE.write_text(json.dumps(cache))
    return cache


def load_nfl_defense() -> dict:
    """Season aggregates don't rot mid-offseason — no age check, build if absent."""
    if NFL_CACHE.exists():
        try:
            return json.loads(NFL_CACHE.read_text())
        except Exception:
            pass
    return fetch_nfl_defense()


def nfl_factor(opponent: str, stat: str, cache: Optional[dict] = None) -> dict:
    """Pass-D scales passing/receiving props, rush-D scales rushing props."""
    if stat in NFL_PASS:
        col = "pass_allowed"
    elif stat in NFL_RUSH:
        col = "rush_allowed"
    else:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"no defense-vs-{stat} feed (tackles/sacks are matchup-neutral here)"}
    cache = cache if cache is not None else load_nfl_defense()
    teams = cache.get("teams", {})
    team = teams.get(wc_fetch.norm_name(opponent))
    if team is None:
        want = set(wc_fetch.norm_name(opponent).split())
        team = next((v for k, v in teams.items() if want <= set(k.split())), None)
    vals = [v[col] for v in teams.values()]
    if not team or not vals:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"'{opponent}' not in NFL defense table — unadjusted"}
    league_avg = sum(vals) / len(vals)
    raw = team[col] / league_avg
    return {"opponent": team.get("display", opponent),
            "factor": round(shrink_factor(raw, team.get("games", 0)), 3),
            "raw_factor": round(raw, 3), "games": team.get("games", 0),
            "allowed_per_game": round(team[col], 1),
            "league_avg": round(league_avg, 1),
            "basis": {"pass_allowed": "pass_defense", "rush_allowed": "rush_defense"}[col],
            "season": cache.get("season")}


# ── Dispatcher ───────────────────────────────────────────────────────────────
def opponent_factor(sport: str, opponent: str, stat: str) -> dict:
    """One entry point for the props engine. Always returns a factor dict;
    factor 1.0 + basis 'no_data' when nothing real backs an adjustment."""
    try:
        if sport == "soccer":
            return soccer_factor(opponent, stat)
        if sport in ("nba", "wnba"):
            return basketball_factor(sport, opponent, stat)
        if sport == "nfl":
            return nfl_factor(opponent, stat)
    except Exception as e:
        return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
                "note": f"defense table unavailable ({e}) — unadjusted"}
    return {"opponent": opponent, "factor": 1.0, "basis": "no_data",
            "note": f"no opponent model for '{sport}'"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build/inspect opponent defense tables")
    ap.add_argument("--build-nfl", action="store_true", help="aggregate season boxscores (~3 min)")
    ap.add_argument("--build-bball", choices=["nba", "wnba"], help="fetch points-allowed table")
    args = ap.parse_args()
    if args.build_nfl:
        c = fetch_nfl_defense()
        print(f"NFL defense table: {len(c['teams'])} teams, season {c['season']}")
    if args.build_bball:
        c = fetch_basketball_defense(args.build_bball)
        print(f"{args.build_bball.upper()} defense table: {len(c['teams'])} teams")
