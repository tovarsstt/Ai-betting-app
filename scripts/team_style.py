#!/usr/bin/env python3
"""
team_style.py — how a side actually plays, and who is refereeing.

"Know the game, not just the maths" is the right ambition and the easiest place
in this project to start inventing. A sentence like "Atlético are a low-block
counter-attacking side" is either a MEASUREMENT or it is prose that sounds
expert and moves a price on nothing. Everything here is the former: counted from
`data/soccer/match_stats.csv` (3,500+ matches carrying shots, shots on target,
fouls, corners, cards, half-time score and the referee's name).

What it measures, and why each one can move a price:

  TEMPO / VOLUME    shots and shots-on-target per game, and shots faced. The
                    difference between a side that plays 28-shot games and one
                    that plays 16-shot games is a goals-market edge.
  FINISHING         goals per shot on target. Separates "creates a lot" from
                    "scores a lot" — and it is the number most likely to be
                    unsustainable, so it is reported with its sample size.
  GAME STATE        share of goals scored and conceded in each half. A side that
                    concedes late is a live-betting and second-half-total edge.
  DISCIPLINE        fouls, yellows and reds per game — the cards-market input,
                    and the red-card variance that wrecks a favourite.
  SET PIECES        corners won and conceded per game.
  REFEREE           cards and fouls per game, plus FOULS PER CARD, which is what
                    actually separates a strict whistle from a lenient one. Two
                    referees can both average 4 cards; the one who gives them
                    after 8 fouls rather than 14 is the strict one.
  DERBY INTENSITY   cards and fouls in a specific fixture measured against the
                    two sides' own baselines. "This one is spicy" becomes a
                    ratio instead of a vibe.

Style is DESCRIPTION, not prediction. Nothing here is fed into the win
probability — the Poisson model owns that, and it has been measured (rule 19).
These are the cited facts rule 13 requires alongside a pick, and inputs for
markets the goals model does not price at all: cards, corners, fouls.

Run: python3 scripts/team_style.py "Real Madrid" ["Espanol"]
     python3 scripts/team_style.py --referee "A Taylor"
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent.parent / "data" / "soccer"
STATS = DATA / "match_stats.csv"

MIN_MATCHES = 6          # below this a "style" is noise
MIN_REF_MATCHES = 8
_CACHE: Optional[list] = None


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def load(path: Path = STATS) -> list[dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with path.open() as f:
            _CACHE = list(csv.DictReader(f))
    except (FileNotFoundError, OSError):
        _CACHE = []
    return _CACHE


def _sides(team: str, rows: list[dict]) -> list[dict]:
    """Every match for a team, flipped so 'for'/'against' are from its view."""
    out = []
    for r in rows:
        if r["home_team"] == team:
            p, o = "home", "away"
        elif r["away_team"] == team:
            p, o = "away", "home"
        else:
            continue
        out.append({
            "date": r["date"], "venue": p, "referee": r.get("referee") or None,
            "gf": _num(r[f"{p}_goals"]), "ga": _num(r[f"{o}_goals"]),
            "ht_gf": _num(r.get(f"ht_{p}_goals")), "ht_ga": _num(r.get(f"ht_{o}_goals")),
            "shots": _num(r.get(f"{p}_shots")), "shots_faced": _num(r.get(f"{o}_shots")),
            "sot": _num(r.get(f"{p}_sot")), "sot_faced": _num(r.get(f"{o}_sot")),
            "fouls": _num(r.get(f"{p}_fouls")), "corners": _num(r.get(f"{p}_corners")),
            "corners_faced": _num(r.get(f"{o}_corners")),
            "yellow": _num(r.get(f"{p}_yellow")), "red": _num(r.get(f"{p}_red")),
            "opponent": r[f"{o}_team"],
        })
    return out


def _avg(ms: list[dict], key: str) -> Optional[float]:
    vals = [m[key] for m in ms if m.get(key) is not None]
    return round(statistics.fmean(vals), 2) if vals else None


def style(team: str, rows: Optional[list[dict]] = None,
          limit: int = 40) -> Optional[dict]:
    """Measured playing profile, or None when there is too little to measure."""
    rows = rows if rows is not None else load()
    ms = _sides(team, rows)[-limit:]
    if len(ms) < MIN_MATCHES:
        return None

    sot = [m["sot"] for m in ms if m.get("sot") is not None]
    gf = [m["gf"] for m in ms if m.get("gf") is not None]
    # Goals per shot on target — creation vs conversion.
    finishing = (round(sum(gf) / sum(sot), 3)
                 if sot and sum(sot) > 0 and len(gf) == len(sot) else None)

    # Where the goals land. A side that concedes after the break is a
    # second-half-total and live-betting signal.
    fh_for = sum(m["ht_gf"] for m in ms if m.get("ht_gf") is not None)
    tot_for = sum(m["gf"] for m in ms if m.get("gf") is not None and m.get("ht_gf") is not None)
    fh_ag = sum(m["ht_ga"] for m in ms if m.get("ht_ga") is not None)
    tot_ag = sum(m["ga"] for m in ms if m.get("ga") is not None and m.get("ht_ga") is not None)

    return {
        "team": team,
        "matches": len(ms),
        "window": f"{ms[0]['date']} to {ms[-1]['date']}",
        "tempo": {
            "shots_for_pg": _avg(ms, "shots"),
            "shots_against_pg": _avg(ms, "shots_faced"),
            "sot_for_pg": _avg(ms, "sot"),
            "sot_against_pg": _avg(ms, "sot_faced"),
            "shot_volume_pg": (round((_avg(ms, "shots") or 0) +
                                     (_avg(ms, "shots_faced") or 0), 2)),
        },
        "finishing": {
            "goals_per_sot": finishing,
            "note": "goals per shot on target — the least stable number here; "
                    f"n={len(sot)} matches",
        },
        "game_state": {
            "share_goals_scored_1st_half": round(fh_for / tot_for, 3) if tot_for else None,
            "share_goals_conceded_1st_half": round(fh_ag / tot_ag, 3) if tot_ag else None,
        },
        "discipline": {
            "fouls_pg": _avg(ms, "fouls"),
            "yellows_pg": _avg(ms, "yellow"),
            "reds_pg": _avg(ms, "red"),
        },
        "set_pieces": {
            "corners_for_pg": _avg(ms, "corners"),
            "corners_against_pg": _avg(ms, "corners_faced"),
        },
        "source": "counted from match_stats.csv — description, not prediction",
    }


def referee(name: str, rows: Optional[list[dict]] = None) -> Optional[dict]:
    """A referee's measured tendency. None when too few matches to judge."""
    rows = rows if rows is not None else load()
    ms = [r for r in rows if (r.get("referee") or "") == name]
    if len(ms) < MIN_REF_MATCHES:
        return None
    cards, fouls, reds, pens = [], [], [], []
    for r in ms:
        y = (_num(r.get("home_yellow")) or 0) + (_num(r.get("away_yellow")) or 0)
        rd = (_num(r.get("home_red")) or 0) + (_num(r.get("away_red")) or 0)
        f = (_num(r.get("home_fouls")) or 0) + (_num(r.get("away_fouls")) or 0)
        cards.append(y + rd)
        reds.append(rd)
        fouls.append(f)
    cpg = statistics.fmean(cards)
    fpg = statistics.fmean(fouls)
    return {
        "referee": name,
        "matches": len(ms),
        "cards_pg": round(cpg, 2),
        "reds_pg": round(statistics.fmean(reds), 3),
        "fouls_pg": round(fpg, 2),
        # THE number that separates strict from lenient. Two refs can average
        # the same cards; the one booking after 8 fouls is the strict one.
        "fouls_per_card": round(fpg / cpg, 2) if cpg > 0 else None,
        "source": "counted from match_stats.csv",
    }


def referee_table(rows: Optional[list[dict]] = None) -> list[dict]:
    rows = rows if rows is not None else load()
    names = {r.get("referee") for r in rows if r.get("referee")}
    out = [referee(n, rows) for n in names]
    return sorted([o for o in out if o], key=lambda r: -r["cards_pg"])


def fixture_intensity(home: str, away: str,
                      rows: Optional[list[dict]] = None) -> Optional[dict]:
    """Is THIS fixture spicier than these two sides usually are?

    Derby heat measured, not asserted: cards and fouls in the head-to-head
    against each side's own baseline.
    """
    rows = rows if rows is not None else load()
    h2h = [r for r in rows
           if {r["home_team"], r["away_team"]} == {home, away}]
    if len(h2h) < 3:
        return None

    def _match_cards(r):
        return ((_num(r.get("home_yellow")) or 0) + (_num(r.get("away_yellow")) or 0)
                + (_num(r.get("home_red")) or 0) + (_num(r.get("away_red")) or 0))

    def _match_fouls(r):
        return (_num(r.get("home_fouls")) or 0) + (_num(r.get("away_fouls")) or 0)

    h2h_cards = statistics.fmean([_match_cards(r) for r in h2h])
    h2h_fouls = statistics.fmean([_match_fouls(r) for r in h2h])

    base_rows = [r for r in rows
                 if home in (r["home_team"], r["away_team"])
                 or away in (r["home_team"], r["away_team"])]
    base_cards = statistics.fmean([_match_cards(r) for r in base_rows])
    base_fouls = statistics.fmean([_match_fouls(r) for r in base_rows])

    ratio = h2h_cards / base_cards if base_cards else None
    return {
        "fixture": f"{home} v {away}",
        "meetings": len(h2h),
        "cards_pg_in_fixture": round(h2h_cards, 2),
        "cards_pg_baseline": round(base_cards, 2),
        "fouls_pg_in_fixture": round(h2h_fouls, 2),
        "fouls_pg_baseline": round(base_fouls, 2),
        "intensity_ratio": round(ratio, 2) if ratio else None,
        "verdict": (None if ratio is None else
                    "hotter than these sides' normal — cards markets run high"
                    if ratio >= 1.25 else
                    "calmer than these sides' normal" if ratio <= 0.8 else
                    "no unusual heat in this fixture"),
        "caveat": f"only {len(h2h)} meetings on file" if len(h2h) < 5 else None,
    }


def context(home: str, away: str, ref: Optional[str] = None) -> dict:
    """The full game-context block for a fixture."""
    rows = load()
    out = {
        "home_style": style(home, rows),
        "away_style": style(away, rows),
        "fixture_intensity": fixture_intensity(home, away, rows),
        "referee": referee(ref, rows) if ref else None,
        "source": "match_stats.csv — every figure counted from real matches",
    }
    missing = [n for n, k in ((home, "home_style"), (away, "away_style")) if not out[k]]
    if missing:
        out["note"] = (f"no measured style for {', '.join(missing)} — fewer than "
                       f"{MIN_MATCHES} matches on file (newly promoted, or "
                       f"outside the big-5 result set)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("home", nargs="?")
    ap.add_argument("away", nargs="?")
    ap.add_argument("--referee")
    ap.add_argument("--ref-table", action="store_true")
    a = ap.parse_args()
    if a.ref_table:
        print(json.dumps(referee_table()[:20], indent=1))
    elif a.referee and not a.home:
        print(json.dumps(referee(a.referee), indent=1))
    elif a.home and a.away:
        print(json.dumps(context(a.home, a.away, a.referee), indent=1))
    elif a.home:
        print(json.dumps(style(a.home), indent=1))
    else:
        ap.error("give a team, two teams, or --referee/--ref-table")
