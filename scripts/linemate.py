#!/usr/bin/env python3
"""
linemate.py — free, key-less market + trend feed (linemate.io public API).

Why this exists: the app's only multi-book price source was the-odds-api, which
is quota-capped (500 req/month) and covers 3 books. Linemate's web app talks to
an OPEN, unauthenticated JSON API — the same one that powers linemate.io — and
it carries things the app had no source for at all:

  * 32 sportsbooks per market (vs 3), so "best price" is a real shop, not a guess
  * quantified trend signals (RECENT_FORM / HEAD_TO_HEAD) with real hit records
  * team injury lists and ATS / total-over hit records per team

NOT a CLV source, despite appearances: every book side carries an `opening`
field and it is null on every row (checked 729/729 book-sides, 2026-08-19).
`opening_decimal` / `line_move_pct` below are wired to it so they light up
if Linemate ever populates it, and until then they are honestly None —
global rule 4 still has no free feed behind it.

Verified 2026-08-19: no API key, no cookie, no signup. Endpoints are
  https://api.linemate.io/api/{league}/v3/teams/rankings
  https://api.linemate.io/api/{league}/v3/teams/injuries
  https://api.linemate.io/api/{league}/v1/trends/straights

Unofficial API (same footing as scripts/sofascore.py): on-demand only, never in
a hot loop, and every consumer must tolerate it going away. Nothing here invents
a number — a missing field comes back as None so callers can print "n/a".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

BASE = "https://api.linemate.io/api"

# Verified live 2026-08-19. Tennis is NOT covered by Linemate — callers asking
# for it must fall back to the app's own tennis engine rather than get a stub.
LEAGUES: dict[str, str] = {
    "mlb": "MLB",
    "nfl": "NFL",
    "nba": "NBA",
    "nhl": "NHL",
    "wnba": "WNBA",
    "ncaaf": "NCAAF",
    "ncaab": "NCAAB",
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "ucl": "Champions League",
    "mls": "MLS",
    "liga-mx": "Liga MX",
    "brazil-serie-a": "Brasileirão",
}

# Which app sport maps to which Linemate league slugs.
SPORT_LEAGUES: dict[str, tuple[str, ...]] = {
    "MLB": ("mlb",),
    "NFL": ("nfl",),
    "NBA": ("nba",),
    "NHL": ("nhl",),
    "WNBA": ("wnba",),
    "SOCCER": ("epl", "laliga", "seriea", "bundesliga", "ligue1",
               "ucl", "mls", "liga-mx", "brazil-serie-a"),
}

TIMEOUT = 20


class LinemateError(RuntimeError):
    """Feed unreachable or returned something that isn't the expected shape."""


def _get(path: str, timeout: int = TIMEOUT) -> Any:
    """GET one Linemate path. No browser User-Agent — several sports edges
    (ESPN's included) actively refuse spoofed browser agents, and Linemate
    serves the default agent fine, so there is nothing to gain by faking one."""
    url = f"{BASE}/{path.lstrip('/')}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise LinemateError(f"{url} -> HTTP {e.code}") from e
    except Exception as e:  # network, DNS, bad JSON
        raise LinemateError(f"{url} -> {e}") from e


def _check_league(league: str) -> str:
    lg = league.lower().strip()
    if lg not in LEAGUES:
        raise LinemateError(
            f"unknown league {league!r} — known: {', '.join(sorted(LEAGUES))}")
    return lg


# ── Injuries ─────────────────────────────────────────────────────────────────

def injuries(league: str) -> dict[str, list[dict]]:
    """{TEAM_CODE: [{name, position, injury, status}]} — global rule 6 input.

    Linemate keys this by team code and includes coach's-decision inactives,
    which is exactly the preseason signal ESPN's injury feed leaves out.
    """
    lg = _check_league(league)
    raw = _get(f"{lg}/v3/teams/injuries")
    if not isinstance(raw, dict):
        raise LinemateError(f"{lg} injuries: expected object, got {type(raw).__name__}")
    out: dict[str, list[dict]] = {}
    for code, players in raw.items():
        if not isinstance(players, list):
            continue
        out[code] = [{
            "name": p.get("fullName"),
            "position": p.get("position"),
            "injury": p.get("injury"),
            "status": p.get("status"),
        } for p in players if isinstance(p, dict)]
    return out


# ── Team form / ATS records ──────────────────────────────────────────────────

def team_records(league: str) -> dict[str, dict]:
    """{TEAM_CODE: {name, games, ats_hit_rate, total_over_hit_rate, streak}}.

    ATS and total-over hit rates are real settled counts from Linemate, not a
    model output — they belong in the profile block (rule 13) as cited stats.
    """
    lg = _check_league(league)
    raw = _get(f"{lg}/v3/teams/rankings")
    if not isinstance(raw, list):
        raise LinemateError(f"{lg} rankings: expected list, got {type(raw).__name__}")
    out: dict[str, dict] = {}
    for t in raw:
        if not isinstance(t, dict) or not t.get("code"):
            continue
        hr = t.get("hitRecords") or {}

        def rate(key: str) -> Optional[float]:
            rec = hr.get(key) or {}
            hits, games = rec.get("hits"), rec.get("games")
            if not games:
                return None
            return round(hits / games, 4)

        out[t["code"]] = {
            "name": t.get("name"),
            "city": t.get("city"),
            "games": t.get("gamesPlayed"),
            "ats_hit_rate": rate("againstTheSpread"),
            "home_ats_hit_rate": rate("homeAgainstTheSpread"),
            "away_ats_hit_rate": rate("awayAgainstTheSpread"),
            "total_over_hit_rate": rate("totalOver"),
            "streak": t.get("streak"),
        }
    return out


# ── Trends (prices across 32 books + opening lines + hit records) ────────────

def _prices(side: dict | None) -> dict:
    """Pull {decimal, american, value} out of one book's side, tolerating the
    nulls Linemate uses for markets a book hasn't posted."""
    cur = (side or {}).get("current") or {}
    odds = cur.get("odds") or {}
    return {"decimal": odds.get("decimal"), "american": odds.get("american"),
            "value": cur.get("value")}


def _opening(side: dict | None) -> dict:
    op = (side or {}).get("opening") or {}
    odds = op.get("odds") or {}
    return {"decimal": odds.get("decimal"), "american": odds.get("american"),
            "value": op.get("value")}


def trends_raw(league: str) -> list[dict]:
    """The UNNORMALISED trend payload, books and all.

    `trends()` flattens each row to the single best price, which is the right
    shape for reading a card but throws away the per-book prices. Anything that
    compares books (line_shop.py) needs the raw thing.
    """
    lg = _check_league(league)
    raw = _get(f"{lg}/v1/trends/straights")
    if not isinstance(raw, list):
        raise LinemateError(f"{lg} trends: expected list, got {type(raw).__name__}")
    return [t for t in raw if isinstance(t, dict)]


def trends(league: str) -> list[dict]:
    """Today's featured trends, normalised.

    Each item: game, player/team, market, line, the side Linemate flags, the
    BEST decimal price across every book carrying it, the opening price for
    line movement (CLV), and the quantified signals behind the trend.
    """
    lg = _check_league(league)
    raw = _get(f"{lg}/v1/trends/straights")
    if not isinstance(raw, list):
        raise LinemateError(f"{lg} trends: expected list, got {type(raw).__name__}")

    out: list[dict] = []
    for t in raw:
        if not isinstance(t, dict):
            continue
        market = t.get("market") or {}
        books = market.get("books") or {}
        outcome = t.get("outcome")  # "over" / "under" — the flagged side

        best_book, best_dec, open_dec = None, None, None
        for name, sides in books.items():
            if not isinstance(sides, dict):
                continue
            p = _prices(sides.get(outcome))
            if p["decimal"] and (best_dec is None or p["decimal"] > best_dec):
                best_dec, best_book = p["decimal"], name
            if open_dec is None:
                open_dec = _opening(sides.get(outcome))["decimal"]

        player = t.get("player") or {}
        team = t.get("team") or {}
        opp = t.get("opposingTeam") or {}

        out.append({
            "game_id": t.get("gameId"),
            "starts_at": t.get("timestamp"),
            "league": lg,
            "subject": player.get("fullName") or team.get("name"),
            "position": player.get("position"),
            "team": team.get("code") or team.get("name"),
            "opponent": opp.get("code") or opp.get("name"),
            "home": t.get("home"),
            "market": market.get("name"),
            "market_type": market.get("type"),
            "line": t.get("line"),
            "side": outcome,
            "best_book": best_book,
            "best_decimal": best_dec,
            "opening_decimal": open_dec,
            # Positive = price drifted OUT (better for us) since open; negative
            # = the market moved onto it. Currently always None — see the
            # module docstring: Linemate never fills `opening`.
            "line_move_pct": (round((best_dec - open_dec) / open_dec * 100, 2)
                              if best_dec and open_dec else None),
            "books_offering": len(books),
            "signals": [{
                "type": s.get("type"),
                "description": s.get("description"),
                "hit_rate": (s.get("hitRecord") or {}).get("hitRate"),
                "games": (s.get("hitRecord") or {}).get("games"),
                "hits": (s.get("hitRecord") or {}).get("hits"),
            } for s in (t.get("signals") or []) if isinstance(s, dict)],
        })
    return out


def trends_for_sport(sport: str) -> list[dict]:
    """Every trend across the leagues that make up one app sport. A league that
    is dark today (or erroring) is skipped, never faked."""
    slugs = SPORT_LEAGUES.get(sport.upper(), ())
    out: list[dict] = []
    for slug in slugs:
        try:
            out.extend(trends(slug))
        except LinemateError:
            continue
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Linemate free market/trend feed")
    ap.add_argument("league", help=f"one of: {', '.join(sorted(LEAGUES))}")
    ap.add_argument("--what", choices=["trends", "injuries", "records"],
                    default="trends")
    ap.add_argument("--json", action="store_true", help="raw JSON out")
    a = ap.parse_args()

    data = {"trends": trends, "injuries": injuries,
            "records": team_records}[a.what](a.league)

    if a.json:
        print(json.dumps(data, indent=2))
    elif a.what == "trends":
        for t in data:
            sig = t["signals"][0]["description"] if t["signals"] else "—"
            print(f"{t['subject']:<22} {t['market']:<42} {t['side']:<5} "
                  f"{t['line']:<6} @{t['best_decimal']} ({t['best_book']}) "
                  f"move={t['line_move_pct']}%  {sig}")
    else:
        print(json.dumps(data, indent=2)[:4000])
