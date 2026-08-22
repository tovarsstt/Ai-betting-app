#!/usr/bin/env python3
"""
line_shop.py — find the outlier price across 32 books, free and unmetered.

The old sharp scanner asked the Odds API for THREE books
(`pinnacle,draftkings,fanduel`) and looked for a gap between them. A gap needs
two of those three to price the same market, so on a normal slate it compared
one game and reported "market efficient" — which was never a finding about the
market, only about the coverage. It also cost quota on every refresh.

Linemate already publishes up to 32 books per market for free
(scripts/linemate.py). With that many prices the useful question changes: not
"do two books disagree" but "is the BEST price out of line with what everyone
else thinks".

Method:
  1. Devig each book's own two-way price to a fair probability. Comparing raw
     prices across books is biased — a 2% margin book and a 6% margin book
     disagree by construction, before either has an opinion.
  2. Take the MEDIAN fair probability across books as the consensus. Median, not
     mean, so one stale or fat-fingered book cannot drag the reference.
  3. Score every book's actual price against that consensus.

An outlier is then real: the market's own collective fair estimate says this
price pays more than it should. Edge is reported in fair-probability points,
which is comparable across markets in a way a raw price gap is not.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import linemate as lmt  # noqa: E402

MIN_BOOKS = 4          # below this a "consensus" is just an opinion
DEFAULT_MIN_EDGE = 0.02


def _dec(side: Optional[dict]) -> Optional[float]:
    cur = (side or {}).get("current") or {}
    d = (cur.get("odds") or {}).get("decimal")
    try:
        d = float(d)
    except (TypeError, ValueError):
        return None
    return d if d > 1.0 else None


def devig_pair(over: Optional[float], under: Optional[float]) -> Optional[float]:
    """Fair probability of the OVER, with the book's margin removed.

    Both sides required — a one-sided devig is a fabricated number.
    """
    if not over or not under:
        return None
    io, iu = 1.0 / over, 1.0 / under
    tot = io + iu
    return io / tot if tot > 0 else None


def scan_market(trend: dict, min_books: int = MIN_BOOKS,
                min_edge: float = DEFAULT_MIN_EDGE) -> Optional[dict]:
    """One market across every book carrying it."""
    market = trend.get("market") or {}
    books = market.get("books") or {}
    side = trend.get("outcome") or "over"
    other = "under" if side == "over" else "over"

    fair, prices = {}, {}
    for name, sides in books.items():
        if not isinstance(sides, dict):
            continue
        a, b = _dec(sides.get(side)), _dec(sides.get(other))
        f = devig_pair(a, b)
        if f is None:
            continue
        fair[name] = f
        prices[name] = a
    if len(fair) < min_books:
        return None

    consensus = statistics.median(fair.values())
    if consensus <= 0:
        return None
    best_book = max(prices, key=lambda k: prices[k])
    best_price = prices[best_book]
    # What the consensus says this side is worth, versus what the best book pays.
    fair_price = 1.0 / consensus
    edge = consensus - (1.0 / best_price)      # fair-probability points

    if edge < min_edge:
        return None
    player = (trend.get("player") or {}).get("fullName")
    team = (trend.get("team") or {}).get("code")
    return {
        "game": trend.get("gameId"),
        "subject": player or (trend.get("team") or {}).get("name"),
        "team": team,
        "market": market.get("name"),
        "line": trend.get("line"),
        "side": side,
        "best_book": best_book,
        "best_price": round(best_price, 3),
        "consensus_fair_prob": round(consensus, 4),
        "consensus_fair_price": round(fair_price, 3),
        "edge_prob_points": round(edge * 100, 2),
        "books_compared": len(fair),
        "min_odds": round(1.05 / consensus, 2),
        "why": (f"{len(fair)} books devigged; median fair "
                f"{consensus*100:.1f}% vs {best_book} paying {best_price} "
                f"({(1/best_price)*100:.1f}% implied)"),
    }


def scan(league: str, min_books: int = MIN_BOOKS,
         min_edge: float = DEFAULT_MIN_EDGE) -> dict:
    try:
        # RAW payload: the normalised rows keep only the best price,
        # and comparing books needs every book's price.
        trends = lmt.trends_raw(league)
    except lmt.LinemateError as e:
        return {"error": "FEED_UNAVAILABLE", "league": league, "note": str(e)}

    out, considered, thin = [], 0, 0
    for t in trends:
        m = (t.get("market") or {}).get("books") or {}
        if len(m) < min_books:
            thin += 1
            continue
        considered += 1
        row = scan_market(t, min_books, min_edge)
        if row:
            out.append(row)
    out.sort(key=lambda r: -r["edge_prob_points"])
    return {
        "league": league,
        "markets_seen": len(trends),
        "markets_compared": considered,
        "skipped_too_few_books": thin,
        "min_books": min_books,
        "min_edge_prob_points": round(min_edge * 100, 2),
        "outliers": out,
        # Say WHY there is nothing, so an empty result is never mistaken for
        # "the market is efficient" when it actually means "we saw one book".
        "note": ("no price is out of line with the multi-book consensus"
                 if considered and not out else
                 "not enough books quoting to form a consensus — this is a "
                 "COVERAGE result, not a market-efficiency finding"
                 if not considered else None),
    }


def scan_sport(sport: str, **kw) -> dict:
    leagues = lmt.SPORT_LEAGUES.get(sport.upper(), ())
    if not leagues:
        return {"error": "UNCOVERED_SPORT", "sport": sport,
                "note": f"Linemate covers {', '.join(sorted(lmt.SPORT_LEAGUES))}"}
    rows, seen, compared = [], 0, 0
    for lg in leagues:
        r = scan(lg, **kw)
        if "error" in r:
            continue
        rows.extend(r["outliers"])
        seen += r["markets_seen"]
        compared += r["markets_compared"]
    rows.sort(key=lambda r: -r["edge_prob_points"])
    return {"sport": sport.upper(), "leagues": list(leagues),
            "markets_seen": seen, "markets_compared": compared,
            "outliers": rows,
            "note": None if rows else
                    ("no outliers against consensus" if compared else
                     "no league in this sport had enough books quoting — "
                     "coverage, not efficiency")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a Linemate league (mlb, epl…) or a sport (MLB, SOCCER)")
    ap.add_argument("--min-books", type=int, default=MIN_BOOKS)
    ap.add_argument("--min-edge", type=float, default=DEFAULT_MIN_EDGE)
    a = ap.parse_args()
    fn = scan if a.target.islower() and a.target in lmt.LEAGUES else scan_sport
    print(json.dumps(fn(a.target, min_books=a.min_books, min_edge=a.min_edge), indent=1))
