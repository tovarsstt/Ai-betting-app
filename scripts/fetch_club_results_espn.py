#!/usr/bin/env python3
"""
fetch_club_results_espn.py — current-season club results, before football-data has them.

football-data.co.uk is the primary result source and it LAGS at the start of a
season. Verified 2026-08-22: /mmz4281/2627/E0.csv did not exist yet (E1, E2, E3
did), while ESPN already had **6 completed Premier League matches**, 2 Serie A
and 2 Ligue 1. So the fitted ratings were carrying zero matches from the new
season for four of the five big leagues — no promoted sides, no new form, and
relegated clubs still in the pool.

This fills that window from ESPN (free, no key) and merges into the same
club_results.csv the fitters read, so `fit_club_ratings` picks it up unchanged.
Once football-data catches up both sources agree and the merge de-duplicates on
(date, home, away).

Team names are mapped to football-data's ABBREVIATED convention ("Espanol",
"Ath Madrid", "Man United") because that is what the ratings key on. A name that
cannot be mapped confidently is SKIPPED with a warning rather than written under
a new spelling — a duplicate club under two names silently splits its history.

Run: python3 scripts/fetch_club_results_espn.py [--since 2026-07-01]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "soccer" / "club_results.csv"

# ESPN league slug -> the league name used in club_results.csv
LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
}
# UEFA cups: the ONLY source of cross-league matches, which is what lets
# fit_club_ratings pool a joint "Europe" fit whose scales mean something
# between leagues. Clubs outside the big-5 pool (Porto, Ajax, Celtic…) are
# accepted VERBATIM under their ESPN name — football-data never covers these
# competitions, so there is no second spelling to collide with; the hard
# anti-split guard still applies to any name that resolves into the pool.
UEFA_LEAGUES = {
    "uefa.champions": "Champions League",
    "uefa.europa": "Europa League",
}
TIMEOUT = 25


def _get(url: str) -> dict:
    req = urllib.request.Request(url)      # no UA — ESPN refuses spoofed ones
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _rating_pool() -> dict:
    """Every club name the fitted ratings already know, across all leagues."""
    try:
        doc = json.loads((DATA / "soccer" / "club_ratings.json").read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    pool = {}
    for lg in (doc.get("leagues") or {}).values():
        pool.update(lg.get("teams") or {})
    return pool


def fetch(since: str, until: str | None = None) -> list[dict]:
    import edge_api as e                   # reuse resolve_club's alias logic
    pool = _rating_pool()
    until = until or date.today().isoformat()
    rows, unmapped = [], set()

    # ESPN rejects long date spans (a ~14-month query returns an empty body,
    # verified 2026-08-31) — chunk into windows of at most 120 days.
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    windows = []
    cur = start
    while cur <= end:
        w_end = min(cur + timedelta(days=119), end)
        windows.append((cur, w_end))
        cur = w_end + timedelta(days=1)

    for slug, league in {**LEAGUES, **UEFA_LEAGUES}.items():
        is_uefa = slug in UEFA_LEAGUES
        events = []
        for w_start, w_end in windows:
            span = f"{w_start.isoformat().replace('-', '')}-{w_end.isoformat().replace('-', '')}"
            try:
                d = _get("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                         f"{slug}/scoreboard?dates={span}&limit=400")
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
                continue
            events.extend(d.get("events", []))
        for ev in events:
            st = (ev.get("status") or {}).get("type") or {}
            if not st.get("completed"):
                continue
            comp = (ev.get("competitions") or [{}])[0]
            sides = {}
            for c in comp.get("competitors", []):
                try:
                    sides[c.get("homeAway")] = (
                        (c.get("team") or {}).get("displayName"), int(c.get("score")))
                except (TypeError, ValueError):
                    pass
            if "home" not in sides or "away" not in sides:
                continue
            (hn, hs), (an, as_) = sides["home"], sides["away"]
            # Map to the abbreviated names the ratings key on. Refuse rather
            # than invent a second spelling for a club we already track.
            hk = e.resolve_club(hn, pool) if pool else None
            ak = e.resolve_club(an, pool) if pool else None
            if is_uefa:
                # UEFA-only clubs enter the pool under their ESPN name.
                hk = hk or hn
                ak = ak or an
            elif not hk or not ak:
                unmapped.add(hn if not hk else an)
                continue
            # HARD GUARD: only ever write a name the ratings ALREADY use.
            # resolve_club can return a token-subset match, and on 2026-08-22
            # that let "Atl. Madrid" and "Rayo Vallecano" into the file as NEW
            # clubs beside "Ath Madrid" and "Vallecano" — one club's history
            # silently split in two, and the next refit baked the split in.
            if not is_uefa and (hk not in pool or ak not in pool):
                unmapped.add(hk if hk not in pool else ak)
                continue
            rows.append({"date": ev.get("date", "")[:10],
                         "home_team": hk, "away_team": ak,
                         "home_score": hs, "away_score": as_,
                         "neutral": "FALSE", "league": league})
    return rows, sorted(unmapped)


def merge(rows: list[dict], path: Path = OUT) -> dict:
    existing, fields = [], ["date", "home_team", "away_team", "home_score",
                            "away_score", "neutral", "league"]
    if path.exists():
        with path.open() as f:
            rd = csv.DictReader(f)
            fields = rd.fieldnames or fields
            existing = list(rd)
    seen = {(r["date"], r["home_team"], r["away_team"]) for r in existing}
    added = [r for r in rows if (r["date"], r["home_team"], r["away_team"]) not in seen]
    merged = sorted(existing + [{k: str(r.get(k, "")) for k in fields} for r in added],
                    key=lambda r: r["date"])
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(merged)
    return {"added": len(added), "total": len(merged)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=(date.today() - timedelta(days=60)).isoformat())
    ap.add_argument("--until", default=None)
    a = ap.parse_args()
    rows, unmapped = fetch(a.since, a.until)
    out = merge(rows)
    if unmapped:
        out["unmapped_skipped"] = unmapped
        out["warning"] = ("these clubs are not in the fitted ratings — likely "
                          "newly promoted; add them to _CLUB_ALIASES or they "
                          "stay unpriced")
    print(json.dumps({"fetched": len(rows), **out}, indent=1))
