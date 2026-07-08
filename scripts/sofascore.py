"""
sofascore.py — client for Sofascore's UNOFFICIAL internal API.

Why: found 2026-07-01 verifying a user's H2H claim (Muchova vs Zhang Shuai)
against the model's read — Sofascore turned out right twice, wrong once. No
official public API or documented terms of service exist for this; this
wraps their internal API the way their own web/app frontend calls it. Use
for on-demand VERIFICATION and cross-checking (recent matches, streaks, H2H,
odds, per-match stats), not as a silent, unverified replacement for the
app's own data-fit models.

IMPORTANT — network reality: this API 403s any request without a real
browser-like User-Agent, and may rate-limit or block datacenter/cloud IP
ranges outright (confirmed blocked from the sandbox this was built in — see
project memory). It works from an ordinary residential connection. If every
call here starts failing, that's the most likely reason, not a code bug.

No API key. Endpoints (undocumented, reverse-engineered by inspection):
  GET /api/v1/search/all?q={name}                      -> resolve a player to an id
  GET /api/v1/team/{id}/events/last/{page}              -> recent results (page 0 = most recent)
  GET /api/v1/event/{eventId}/h2h                       -> {"teamDuel": {homeWins,awayWins,draws}}
  GET /api/v1/event/{eventId}/odds/1/all                -> pre-match markets (fractional odds)
  GET /api/v1/event/{eventId}/statistics                -> per-match stats (aces, serve%, points, games)

Pure parsing functions are separated from the network calls so they're
testable with fixture JSON — no live network access in tests, ever (see
project rule: never call external APIs during debug/test).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional

BASE = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}


def _get(path: str, timeout: int = 10) -> dict:
    """Network call — the only place this module talks to the internet."""
    req = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ── Search ───────────────────────────────────────────────────────────────────
def search_player(name: str) -> Optional[dict]:
    """Resolve a display name to a Sofascore player (team-typed) entity.
    Returns the highest-scored 'team' match, or None if nothing matches."""
    data = _get(f"/search/all?q={urllib.parse.quote(name)}")
    return parse_search_results(data, sport="tennis")


def parse_search_results(data: dict, sport: str = "tennis") -> Optional[dict]:
    """Pure: pick the best player/team match for the given sport."""
    candidates = [
        r["entity"] for r in data.get("results", [])
        if r.get("type") == "team"
        and (r["entity"].get("sport") or {}).get("slug") == sport
        and r["entity"].get("type") == 1  # 1 = individual player, not a doubles pair
    ]
    if not candidates:
        return None
    return candidates[0]  # results are pre-sorted by relevance score


# ── Recent events / streaks ─────────────────────────────────────────────────
def recent_events(team_id: int, pages: int = 1) -> list:
    """Fetch up to `pages` pages of this player's most recent finished
    matches (page 0 = most recent), oldest-appended-last within each page."""
    out = []
    for p in range(pages):
        try:
            data = _get(f"/team/{team_id}/events/last/{p}")
        except Exception:
            break
        out.extend(data.get("events", []))
    return out


def parse_match_result(event: dict, team_id: int) -> Optional[dict]:
    """Pure: simplify one raw event into this player's result in it."""
    home, away = event.get("homeTeam") or {}, event.get("awayTeam") or {}
    if home.get("id") == team_id:
        won, opponent = event.get("winnerCode") == 1, away
    elif away.get("id") == team_id:
        won, opponent = event.get("winnerCode") == 2, home
    else:
        return None
    tourney = event.get("tournament") or {}
    return {
        "opponent": opponent.get("name"),
        "won": won,
        "tournament": tourney.get("name"),
        "surface": tourney.get("groundType"),
        "start_timestamp": event.get("startTimestamp"),
        "status": (event.get("status") or {}).get("type"),
    }


def compute_streak(results: list) -> int:
    """Pure: current streak from a list of parse_match_result() dicts,
    already in most-recent-first order (matches recent_events()'s ordering).
    Positive = win streak, negative = loss streak, 0 if empty."""
    finished = [r for r in results if r.get("status") == "finished"]
    if not finished:
        return 0
    streak = 1 if finished[0]["won"] else -1
    for r in finished[1:]:
        if r["won"] == (streak > 0):
            streak += 1 if streak > 0 else -1
        else:
            break
    return streak


def player_profile(name: str, pages: int = 2) -> Optional[dict]:
    """Convenience: search + recent form + streak in one call."""
    entity = search_player(name)
    if not entity:
        return None
    events = recent_events(entity["id"], pages=pages)
    results = [r for r in (parse_match_result(e, entity["id"]) for e in events) if r]
    finished = [r for r in results if r["status"] == "finished"]
    wins = sum(1 for r in finished if r["won"])
    return {
        "id": entity["id"], "name": entity.get("name"), "country": (entity.get("country") or {}).get("name"),
        "n_recent": len(finished),
        "recent_win_rate": round(wins / len(finished), 3) if finished else None,
        "streak": compute_streak(results),
        "recent_results": results[:10],
    }


# ── Head-to-head ─────────────────────────────────────────────────────────────
def find_shared_event(team_id: int, opponent_name: str, max_pages: int = 5) -> Optional[dict]:
    """Search a player's recent event history for any past meeting with a
    named opponent — needed because there's no direct team-vs-team H2H
    endpoint, only a per-EVENT one. Returns the raw event dict, or None."""
    opponent_name_l = opponent_name.lower()
    for e in recent_events(team_id, pages=max_pages):
        home, away = (e.get("homeTeam") or {}).get("name", ""), (e.get("awayTeam") or {}).get("name", "")
        if opponent_name_l in home.lower() or opponent_name_l in away.lower():
            return e
    return None


def h2h_summary(event_id: int) -> dict:
    """Raw {"homeWins", "awayWins", "draws"} career head-to-head for the two
    players in this specific event (Sofascore's own aggregate, no surface
    breakdown available via this endpoint)."""
    data = _get(f"/event/{event_id}/h2h")
    duel = data.get("teamDuel") or {}
    return {"home_wins": duel.get("homeWins", 0), "away_wins": duel.get("awayWins", 0),
            "draws": duel.get("draws", 0)}


# ── Odds ─────────────────────────────────────────────────────────────────────
def fractional_to_decimal(frac: str) -> Optional[float]:
    """Pure: '11/25' -> 1.44. Returns None for an unparseable string."""
    try:
        num, den = frac.split("/")
        return round(float(num) / float(den) + 1.0, 4)
    except (ValueError, ZeroDivisionError):
        return None


def match_odds(event_id: int) -> list:
    """Pre-match markets for an event, odds converted to decimal."""
    data = _get(f"/event/{event_id}/odds/1/all")
    return parse_odds(data)


def parse_odds(data: dict) -> list:
    """Pure: simplify raw markets into {market, period, choices:[{name,decimal}]}."""
    out = []
    for m in data.get("markets", []):
        out.append({
            "market": m.get("marketName"),
            "period": m.get("marketPeriod"),
            "choices": [
                {"name": c.get("name"), "decimal": fractional_to_decimal(c.get("fractionalValue", ""))}
                for c in m.get("choices", [])
            ],
        })
    return out


# ── Match statistics ─────────────────────────────────────────────────────────
def match_statistics(event_id: int) -> dict:
    """Per-match stats (aces, double faults, serve %, points, games), keyed
    by period ('ALL' = whole match, '1ST'/'2ND'/... = per set)."""
    data = _get(f"/event/{event_id}/statistics")
    return parse_statistics(data)


def parse_statistics(data: dict) -> dict:
    """Pure: flatten Sofascore's nested period/group/item shape into
    {period: {stat_key: {"home": v, "away": v}}}."""
    out = {}
    for period_block in data.get("statistics", []):
        period = period_block.get("period", "?")
        stats = {}
        for group in period_block.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if key:
                    stats[key] = {"home": item.get("homeValue"), "away": item.get("awayValue")}
        out[period] = stats
    return out


# ── Soccer players (props engine) ────────────────────────────────────────────
# Soccer players are 'player'-typed search entities (tennis players are
# 'team'-typed — Sofascore models a tennis player AS a team). Endpoints:
#   GET /api/v1/player/{id}/events/last/{page}                -> recent matches
#   GET /api/v1/event/{eventId}/player/{playerId}/statistics  -> per-match line
def search_soccer_player(name: str) -> Optional[dict]:
    """Resolve a display name to a Sofascore SOCCER player entity."""
    data = _get(f"/search/all?q={urllib.parse.quote(name)}")
    return parse_soccer_player_search(data)


def parse_soccer_player_search(data: dict) -> Optional[dict]:
    """Pure: best football player match from search results."""
    candidates = [
        r["entity"] for r in data.get("results", [])
        if r.get("type") == "player"
        and ((r["entity"].get("team") or {}).get("sport") or {}).get("slug") == "football"
    ]
    return candidates[0] if candidates else None


def soccer_player_events(player_id: int, pages: int = 1) -> list:
    """Most recent FINISHED matches this player's team played (page 0 first)."""
    out = []
    for p in range(pages):
        try:
            data = _get(f"/player/{player_id}/events/last/{p}")
        except Exception:
            break
        out.extend(e for e in data.get("events", [])
                   if (e.get("status") or {}).get("type") == "finished")
    out.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
    return out


def soccer_player_match_stats(event_id: int, player_id: int) -> dict:
    """This player's stat line in one match ({} if he didn't play)."""
    try:
        data = _get(f"/event/{event_id}/player/{player_id}/statistics")
    except Exception:
        return {}
    return data.get("statistics") or {}


# Per-match Sofascore keys -> prop stat. A goal counts as a shot on target,
# but Sofascore's onTargetScoringAttempt already includes it — no double add.
def extract_soccer_stat(stats: dict, stat: str) -> Optional[float]:
    """Pure: pull one prop stat from a Sofascore player match-stats dict.
    Returns None when the player has no minutes (didn't play)."""
    if not stats or not stats.get("minutesPlayed"):
        return None
    on_target = stats.get("onTargetScoringAttempt", 0) or 0
    off_target = stats.get("shotOffTarget", 0) or 0
    blocked = stats.get("blockedScoringAttempt", 0) or 0
    table = {
        "shots": on_target + off_target + blocked,
        "shots_on_target": on_target,
        "goals": stats.get("goals", 0) or 0,
        "assists": stats.get("goalAssist", 0) or 0,
        "tackles": stats.get("totalTackle", 0) or 0,
        "passes": stats.get("totalPass", 0) or 0,
    }
    val = table.get(stat)
    return float(val) if val is not None else None


def soccer_player_gamelog(name: str, stat: str, pages: int = 1, max_games: int = 12) -> Optional[dict]:
    """Player name -> {player, entries, values} where entries = per-match
    (iso_date, stat) most recent first, matches he didn't play excluded.
    Dates let callers dedupe against other sources. None if name unresolved."""
    import datetime as _dt
    entity = search_soccer_player(name)
    if not entity:
        return None
    entries = []
    for ev in soccer_player_events(entity["id"], pages=pages)[:max_games]:
        v = extract_soccer_stat(soccer_player_match_stats(ev["id"], entity["id"]), stat)
        if v is None:
            continue
        ts = ev.get("startTimestamp")
        date = (_dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat()
                if ts else "")
        entries.append((date, v))
    return {"player": entity.get("name", name), "player_id": entity["id"],
            "entries": entries, "values": [v for _, v in entries]}
