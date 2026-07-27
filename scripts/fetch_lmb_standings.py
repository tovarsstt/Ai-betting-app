#!/usr/bin/env python3
"""
fetch_lmb_standings.py — Liga Mexicana de Béisbol team rates from MLB statsapi.

Why: user bets LMB on Stake (Dorados ML hit Jul 16) but the app had no model —
the coverage gate blocked the sport. statsapi.mlb.com (free, no key, NOT Odds
API quota) carries LMB as leagueId=125 with runs scored/allowed, games and
home/away splits per team — enough for a run-rate model with every parameter
measured from this league's own data:
  - per-team RS/G and RA/G
  - league runs-per-game environment
  - Pythagorean exponent FITTED to the 20 teams' actual win% (not MLB's 1.83)
  - home-field advantage measured from the league's aggregate home/away record

Writes data/lmb_ratings.json. Run: python3 scripts/fetch_lmb_standings.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "lmb_ratings.json"
API = "https://statsapi.mlb.com/api/v1/standings?leagueId=125&season={season}"


def fetch(season: int) -> dict:
    with urllib.request.urlopen(API.format(season=season), timeout=20) as r:
        return json.loads(r.read().decode())


def _home_away(rec: dict) -> tuple[int, int, int, int]:
    """(home_w, home_l, away_w, away_l) from splitRecords; zeros if absent."""
    hw = hl = aw = al = 0
    for s in (rec.get("records") or {}).get("splitRecords") or []:
        if s.get("type") == "home":
            hw, hl = int(s.get("wins", 0)), int(s.get("losses", 0))
        elif s.get("type") == "away":
            aw, al = int(s.get("wins", 0)), int(s.get("losses", 0))
    return hw, hl, aw, al


def extract_teams(payload: dict) -> dict:
    teams = {}
    for div in payload.get("records", []):
        for rec in div.get("teamRecords", []):
            g = int(rec.get("gamesPlayed", 0))
            if g <= 0:
                continue
            hw, hl, aw, al = _home_away(rec)
            teams[rec["team"]["name"]] = {
                "w": int(rec["wins"]), "l": int(rec["losses"]), "g": g,
                "rs": int(rec["runsScored"]), "ra": int(rec["runsAllowed"]),
                "rs_pg": round(int(rec["runsScored"]) / g, 3),
                "ra_pg": round(int(rec["runsAllowed"]) / g, 3),
                "home_w": hw, "home_l": hl, "away_w": aw, "away_l": al,
            }
    return teams


def fit_pyth_exponent(teams: dict, lo=0.5, hi=4.0, steps=350) -> float:
    """Exponent x minimizing squared error between actual win% and
    RS^x/(RS^x+RA^x) across this league's own teams."""
    best_x, best_err = lo, float("inf")
    for i in range(steps + 1):
        x = lo + (hi - lo) * i / steps
        err = 0.0
        for t in teams.values():
            pyth = t["rs"] ** x / (t["rs"] ** x + t["ra"] ** x)
            err += (pyth - t["w"] / t["g"]) ** 2
        if err < best_err:
            best_x, best_err = x, err
    return best_x


def league_home_win_pct(teams: dict) -> float | None:
    hw = sum(t["home_w"] for t in teams.values())
    hl = sum(t["home_l"] for t in teams.values())
    return round(hw / (hw + hl), 4) if hw + hl > 0 else None


def main() -> int:
    season = datetime.now(timezone.utc).year
    payload = fetch(season)
    teams = extract_teams(payload)
    if len(teams) < 10:
        print(f"only {len(teams)} LMB teams returned — aborting, keeping old file",
              file=sys.stderr)
        return 1
    games = sum(t["g"] for t in teams.values())
    doc = {
        "meta": {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": f"statsapi.mlb.com standings leagueId=125 season={season}",
            "league_rpg": round(sum(t["rs"] for t in teams.values()) / games, 3),
            "pyth_exponent": round(fit_pyth_exponent(teams), 3),
            "home_win_pct": league_home_win_pct(teams),
            "n_teams": len(teams),
            "method": "run rates + Pythagorean exponent fitted to this league's W%",
        },
        "teams": teams,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    m = doc["meta"]
    print(f"wrote {OUT.name}: {len(teams)} teams, league {m['league_rpg']} R/G, "
          f"pyth exp {m['pyth_exponent']}, home win% {m['home_win_pct']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
