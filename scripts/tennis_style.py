#!/usr/bin/env python3
"""
tennis_style.py — a player's measured context: surface, conditions, stage, nerve.

The soccer engine got measured style (team_style.py). Tennis needs its own, and
the niche stats are completely different ones — a tennis "style" is not shots
and corners, it is where a player is comfortable and what happens when a match
gets tight.

Everything here is COUNTED from the tennis-data result files already on disk
(1,881 ATP matches for 2026 alone), which carry per-match Surface, Court
(indoor/outdoor), Series (Grand Slam / Masters / 500 / 250), Round, Best of, and
the full set scores.

What it measures, and why each one moves a price:

  SURFACE       win rate on clay / hard / grass. The single biggest context
                variable in tennis and the one a rank-difference model is blind
                to — the ratings know who is better overall, not where.
  CONDITIONS    indoor vs outdoor. Indoor removes wind and sun and rewards flat
                hitting and big serving; some players are transformed by it.
  STAGE         record by tournament tier and by round. "Shows up at Slams" and
                "loses early at 250s" are measurable, not vibes.
  NERVE         tiebreaks won, and deciding sets won. These are the closest
                thing tennis has to a clutch statistic, and they price the live
                and set-handicap markets directly.
  SHAPE         straight-sets rate (dominance) and games per match (grinder vs
                quick closer) — the games-total and set-handicap inputs.

Sample sizes are attached to every split, because a 3-match grass record is not
a grass preference. Below the floor a split returns None rather than a number
that will be read as knowledge.

Description, not prediction: none of this feeds the win probability, which the
points model owns and which has been measured point-in-time (rule 23).

Run: python3 scripts/tennis_style.py "Sinner J." [--tour atp] [--years 2025 2026]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

MIN_SPLIT = 5          # below this a split is noise, not a preference
MIN_TOTAL = 10         # below this there is no profile at all
_CACHE: dict = {}

SET_COLS = [("W1", "L1"), ("W2", "L2"), ("W3", "L3"), ("W4", "L4"), ("W5", "L5")]


def load_matches(tour: str = "atp", years: Optional[list[int]] = None) -> list[dict]:
    """Completed singles matches with their context columns."""
    key = (tour, tuple(years or []))
    if key in _CACHE:
        return _CACHE[key]
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("openpyxl required: pip install openpyxl")

    suffix = "m" if tour == "atp" else "w"
    out = []
    for yr in (years or [2025, 2026]):
        path = Path(f"/tmp/tdform_{yr}_{suffix}.xlsx")
        if not path.exists():
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = wb.active.iter_rows(values_only=True)
        head = [str(h).strip() if h else "" for h in next(rows)]
        for r in rows:
            d = dict(zip(head, r))
            if str(d.get("Comment", "")).strip() != "Completed":
                continue
            sets = []
            for w, l in SET_COLS:
                gw, gl = d.get(w), d.get(l)
                if gw is None or gl is None:
                    continue
                try:
                    sets.append((int(gw), int(gl)))
                except (TypeError, ValueError):
                    break
            if len(sets) < 2:
                continue
            out.append({
                "winner": str(d.get("Winner", "")).strip(),
                "loser": str(d.get("Loser", "")).strip(),
                "surface": str(d.get("Surface", "")).strip(),
                "court": str(d.get("Court", "")).strip(),
                "series": str(d.get("Series", "")).strip(),
                "round": str(d.get("Round", "")).strip(),
                "best_of": int(d.get("Best of") or 3),
                "sets": sets, "year": yr,
            })
    _CACHE[key] = out
    return out


def _player_rows(name: str, rows: list[dict]) -> list[dict]:
    """Every match for a player, oriented so 'won' is from their side."""
    out = []
    for m in rows:
        if m["winner"] == name:
            won, sets = True, m["sets"]
        elif m["loser"] == name:
            # Flip each set so the first number is always this player's games.
            won, sets = False, [(b, a) for a, b in m["sets"]]
        else:
            continue
        out.append({**m, "won": won, "own_sets": sets,
                    "opponent": m["loser"] if won else m["winner"]})
    return out


def _rate(ms: list[dict]) -> Optional[dict]:
    if len(ms) < MIN_SPLIT:
        return None
    w = sum(1 for m in ms if m["won"])
    return {"n": len(ms), "w": w, "l": len(ms) - w,
            "win_pct": round(w / len(ms), 3)}


def _split(ms: list[dict], key: str) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for m in ms:
        if m.get(key):
            groups[m[key]].append(m)
    out = {}
    for k, v in groups.items():
        r = _rate(v)
        out[k] = r if r else {"n": len(v), "win_pct": None,
                              "note": f"only {len(v)} matches — too few to read"}
    return out


def _tiebreaks(ms: list[dict]) -> dict:
    won = played = 0
    for m in ms:
        for a, b in m["own_sets"]:
            # A 7-6 or 6-7 set was decided by a breaker.
            if {a, b} == {7, 6}:
                played += 1
                won += a > b
    return {"played": played, "won": won,
            "win_pct": round(won / played, 3) if played >= MIN_SPLIT else None,
            "note": None if played >= MIN_SPLIT else
                    f"only {played} tiebreaks — too few to read"}


def _deciders(ms: list[dict]) -> dict:
    dec = [m for m in ms if len(m["own_sets"]) == m["best_of"]]
    r = _rate(dec)
    return r or {"n": len(dec), "win_pct": None,
                 "note": f"only {len(dec)} deciding sets — too few to read"}


def _shape(ms: list[dict]) -> dict:
    wins = [m for m in ms if m["won"]]
    straights = [m for m in wins if len(m["own_sets"]) == (m["best_of"] // 2 + 1)]
    games = [sum(a + b for a, b in m["own_sets"]) for m in ms if m["best_of"] == 3]
    return {
        "straight_set_win_pct": round(len(straights) / len(wins), 3) if wins else None,
        "wins": len(wins),
        "games_per_bo3_match": round(statistics.fmean(games), 2) if games else None,
        "bo3_matches": len(games),
    }


def profile(name: str, tour: str = "atp",
            years: Optional[list[int]] = None) -> Optional[dict]:
    rows = load_matches(tour, years)
    ms = _player_rows(name, rows)
    if len(ms) < MIN_TOTAL:
        return None
    overall = _rate(ms)
    return {
        "player": name,
        "tour": tour.upper(),
        "matches": len(ms),
        "years": years or [2025, 2026],
        "overall": overall,
        # The variable a rank-difference model is blind to.
        "by_surface": _split(ms, "surface"),
        "by_court": _split(ms, "court"),
        "by_series": _split(ms, "series"),
        "by_round": _split(ms, "round"),
        "nerve": {"tiebreaks": _tiebreaks(ms), "deciding_sets": _deciders(ms)},
        "shape": _shape(ms),
        "source": "counted from tennis-data results — description, not prediction",
        "caveat": f"splits under {MIN_SPLIT} matches report n and no rate",
    }


def matchup(a: str, b: str, tour: str = "atp", surface: Optional[str] = None,
            court: Optional[str] = None,
            years: Optional[list[int]] = None) -> dict:
    """Both players' context, plus their head-to-head on these conditions."""
    rows = load_matches(tour, years)
    h2h = [m for m in rows if {m["winner"], m["loser"]} == {a, b}]
    if surface:
        h2h_s = [m for m in h2h if m["surface"] == surface]
    else:
        h2h_s = h2h
    out = {
        "a": profile(a, tour, years),
        "b": profile(b, tour, years),
        "conditions": {"surface": surface, "court": court},
        "h2h": ({"n": len(h2h), "a_wins": sum(1 for m in h2h if m["winner"] == a)}
                if h2h else None),
        "h2h_on_surface": ({"surface": surface, "n": len(h2h_s),
                            "a_wins": sum(1 for m in h2h_s if m["winner"] == a)}
                           if surface and h2h_s else None),
        "source": "counted from tennis-data results",
    }
    missing = [n for n, k in ((a, "a"), (b, "b")) if not out[k]]
    if missing:
        out["note"] = (f"no measured profile for {', '.join(missing)} — fewer "
                       f"than {MIN_TOTAL} matches on file")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("player")
    ap.add_argument("opponent", nargs="?")
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--surface", default=None)
    ap.add_argument("--years", type=int, nargs="*", default=None)
    a = ap.parse_args()
    if a.opponent:
        print(json.dumps(matchup(a.player, a.opponent, a.tour, a.surface,
                                 years=a.years), indent=1))
    else:
        print(json.dumps(profile(a.player, a.tour, a.years), indent=1))
