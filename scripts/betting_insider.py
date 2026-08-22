#!/usr/bin/env python3
"""
betting_insider.py — free Pinnacle open/current + real line movement (CLV).

Source: thebettinginsider.com's Next.js route `/api/market-props/signals`, which
is unauthenticated even though the rest of the site is a $29.99/mo paywall
(verified 2026-08-19). What it gives that nothing else in this app had:

  * PINNACLE line + odds, OPENING **and** CURRENT — 96/96 coverage on MLB.
    The whole sharp-anchor engine is built on Pinnacle and currently pays
    Odds API quota for it; this is the same number for free.
  * REAL line movement (opening vs current) — 80/96 props moved today. This is
    the first genuine CLV feed the app has ever had (global rule 4, which has
    been dead since it was written).
  * Backtested fade systems with sample sizes (wins/losses/hit rate/ROI).

⚠️ TWO TRAPS, both guarded below — do not "simplify" them away:

  1. `consensus_over_pct` is NOT public money. It tracks `sleeper_over_pct`
     exactly, and `prizepicks_entries` is 0 on every single row. A value of
     100 means "a handful of Sleeper entries all took the over", not "100% of
     the public". 33/96 rows read exactly 100 for this reason. It is therefore
     NOT a valid feed for the contrarian rule (7) and is exposed as
     `consensus_pct` + `consensus_reliable=False` so no caller can mistake it.
  2. The site's own /public-betting PAGE renders every split as 50%/50% when
     logged out — placeholder, not data. Never scrape that page.

Coverage: mlb, nfl, nba, nhl ONLY. No soccer, no tennis — callers for those
must fall back to the app's own engines rather than receive a stub.

Unofficial API, same footing as sofascore.py / linemate.py: on-demand only,
never a hot loop, degrade rather than fabricate.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

BASE = "https://www.thebettinginsider.com/api/market-props/signals"

SPORTS: tuple[str, ...] = ("mlb", "nfl", "nba", "nhl")

# A Sleeper-driven consensus needs more than a token sample before it means
# anything. The feed exposes no entry count, so an exact 0/100 reading is
# treated as unusable rather than as a screaming contrarian signal.
_DEGENERATE_CONSENSUS = (0, 100)

TIMEOUT = 25


class BettingInsiderError(RuntimeError):
    """Feed unreachable, or returned something that isn't the expected shape."""


def _get(url: str, timeout: int = TIMEOUT) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise BettingInsiderError(f"{url} -> HTTP {e.code}") from e
    except Exception as e:
        raise BettingInsiderError(f"{url} -> {e}") from e


def american_to_decimal(o: Optional[float]) -> Optional[float]:
    """American -> decimal. None-safe: a missing price stays missing."""
    if o is None:
        return None
    o = float(o)
    if o == 0:
        return None
    return round((o / 100 + 1) if o > 0 else (100 / -o + 1), 4)


def implied(o: Optional[float]) -> Optional[float]:
    """American -> implied probability (still vigged)."""
    if o is None:
        return None
    o = float(o)
    if o == 0:
        return None
    return round((100 / (o + 100)) if o > 0 else ((-o) / (-o + 100)), 6)


def devig_pinnacle(over_odds: Optional[float],
                   under_odds: Optional[float]) -> Optional[dict]:
    """Two-way devig of Pinnacle's own price = the fair probability the app's
    sharp-anchor engine wants. Returns None unless BOTH sides are present —
    a one-sided devig is a fabricated number."""
    io, iu = implied(over_odds), implied(under_odds)
    if io is None or iu is None:
        return None
    tot = io + iu
    if tot <= 0:
        return None
    return {"over": round(io / tot, 4), "under": round(iu / tot, 4),
            "vig_pct": round((tot - 1) * 100, 2)}


def _movement(opening: Optional[float], current: Optional[float]) -> Optional[float]:
    """Percentage move in DECIMAL price from open to now.

    Positive = the price drifted out (you'd now get paid more than at open, so
    the market moved AWAY from this side). Negative = money came in on it."""
    od, cd = american_to_decimal(opening), american_to_decimal(current)
    if od is None or cd is None or od == 0:
        return None
    return round((cd - od) / od * 100, 2)


def _normalise(p: dict) -> dict:
    cons = p.get("consensus_over_pct")
    # Guard trap #1 (see module docstring).
    reliable = (cons is not None
                and cons not in _DEGENERATE_CONSENSUS
                and bool(p.get("prizepicks_entries")))

    return {
        "player": p.get("player_name"),
        "position": p.get("position"),
        "team": p.get("team_name"),
        "game_id": p.get("game_id"),
        "game_time": p.get("game_time"),
        "home_team": p.get("home_team"),
        "away_team": p.get("away_team"),
        "market": p.get("stat_type"),
        "line": p.get("current_line"),
        "opening_line": p.get("opening_line"),
        "line_moved": (p.get("opening_line") != p.get("current_line")
                       if p.get("opening_line") is not None else None),

        # Book price (American in, decimal out for Stake comparison).
        "over_decimal": american_to_decimal(p.get("current_over_odds")),
        "under_decimal": american_to_decimal(p.get("current_under_odds")),

        # ── The sharp anchor, free ──
        "pinnacle_line": p.get("pinnacle_line"),
        "pinnacle_over_decimal": american_to_decimal(p.get("pinnacle_over_odds")),
        "pinnacle_under_decimal": american_to_decimal(p.get("pinnacle_under_odds")),
        "pinnacle_fair": devig_pinnacle(p.get("pinnacle_over_odds"),
                                        p.get("pinnacle_under_odds")),

        # ── Real CLV (global rule 4) ──
        "over_move_pct": _movement(p.get("opening_over_odds"),
                                   p.get("current_over_odds")),
        "under_move_pct": _movement(p.get("opening_under_odds"),
                                    p.get("current_under_odds")),
        "pinnacle_over_move_pct": _movement(p.get("pinnacle_opening_over_odds"),
                                            p.get("pinnacle_over_odds")),

        # ── Consensus: exposed but explicitly NOT trusted ──
        "consensus_pct": cons,
        "consensus_reliable": reliable,
        "consensus_note": (None if reliable else
                           "Sleeper small-sample, not public money — do NOT use "
                           "for the contrarian rule"),

        # ── Their backtested fade system, with its sample size ──
        "fade_side": p.get("fade_bet_side") or None,
        "fade_hit_rate": p.get("fade_perf_hit_rate"),
        "fade_sample": p.get("fade_perf_total"),
        "fade_roi": p.get("fade_perf_roi"),
        "signal": p.get("signal") or None,
        "signal_side": p.get("signal_side") or None,
    }


def signals(sport: str) -> list[dict]:
    """Today's props for one sport, normalised. Empty list = nothing posted
    today (out of season / preseason), which is not an error."""
    sp = sport.lower().strip()
    if sp not in SPORTS:
        raise BettingInsiderError(
            f"unsupported sport {sport!r} — this feed covers only "
            f"{', '.join(SPORTS)} (no soccer, no tennis)")
    raw = _get(f"{BASE}?sport={sp}")
    if not isinstance(raw, dict) or not raw.get("success"):
        raise BettingInsiderError(f"{sp}: unexpected payload shape")
    props = raw.get("props") or []
    if not isinstance(props, list):
        raise BettingInsiderError(f"{sp}: props was {type(props).__name__}, expected list")
    return [_normalise(p) for p in props if isinstance(p, dict)]


def sharp_moves(sport: str, min_move_pct: float = 5.0) -> list[dict]:
    """Props whose PINNACLE price moved meaningfully since open.

    Pinnacle moving is the sharp signal worth reading — a soft book drifting is
    often just position management. Sorted by absolute move, biggest first.
    """
    out = [s for s in signals(sport)
           if s["pinnacle_over_move_pct"] is not None
           and abs(s["pinnacle_over_move_pct"]) >= min_move_pct]
    return sorted(out, key=lambda s: -abs(s["pinnacle_over_move_pct"]))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Betting Insider free signals feed")
    ap.add_argument("sport", choices=SPORTS)
    ap.add_argument("--moves", action="store_true",
                    help="only props whose Pinnacle price moved >= 5%%")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = sharp_moves(a.sport) if a.moves else signals(a.sport)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{len(rows)} props\n")
        for s in rows[:25]:
            fair = s["pinnacle_fair"]
            fair_s = f"{fair['over']:.3f}" if fair else "n/a"
            print(f"{str(s['player'])[:20]:<20} {str(s['market'])[:18]:<18} "
                  f"{str(s['line']):<5} pinn_fair_over={fair_s:<6} "
                  f"move={s['pinnacle_over_move_pct']}%  "
                  f"fade={s['fade_side'] or '-'}({s['fade_hit_rate']}% n={s['fade_sample']})")
