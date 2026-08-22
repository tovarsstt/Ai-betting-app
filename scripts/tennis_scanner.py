#!/usr/bin/env python3
"""
tennis_scanner.py — find the +EV tennis markets on a board, automatically.

Why this exists: on 2026-08-19 the value on the Cincinnati board was not in any
moneyline — every ML was priced through the model's floor — it was in the
UNDERDOG games handicaps (O'Connell +5.5 @1.46, Bejlek +6.5 @1.60; both landed).
That was found by hand, in conversation. Hand-found edges do not scale and are
not there when you need them. This scans every market on every match and returns
the ones that clear the gates, ranked the way the user ranks: WINNING FIRST.

What it prices per match (rule 5 — no auto-moneyline):
  * moneyline, both sides
  * games handicap, EVERY line the book posts, BOTH sides
  * games totals, over and under
  * set handicap (-1.5 sets = must win 2-0) — named explicitly so it can never
    be confused with the games handicap (rule 20)
  * "wins at least one set", both players

Ranking is win probability first, EV second (rule 0). A market only surfaces if
it clears BOTH gates: positive EV against the price, and a win probability worth
staking. Nothing is invented — a market with no price is skipped, and a player
with no serve stats produces no opinion at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402
import win_simulator as wsim  # noqa: E402

# A pick must clear BOTH: real edge AND a win rate worth having.
MIN_EV = 0.02          # 2% — below this the model's own error swamps the edge
MIN_WIN_PROB = 0.50    # winning is king: never surface a sub-coinflip "value" bet


def _ev(prob: float, decimal: float) -> float:
    return prob * decimal - 1.0


def _row(match: str, market: str, prob: float, price: float,
         note: Optional[str] = None) -> dict:
    verdict, vnote = wsim._verdict(prob)
    return {
        "match": match,
        "market": market,
        "win_prob": round(prob, 4),
        "price": price,
        "ev_pct": round(_ev(prob, price) * 100, 1),
        "min_odds": round(1.05 / prob, 2) if prob > 0 else None,
        "verdict": verdict,
        "note": note or vnote,
    }


def scan_match(match: dict) -> list[dict]:
    """Price every market on one match. `match` shape:

        {"player_a","player_b","match_prob_a"?,"best_of"?,
         "ml": {"a": 1.11, "b": 7.40},
         "games_handicap": {"-4.5": {"a": 1.39, "b": 2.80}, ...},
         "games_total":    {"21.5": {"over": 1.90, "under": 1.90}},
         "set_handicap":   {"-1.5": {"a": 1.36, "b": 2.90}},
         "wins_a_set":     {"a": 1.05, "b": 1.80}}

    Every price is optional; only what the book actually posts gets priced.
    """
    a, b = match["player_a"], match["player_b"]
    name = f"{a} v {b}"
    best_of = int(match.get("best_of", 3))

    d = tgm.predict(a, b, best_of=best_of,
                    target_match_prob_a=match.get("match_prob_a"))
    if not isinstance(d, dict) or "serve_point_prob" not in d:
        return [{"match": name, "market": None, "error": "NO_DATA",
                 "note": "no serve stats for one or both players — no opinion"}]

    ka, kb = d["player_a"], d["player_b"]
    p_a = d["match_prob"][ka]
    rows: list[dict] = []

    ml = match.get("ml") or {}
    if ml.get("a"):
        rows.append(_row(name, f"{a} ML", p_a, float(ml["a"])))
    if ml.get("b"):
        rows.append(_row(name, f"{b} ML", 1 - p_a, float(ml["b"])))

    # Games handicap — every posted line, BOTH sides. The dog side is where the
    # 2026-08-19 edge lived, and it only shows up if you actually price it.
    ladder = d.get("game_handicap_ladder") or {}
    for line, prices in (match.get("games_handicap") or {}).items():
        cover = ladder.get(str(line)) or ladder.get(f"{float(line):+g}")
        if cover is None:
            continue
        if (prices or {}).get("a"):
            rows.append(_row(name, f"{a} {line} games", cover, float(prices["a"])))
        if (prices or {}).get("b"):
            rows.append(_row(name, f"{b} +{abs(float(line))} games",
                             1 - cover, float(prices["b"])))

    for line, prices in (match.get("games_total") or {}).items():
        gt = tgm.predict(a, b, games_line=float(line), best_of=best_of,
                         target_match_prob_a=match.get("match_prob_a")).get("games_total") or {}
        if (prices or {}).get("over") and gt.get("p_over"):
            rows.append(_row(name, f"OVER {line} games", gt["p_over"], float(prices["over"])))
        if (prices or {}).get("under") and gt.get("p_under"):
            rows.append(_row(name, f"UNDER {line} games", gt["p_under"], float(prices["under"])))

    # SET handicap — spelled out. -1.5 SETS needs a 2-0 win; a 2-1 win loses it.
    sh = d.get("set_handicap") or {}
    for line, prices in (match.get("set_handicap") or {}).items():
        if abs(float(line)) != 1.5:
            continue
        if (prices or {}).get("a") and sh.get("a_minus_1_5_sets") is not None:
            rows.append(_row(name, f"{a} -1.5 SETS (must win 2-0)",
                             sh["a_minus_1_5_sets"], float(prices["a"]),
                             note="a 2-1 win LOSES this — not the games handicap"))
        if (prices or {}).get("b") and sh.get("a_minus_1_5_sets") is not None:
            rows.append(_row(name, f"{b} +1.5 SETS", 1 - sh["a_minus_1_5_sets"],
                             float(prices["b"])))

    was = match.get("wins_a_set") or {}
    if was or True:
        import tennis_live as tlive
        ps = tlive.implied_set_prob(p_a, best_of)
        if was.get("a"):
            rows.append(_row(name, f"{a} wins a set", 1 - (1 - ps) ** 2, float(was["a"])))
        if was.get("b"):
            rows.append(_row(name, f"{b} wins a set", 1 - ps ** 2, float(was["b"])))
    return rows


def scan_board(board: list[dict], min_ev: float = MIN_EV,
               min_win: float = MIN_WIN_PROB) -> dict:
    """Scan every match; return the plays that clear both gates, win-prob first."""
    priced, errors = [], []
    for m in board:
        for r in scan_match(m):
            (errors if r.get("error") else priced).append(r)

    plays = [r for r in priced
             if r["ev_pct"] / 100 >= min_ev and r["win_prob"] >= min_win]
    plays.sort(key=lambda r: (-r["win_prob"], -r["ev_pct"]))
    return {
        "scanned_markets": len(priced),
        "matches": len(board),
        "plays": plays,
        "best": plays[0] if plays else None,
        "gates": {"min_ev_pct": min_ev * 100, "min_win_prob": min_win,
                  "rule": "winning first (rule 0), then EV — a fat-EV longshot "
                          "never outranks a probable winner"},
        "no_opinion": errors,
        "all_markets": priced,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scan a tennis board for +EV markets")
    ap.add_argument("--min-ev", type=float, default=MIN_EV)
    ap.add_argument("--min-win", type=float, default=MIN_WIN_PROB)
    ap.add_argument("--all", action="store_true", help="print every market priced")
    a = ap.parse_args()
    board = json.loads(sys.stdin.read() or "[]")
    out = scan_board(board, a.min_ev, a.min_win)
    if a.all:
        print(json.dumps(out, indent=1))
    else:
        print(f"{out['scanned_markets']} markets across {out['matches']} matches "
              f"-> {len(out['plays'])} plays\n")
        for p in out["plays"]:
            print(f"  {p['market'][:42]:<42} win {p['win_prob']*100:5.1f}%  "
                  f"@{p['price']:<5} EV {p['ev_pct']:+6.1f}%  {p['verdict']}")
        for e in out["no_opinion"]:
            print(f"  [no opinion] {e['match']}: {e['note']}")
