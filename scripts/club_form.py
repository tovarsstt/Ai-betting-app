#!/usr/bin/env python3
"""
club_form.py — recent form, splits and H2H for CLUB sides (global rule 13).

`data/soccer_form.json` holds only NATIONAL teams (229 of them, built for the
World Cup). Club fixtures therefore returned `profile: null`, so every club pick
was presented without the both-sides profile rule 13 requires — in the user's
number-one sport, mid-season.

Nothing new needs fetching: `data/soccer/club_results.csv` already carries every
big-5 result (3,509 matches, including the 2026-27 season). This derives form
from it directly.

Everything here is a COUNTED fact from real results — matches played, goals for
and against, current streak, home/away split, head-to-head. No ratings, no
model output, nothing estimated; a side with too few matches reports what it
has rather than padding with a prior.

Run: python3 scripts/club_form.py "Real Madrid" "Espanyol"
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent.parent / "data"
RESULTS = DATA / "soccer" / "club_results.csv"

RECENT_N = 6            # matches in the "recent form" window
SEASON_LOOKBACK_DAYS = 400
_CACHE: Optional[list] = None


def load_results(path: Path = RESULTS) -> list[dict]:
    """Every club result, newest last. Cached — the file only changes on refit."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with path.open() as f:
            rows = [r for r in csv.DictReader(f) if r.get("date")]
    except (FileNotFoundError, OSError):
        rows = []
    for r in rows:
        try:
            r["hs"], r["as_"] = int(r["home_score"]), int(r["away_score"])
        except (TypeError, ValueError, KeyError):
            r["hs"] = r["as_"] = None
    _CACHE = sorted((r for r in rows if r["hs"] is not None), key=lambda r: r["date"])
    return _CACHE


def _team_matches(team: str, rows: list[dict], as_of: Optional[str] = None) -> list[dict]:
    cutoff = as_of or date.today().isoformat()
    floor = (datetime.fromisoformat(cutoff) - timedelta(days=SEASON_LOOKBACK_DAYS)).date().isoformat()
    out = []
    for r in rows:
        if r["date"] >= cutoff or r["date"] < floor:
            continue
        if r["home_team"] == team:
            out.append({**r, "venue": "home", "gf": r["hs"], "ga": r["as_"],
                        "opp": r["away_team"]})
        elif r["away_team"] == team:
            out.append({**r, "venue": "away", "gf": r["as_"], "ga": r["hs"],
                        "opp": r["home_team"]})
    return out


def _outcome(m: dict) -> str:
    return "W" if m["gf"] > m["ga"] else ("D" if m["gf"] == m["ga"] else "L")


def _streak(ms: list[dict]) -> Optional[str]:
    if not ms:
        return None
    last = _outcome(ms[-1])
    n = 0
    for m in reversed(ms):
        if _outcome(m) != last:
            break
        n += 1
    return f"{n}{last}"


def _split(ms: list[dict], venue: Optional[str] = None) -> dict:
    sel = [m for m in ms if venue is None or m["venue"] == venue]
    if not sel:
        return {"n": 0}
    w = sum(1 for m in sel if _outcome(m) == "W")
    d = sum(1 for m in sel if _outcome(m) == "D")
    return {
        "n": len(sel), "w": w, "d": d, "l": len(sel) - w - d,
        "gf_pg": round(sum(m["gf"] for m in sel) / len(sel), 2),
        "ga_pg": round(sum(m["ga"] for m in sel) / len(sel), 2),
        "ppg": round((3 * w + d) / len(sel), 2),
    }


def team_form(team: str, as_of: Optional[str] = None,
              rows: Optional[list[dict]] = None) -> Optional[dict]:
    """Counted form for one club, or None when it has no results on file."""
    rows = rows if rows is not None else load_results()
    ms = _team_matches(team, rows, as_of)
    if not ms:
        return None
    recent = ms[-RECENT_N:]
    btts = sum(1 for m in recent if m["gf"] > 0 and m["ga"] > 0)
    over25 = sum(1 for m in recent if m["gf"] + m["ga"] > 2.5)
    clean = sum(1 for m in recent if m["ga"] == 0)
    return {
        "team": team,
        "matches_on_file": len(ms),
        "last_result_date": ms[-1]["date"],
        "form": "".join(_outcome(m) for m in recent),
        "streak": _streak(ms),
        "season": _split(ms),
        "home": _split(ms, "home"),
        "away": _split(ms, "away"),
        # Niche trends rule 13 asks for, counted over the recent window only.
        "recent_window": len(recent),
        "btts_rate": round(btts / len(recent), 2),
        "over_2_5_rate": round(over25 / len(recent), 2),
        "clean_sheet_rate": round(clean / len(recent), 2),
        "recent_gf_pg": round(sum(m["gf"] for m in recent) / len(recent), 2),
        "recent_ga_pg": round(sum(m["ga"] for m in recent) / len(recent), 2),
    }


def head_to_head(home: str, away: str, rows: Optional[list[dict]] = None,
                 limit: int = 6) -> Optional[dict]:
    rows = rows if rows is not None else load_results()
    ms = [r for r in rows
          if {r["home_team"], r["away_team"]} == {home, away}][-limit:]
    if not ms:
        return None
    hw = sum(1 for m in ms if (m["home_team"] == home and m["hs"] > m["as_"])
             or (m["away_team"] == home and m["as_"] > m["hs"]))
    dr = sum(1 for m in ms if m["hs"] == m["as_"])
    return {
        "n": len(ms), "home_wins": hw, "draws": dr, "away_wins": len(ms) - hw - dr,
        "avg_goals": round(sum(m["hs"] + m["as_"] for m in ms) / len(ms), 2),
        "last": [{"date": m["date"], "score": f"{m['home_team']} {m['hs']}-{m['as_']} {m['away_team']}"}
                 for m in ms[-3:]],
    }


def profile(home: str, away: str, as_of: Optional[str] = None) -> Optional[dict]:
    """Both sides plus H2H — the rule-13 block for a club fixture."""
    rows = load_results()
    h, a = team_form(home, as_of, rows), team_form(away, as_of, rows)
    if not h and not a:
        return None
    out: dict = {"source": "counted from soccer/club_results.csv — real results only"}
    if h:
        out["home"] = h
    if a:
        out["away"] = a
    h2h = head_to_head(home, away, rows)
    if h2h:
        out["h2h"] = h2h
    missing = [n for n, v in ((home, h), (away, a)) if not v]
    if missing:
        out["note"] = (f"no results on file for {', '.join(missing)} — newly "
                       f"promoted or not in the big-5 result set")
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print('usage: club_form.py "Home Team" "Away Team"')
        raise SystemExit(2)
    print(json.dumps(profile(sys.argv[1], sys.argv[2]), indent=1))
