#!/usr/bin/env python3
"""
market_context.py — Linemate + Betting Insider joined into the pick flow.

Both feeds are UNOFFICIAL APIs whose own rule (global heuristic 17) is
"on-demand only, never a hot loop". Calling them straight from /predict would
break that and put a network round-trip on every prediction, so everything here
goes through a disk-backed TTL cache: repeat picks on the same slate read the
cached slate, the upstreams see one request per TTL window, and a restart does
not re-hammer them.

What it adds to a pick:
  * ATS / home-ATS / total-over hit records per team      (rule 13 profiles)
  * injuries, including preseason coach's-decision inactives (rule 6)
  * Pinnacle open-vs-current movement                      (rule 4 CLV)

TEAM MATCHING IS THE DANGEROUS PART. The app says "Baltimore Ravens"; Linemate
says {code: BAL, name: "Ravens", city: "Baltimore"} for NFL and "Brighton & Hove
Albion FC" for a club the app calls "Brighton". Attaching the WRONG team's
injuries to a pick is worse than attaching none, so `match_team` resolves only
on an unambiguous match and returns None otherwise — never a best guess.

Nothing here can fail a prediction: every entry point degrades to None plus a
note, so an upstream going dark costs context, never the pick.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

import betting_insider as tbi
import linemate as lmt

CACHE_DIR = Path(__file__).parent.parent / "data" / "_cache"

# Seconds. Trends and sharp moves chase live prices, so they expire fast;
# rosters and season-long ATS records barely move within a day.
TTL = {"trends": 600, "sharp": 900, "injuries": 3600, "records": 3600}

# Club suffixes/prefixes that carry no identity — "Arsenal FC" is "Arsenal".
_NOISE = re.compile(r"\b(fc|afc|cf|sc|ac|club|de|futbol|football)\b")
# Dots are dropped WITHOUT a space so "F.C." collapses to the token "fc" and the
# noise filter can see it; every other symbol becomes a separator so
# "Brighton & Hove" splits into words rather than fusing.
_DOTS = re.compile(r"\.")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


# ── Disk-backed TTL cache ───────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    # Collapse anything that isn't plainly alphanumeric. Dots are stripped too:
    # the separator substitution already prevents traversal (the result is one
    # path component), but a key of ".." must never become a filename of "..".
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", key).strip("_") or "key"
    return CACHE_DIR / f"{safe}.json"


def cached(key: str, ttl: int, producer: Callable[[], Any]) -> tuple[Any, dict]:
    """Return (value, meta). Serves fresh cache without calling `producer`.

    On a producer failure with a STALE cache present we return the stale value
    rather than nothing — old ATS records still beat no ATS records, and the
    meta says exactly how old so the caller can be honest about it.
    """
    path = _cache_path(key)
    now = time.time()
    stale: Any = None
    stale_age: Optional[float] = None

    if path.exists():
        try:
            blob = json.loads(path.read_text())
            age = now - blob["stored_at"]
            if age < ttl:
                return blob["value"], {"from_cache": True, "age_s": round(age),
                                       "stale": False, "error": None}
            stale, stale_age = blob["value"], age
        except Exception:
            pass  # unreadable cache is the same as no cache

    try:
        value = producer()
    except Exception as e:
        if stale is not None:
            return stale, {"from_cache": True, "age_s": round(stale_age or 0),
                           "stale": True, "error": str(e)[:120]}
        return None, {"from_cache": False, "age_s": None, "stale": False,
                      "error": str(e)[:120]}

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stored_at": now, "value": value}))
    except Exception:
        pass  # a cache we can't write is a slow path, not a failure
    return value, {"from_cache": False, "age_s": 0, "stale": False, "error": None}


# ── Team matching ───────────────────────────────────────────────────────────

def normalise(name: str) -> str:
    """Lowercase, drop punctuation and club-noise words, collapse spaces."""
    s = _DOTS.sub("", (name or "").lower())
    s = _PUNCT.sub(" ", s)
    s = _NOISE.sub(" ", s)
    return " ".join(s.split())


def match_team(query: str, candidates: dict[str, dict]) -> Optional[str]:
    """Resolve an app team name to a Linemate key, or None.

    `candidates` is {key: {"name":.., "city":.., ...}} as returned by
    linemate.team_records. Three passes, each requiring a UNIQUE winner:

      1. exact normalised match on the key, the name, or "city name"
      2. one side's tokens being a subset of the other's
         ("Brighton" ⊂ "Brighton Hove Albion")
      3. otherwise None — an ambiguous match is not a match

    Returning None is a correct, safe answer. Guessing is not.
    """
    if not query or not candidates:
        return None
    q = normalise(query)
    if not q:
        return None

    forms: dict[str, set[str]] = {}
    for key, meta in candidates.items():
        name = (meta or {}).get("name") or ""
        city = (meta or {}).get("city") or ""
        forms[key] = {normalise(key), normalise(name),
                      normalise(f"{city} {name}").strip()} - {""}

    exact = [k for k, f in forms.items() if q in f]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None                      # genuinely ambiguous — refuse

    qt = set(q.split())
    subset = [k for k, f in forms.items()
              if any(qt and (qt <= set(v.split()) or set(v.split()) <= qt) for v in f)]
    return subset[0] if len(subset) == 1 else None


# ── Context builders ────────────────────────────────────────────────────────

def _leagues_for(sport: str) -> tuple[str, ...]:
    return lmt.SPORT_LEAGUES.get(sport.upper(), ())


def team_context(sport: str, team: str) -> dict:
    """ATS record + injuries for one team, or an honest 'no context' payload.

    Searches every Linemate league that maps to this sport, so a soccer club is
    found without the caller having to know which league it plays in.
    """
    out: dict = {"team": team, "sport": sport.upper(), "matched": None,
                 "league": None, "ats": None, "injuries": None, "note": None}
    leagues = _leagues_for(sport)
    if not leagues:
        out["note"] = f"Linemate does not cover {sport.upper()} — no external context"
        return out

    for lg in leagues:
        records, rmeta = cached(f"records_{lg}", TTL["records"],
                                lambda lg=lg: lmt.team_records(lg))
        if not records:
            continue
        key = match_team(team, records)
        if not key:
            continue

        injuries, _ = cached(f"injuries_{lg}", TTL["injuries"],
                             lambda lg=lg: lmt.injuries(lg))
        # An EMPTY list is not the same as a clean bill of health. Linemate lists
        # all 23 EPL clubs with zero injuries each — it simply has no soccer
        # injury coverage — and reporting that as "none ruled out" would claim a
        # fully fit Premier League squad, which is essentially never true. If the
        # WHOLE league's feed is empty, treat it as uncovered (None) rather than
        # as data. Self-correcting: it flips back the day Linemate populates it.
        covered = any(v for v in (injuries or {}).values())
        out.update({
            "matched": key,
            "league": lg,
            "ats": records[key],
            "injuries": (injuries or {}).get(key) if covered else None,
            "injuries_covered": covered,
            "cache_age_s": rmeta.get("age_s"),
            "stale": rmeta.get("stale", False),
        })
        if not covered:
            out["note"] = (f"Linemate publishes no injury data for {lg} — "
                           f"absence of listed injuries is NOT a clean bill of health")
        return out

    out["note"] = (f"'{team}' not matched in Linemate ({', '.join(leagues)}) — "
                   f"no external context (not an error; name may differ or the "
                   f"league may be uncovered)")
    return out


def sharp_context(sport: str, min_move_pct: float = 5.0) -> dict:
    """Pinnacle open-vs-current movers for a sport (rule 4). Betting Insider
    covers mlb/nfl/nba/nhl only; anything else says so rather than stubbing."""
    sp = sport.lower()
    if sp not in tbi.SPORTS:
        return {"sport": sp, "moves": None,
                "note": f"Betting Insider covers only {', '.join(tbi.SPORTS)} "
                        f"— no CLV feed for {sp}"}
    moves, meta = cached(f"sharp_{sp}", TTL["sharp"],
                         lambda: tbi.sharp_moves(sp, min_move_pct))
    return {"sport": sp, "moves": moves, "count": len(moves or []),
            "cache_age_s": meta.get("age_s"), "stale": meta.get("stale", False),
            "note": meta.get("error")}


def match_context(sport: str, home: str, away: str) -> dict:
    """Everything the external feeds know about one fixture. Used by /predict."""
    return {
        "home": team_context(sport, home),
        "away": team_context(sport, away),
        "sharp_moves": sharp_context(sport),
        "sources": ["linemate.io", "thebettinginsider.com"],
        "caveat": "external stats are CITED CONTEXT, not model output — a trend "
                  "still has to clear the value gate (rule 1) and never overrides "
                  "the engine (rule 15)",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="External market context for a fixture")
    ap.add_argument("sport")
    ap.add_argument("home")
    ap.add_argument("away", nargs="?", default=None)
    a = ap.parse_args()
    if a.away:
        print(json.dumps(match_context(a.sport, a.home, a.away), indent=2)[:6000])
    else:
        print(json.dumps(team_context(a.sport, a.home), indent=2)[:4000])
