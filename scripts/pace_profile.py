#!/usr/bin/env python3
"""
pace_profile.py — how a team plays, for the period sports (NBA, WNBA, NFL, NHL).

Soccer got team_style.py and tennis got tennis_style.py; the niche stats that
matter are different again here. For a period sport the questions a price cares
about are: how fast does this team play, WHEN do they score, do they start or
finish, and do their games go long?

Counted from `data/period_scores.json` — real per-period scorelines harvested
from ESPN (fetch_period_scores.py). No estimates.

What it measures, and why each moves a price:

  PACE          points for and against per game, and combined game total. The
                totals-market input, and the thing team ratings hide: two teams
                with the same net rating can play a 210-point game or a 190.
  PERIOD SHAPE  share of points scored in each quarter. This is what prices a
                1st-quarter or 1st-half line, and it is NOT uniform — measured
                across 571 NFL games, Q2 and Q4 run ~54% hotter than Q1 and Q3.
  START / CLOSE first-quarter and fourth-quarter margin per game. A team that
                starts fast is a live 1Q edge; a team that closes is a
                second-half and live-comeback edge.
  VARIANCE      standard deviation of the game total and margin. A high-variance
                team makes every line on their game a worse bet at the same
                price, which no average captures.
  OVERTIME      how often their games go past regulation.

Description, not prediction. The win probability belongs to the rated model;
this is the cited context rule 13 wants beside a pick, and the input for period
markets (rule 24) that a full-game rating cannot price.

Run: python3 scripts/pace_profile.py --sport nba "Boston Celtics"
     python3 scripts/pace_profile.py --sport wnba --league
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent.parent / "data"
SCORES = DATA / "period_scores.json"
MIN_GAMES = 8
_CACHE: dict = {}


def load(sport: str) -> Optional[dict]:
    s = sport.lower()
    if s in _CACHE:
        return _CACHE[s]
    try:
        _CACHE[s] = json.loads(SCORES.read_text()).get(s)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        _CACHE[s] = None
    return _CACHE[s]


def _sides(team: str, games: list[dict]) -> list[dict]:
    """Every game for a team, oriented so 'for' is always theirs."""
    out = []
    for g in games:
        if g["home"] == team:
            pf, pa = g["home_periods"], g["away_periods"]
            venue = "home"
        elif g["away"] == team:
            pf, pa = g["away_periods"], g["home_periods"]
            venue = "away"
        else:
            continue
        out.append({"date": g["date"], "venue": venue, "pf": pf, "pa": pa,
                    "ot": g.get("ot", False),
                    "opponent": g["away"] if venue == "home" else g["home"]})
    return out


def profile(team: str, sport: str, limit: int = 60) -> Optional[dict]:
    doc = load(sport)
    if not doc or not doc.get("games"):
        return None
    reg = int(doc.get("regulation_periods", 4))
    ms = _sides(team, doc["games"])[-limit:]
    if len(ms) < MIN_GAMES:
        return None

    tot_for = [sum(m["pf"]) for m in ms]
    tot_ag = [sum(m["pa"]) for m in ms]
    totals = [f + a for f, a in zip(tot_for, tot_ag)]
    margins = [f - a for f, a in zip(tot_for, tot_ag)]

    # Per-period shares and margins, regulation only — overtime is its own thing.
    per = []
    for p in range(reg):
        pf = [m["pf"][p] for m in ms if len(m["pf"]) > p]
        pa = [m["pa"][p] for m in ms if len(m["pa"]) > p]
        if not pf:
            continue
        per.append({
            "period": f"P{p + 1}",
            "points_for_pg": round(statistics.fmean(pf), 2),
            "points_against_pg": round(statistics.fmean(pa), 2),
            "margin_pg": round(statistics.fmean(pf) - statistics.fmean(pa), 2),
            "share_of_own_points": round(sum(pf) / sum(tot_for), 3) if sum(tot_for) else None,
        })

    return {
        "team": team, "sport": sport.lower(),
        "games": len(ms),
        "window": f"{ms[0]['date']} to {ms[-1]['date']}",
        "pace": {
            "points_for_pg": round(statistics.fmean(tot_for), 2),
            "points_against_pg": round(statistics.fmean(tot_ag), 2),
            "game_total_pg": round(statistics.fmean(totals), 2),
            "margin_pg": round(statistics.fmean(margins), 2),
        },
        "variance": {
            "game_total_sd": round(statistics.pstdev(totals), 2),
            "margin_sd": round(statistics.pstdev(margins), 2),
            "note": "higher spread = every line on this team's games is a worse "
                    "bet at the same price; an average cannot show this",
        },
        "period_shape": per,
        "start_and_close": {
            "first_period_margin_pg": per[0]["margin_pg"] if per else None,
            "last_period_margin_pg": per[-1]["margin_pg"] if per else None,
            "reads": ("starts faster than it finishes"
                      if per and per[0]["margin_pg"] > per[-1]["margin_pg"] + 1
                      else "finishes stronger than it starts"
                      if per and per[-1]["margin_pg"] > per[0]["margin_pg"] + 1
                      else "no meaningful start/close split"),
        },
        "overtime_rate": round(sum(1 for m in ms if m["ot"]) / len(ms), 3),
        "source": "counted from real per-period scorelines — description, not prediction",
    }


def league_shape(sport: str) -> Optional[dict]:
    """League-wide period shape — the baseline a team is fast or slow against."""
    doc = load(sport)
    if not doc or not doc.get("games"):
        return None
    reg = int(doc.get("regulation_periods", 4))
    games = doc["games"]
    per = []
    for p in range(reg):
        vals = [g["home_periods"][p] + g["away_periods"][p]
                for g in games if len(g["home_periods"]) > p and len(g["away_periods"]) > p]
        if vals:
            per.append({"period": f"P{p + 1}",
                        "total_pg": round(statistics.fmean(vals), 2)})
    totals = [sum(g["home_periods"]) + sum(g["away_periods"]) for g in games]
    return {
        "sport": sport.lower(), "games": len(games),
        "league_total_pg": round(statistics.fmean(totals), 2),
        "league_total_sd": round(statistics.pstdev(totals), 2),
        "period_totals": per,
        "overtime_rate": doc.get("ot_rate"),
        "note": "the baseline a team's pace is fast or slow AGAINST",
    }


def matchup(home: str, away: str, sport: str) -> dict:
    out = {"home": profile(home, sport), "away": profile(away, sport),
           "league": league_shape(sport),
           "source": "period_scores.json — every figure counted"}
    missing = [n for n, k in ((home, "home"), (away, "away")) if not out[k]]
    if missing:
        out["note"] = (f"no measured pace profile for {', '.join(missing)} — "
                       f"fewer than {MIN_GAMES} games on file for this sport")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("team", nargs="?")
    ap.add_argument("opponent", nargs="?")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--league", action="store_true")
    a = ap.parse_args()
    if a.league:
        print(json.dumps(league_shape(a.sport), indent=1))
    elif a.team and a.opponent:
        print(json.dumps(matchup(a.team, a.opponent, a.sport), indent=1))
    elif a.team:
        print(json.dumps(profile(a.team, a.sport), indent=1))
    else:
        ap.error("give a team, two teams, or --league")
