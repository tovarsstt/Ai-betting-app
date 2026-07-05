#!/usr/bin/env python3
"""
fetch_stake_odds.py — pull STAKE's own sportsbook prices via OddsPapi.

Why this path: Stake has no official API, it is NOT on the-odds-api, and the
community scrapers need anti-bot/captcha bypass (fragile + against Stake ToS).
OddsPapi (api.oddspapi.io) licenses the feed and carries Stake among 350+
books; the free tier (250 req/month) covers daily matchday pulls.

Until Stake prices flow, the app is already Stake-portable: every pick carries
`min_odds` — bet on Stake only if its on-screen price >= that floor.

Setup (once):
  1. Sign up at oddspapi.io -> put ODDSPAPI_KEY=... in .env
  2. python3 scripts/fetch_stake_odds.py --discover
     -> prints the bookmaker keys OddsPapi actually serves on a live fixture;
        find Stake's exact key (e.g. "stake"), put ODDSPAPI_STAKE_KEY=... in .env
  3. python3 scripts/fetch_stake_odds.py --raw
     -> dumps one fixture's full Stake odds payload to data/stake_raw.json so
        the market map below can be verified against REAL field names.

REAL runs only — never called in dev/test (project rule). Every request is
one unit of the 250/month free quota.

Schema note (do not trust blindly): per OddsPapi docs the odds response nests
bookmakerOdds.{bookmaker}.markets.{marketId}.outcomes.{outcomeId}.price with
opaque market ids. _extract_1x2 below is defensive: it returns None and says
what it saw instead of guessing. First --raw dump = ground truth to finish it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.oddspapi.io/v4"
RAW_DUMP = Path(__file__).parent.parent / "data" / "stake_raw.json"


def _get(path: str, **params) -> dict | list:
    key = os.environ.get("ODDSPAPI_KEY")
    if not key:
        raise SystemExit("ODDSPAPI_KEY not set — sign up at oddspapi.io (free tier), "
                         "add it to .env. No key = no Stake feed; min_odds floors "
                         "in bank_builder still make every pick Stake-portable.")
    qs = urllib.parse.urlencode({"apiKey": key, **params})
    with urllib.request.urlopen(f"{BASE}/{path}?{qs}", timeout=20) as resp:
        return json.load(resp)


def discover(sport_hint: str = "soccer") -> None:
    """One live fixture -> which bookmaker keys OddsPapi serves (find Stake's)."""
    sports = _get("sports")
    print(f"[discover] sports returned: {len(sports) if isinstance(sports, list) else 'dict'}")
    sport = next((s for s in sports if sport_hint in str(s).lower()), None) \
        if isinstance(sports, list) else None
    print(f"[discover] matched sport entry: {json.dumps(sport)[:200]}")
    fixtures = _get("fixtures", sportId=sport.get("id") if isinstance(sport, dict) else "")
    fx = (fixtures or [None])[0] if isinstance(fixtures, list) else None
    if not isinstance(fx, dict):
        raise SystemExit(f"[discover] no fixtures — raw: {json.dumps(fixtures)[:300]}")
    odds = _get("odds", fixtureId=fx.get("id") or fx.get("fixtureId"))
    books = list((odds.get("bookmakerOdds") or {}).keys()) if isinstance(odds, dict) else []
    print(f"[discover] fixture {fx.get('id')} bookmaker keys ({len(books)}):")
    for b in sorted(books):
        marker = "  <== STAKE?" if "stake" in b.lower() else ""
        print(f"    {b}{marker}")


def dump_raw(bookmaker: str) -> None:
    """Save one fixture's full payload — ground truth for the market map."""
    sports = _get("sports")
    sport = next((s for s in sports if "soccer" in str(s).lower()), {}) \
        if isinstance(sports, list) else {}
    fixtures = _get("fixtures", sportId=sport.get("id", ""))
    fx = (fixtures or [{}])[0] if isinstance(fixtures, list) else {}
    odds = _get("odds", fixtureId=fx.get("id") or fx.get("fixtureId"), bookmaker=bookmaker)
    RAW_DUMP.write_text(json.dumps({"fixture": fx, "odds": odds}, indent=1))
    print(f"[raw] wrote {RAW_DUMP} — verify market/outcome ids, then finish _extract_1x2")


def _extract_1x2(odds: dict, bookmaker: str) -> list | None:
    """Best-effort 1X2 from the documented shape. Refuses to guess: returns
    None (with a summary printed) when the market can't be identified."""
    book = (odds.get("bookmakerOdds") or {}).get(bookmaker)
    if not isinstance(book, dict):
        print(f"[extract] bookmaker '{bookmaker}' absent; have: "
              f"{list((odds.get('bookmakerOdds') or {}).keys())}")
        return None
    markets = book.get("markets") or {}
    for mid, m in markets.items():
        outs = (m or {}).get("outcomes") or {}
        prices = [o.get("price") for o in outs.values() if isinstance(o, dict)]
        if len(prices) == 3 and all(isinstance(p, (int, float)) for p in prices):
            print(f"[extract] market {mid} has 3 priced outcomes — candidate 1X2: {prices}")
            return prices
    print(f"[extract] no 3-outcome market found; market ids: {list(markets)[:10]}")
    return None


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="list bookmaker keys (1-3 requests)")
    ap.add_argument("--raw", action="store_true", help="dump one Stake fixture payload")
    ap.add_argument("--bookmaker", default=os.environ.get("ODDSPAPI_STAKE_KEY", "stake"))
    args = ap.parse_args()
    if args.discover:
        discover()
    elif args.raw:
        dump_raw(args.bookmaker)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _main()
