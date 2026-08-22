#!/usr/bin/env python3
"""
feed_health.py — is every upstream feed still reachable, and is its data current?

The bug this exists to prevent: ESPN's edge started 403ing browser-spoofed
User-Agents, `fetch_tennis_ratings.py` exited non-zero on every run, and the
tennis ranks sat frozen at 2026-07-18 for a month while the engine kept pricing
matches at full confidence. Nothing anywhere noticed. `data_freshness.py` knew
the data was old but not WHY, and nothing knew the source was dead.

This joins the two halves:
  * REACHABILITY — can we still fetch from the host at all, right now?
  * FRESHNESS    — how old is the file that fetch actually writes?

so a red line reads "tennis: source DEAD (403) + data 32d old" instead of a
silent STALE that looks like nobody has run the refresh lately.

Probes are cheap GETs against the real endpoints, with the SAME headers the
fetchers use — a probe that passes where the fetcher fails is worse than no
probe. Never call a quota-metered API here (CLAUDE.md): every host below is
free and unmetered.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

TIMEOUT = 12


@dataclass(frozen=True)
class Feed:
    """One upstream source, the script that consumes it, and how to probe it."""
    name: str
    script: str
    url: str
    feeds: tuple[str, ...]      # data_freshness keys this source keeps current
    note: str = ""


# NB on User-Agent: ESPN's site.api 403s ANY "Mozilla/..." string and serves
# urllib's default fine. The probes deliberately send no UA so they fail exactly
# where the fetchers would. Do not "fix" a red ESPN line by adding a browser UA.
FEEDS: tuple[Feed, ...] = (
    Feed("espn-tennis-ranks", "fetch_tennis_ratings.py",
         "https://sports.core.api.espn.com/v2/sports/tennis/leagues/atp/rankings",
         ("tennis",), "ATP+WTA official ranks"),
    Feed("tennis-data-form", "fetch_tennis_form.py",
         "http://www.tennis-data.co.uk/2026/2026.xlsx",
         ("tennis_form",), "H2H / form / psych / clutch"),
    Feed("sackmann-serve", "fetch_tennis_serve_stats.py",
         "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/2026.csv",
         ("tennis_serve",), "ATP serve / break-point stats"),
    Feed("football-data-club", "fetch_club_results.py",
         "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
         ("soccer_club",), "big-5 league results"),
    Feed("espn-nfl", "fetch_nfl_rosters.py",
         "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams",
         ("nfl",), "NFL rosters / churn"),
    Feed("espn-wnba", "fetch_wnba_form.py",
         "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard",
         ("wnba",), "WNBA form"),
    Feed("mlb-statsapi", "fetch_mlb_data.py",
         "https://statsapi.mlb.com/api/v1/teams?sportId=1",
         ("mlb",), "MLB games / probables"),
    Feed("linemate", "linemate.py",
         "https://api.linemate.io/api/mlb/v3/teams/rankings",
         (), "32-book prices, injuries, ATS records"),
    Feed("betting-insider", "betting_insider.py",
         "https://www.thebettinginsider.com/api/market-props/signals?sport=mlb",
         (), "free Pinnacle open/current — the CLV feed"),
)


def probe(feed: Feed, timeout: int = TIMEOUT) -> dict:
    """One reachability check. Never raises — a dead feed is data, not an error."""
    try:
        req = urllib.request.Request(feed.url)   # deliberately no User-Agent
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            # A 200 that returns nothing is still a broken feed.
            empty = not r.read(64)
        if empty:
            return {"reachable": False, "http": code, "error": "empty response"}
        return {"reachable": True, "http": code, "error": None}
    except urllib.error.HTTPError as ex:
        hint = ""
        if ex.code == 403 and "espn.com" in feed.url:
            hint = " (ESPN blocks browser-spoofed User-Agents — do NOT add one)"
        return {"reachable": False, "http": ex.code, "error": f"HTTP {ex.code}{hint}"}
    except Exception as ex:                        # DNS, TLS, timeout, refused
        return {"reachable": False, "http": None, "error": str(ex)[:120]}


def check(feeds: tuple[Feed, ...] = FEEDS, freshness: Optional[dict] = None) -> dict:
    """Probe every feed in parallel and join it to data freshness.

    Returns {"worst": .., "feeds": {name: {...}}}. `worst` is DEAD if any source
    is unreachable, STALE if all are up but some data is past its budget.
    """
    if freshness is None:
        try:
            import data_freshness as dfr
            freshness = dfr.audit()["sports"]
        except Exception:
            freshness = {}

    with ThreadPoolExecutor(max_workers=len(feeds) or 1) as pool:
        results = list(pool.map(probe, feeds))

    out: dict = {}
    for feed, res in zip(feeds, results):
        ages = {k: freshness.get(k, {}).get("age_days") for k in feed.feeds}
        statuses = [freshness.get(k, {}).get("status") for k in feed.feeds]
        stale = any(s in ("STALE", "MISSING") for s in statuses)
        out[feed.name] = {
            "script": feed.script,
            "note": feed.note,
            "url": feed.url,
            **res,
            "data_ages_days": ages,
            "data_stale": stale,
            # The line that would have caught the month-long tennis freeze.
            "verdict": ("DEAD" if not res["reachable"]
                        else "STALE" if stale else "OK"),
        }

    verdicts = [v["verdict"] for v in out.values()]
    worst = ("DEAD" if "DEAD" in verdicts
             else "STALE" if "STALE" in verdicts else "OK")
    return {"worst": worst, "feeds": out}


if __name__ == "__main__":
    import sys
    rep = check()
    icon = {"OK": "ok  ", "STALE": "STALE", "DEAD": "DEAD"}
    print(f"worst: {rep['worst']}\n")
    for name, v in rep["feeds"].items():
        ages = ", ".join(f"{k}={d}d" for k, d in v["data_ages_days"].items() if d is not None)
        print(f"  {icon[v['verdict']]:<6} {name:<20} {v['script']:<28} "
              f"{v['error'] or ''}{(' | ' + ages) if ages else ''}")
    # Non-zero exit on a dead source so a cron/CI run fails loudly.
    sys.exit(1 if rep["worst"] == "DEAD" else 0)
