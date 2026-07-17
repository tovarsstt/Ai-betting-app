#!/usr/bin/env python3
"""
fetch_mlb_data.py — everything the MLB game engine needs, from statsapi.mlb.com
(official, free, no key — NOT Odds API quota).

Pulls and writes data/mlb_game_data.json:
  meta   — league runs environment, Pythagorean exponent FITTED to the 30 teams,
           home-field measured from real home/away splits, negative-binomial
           overdispersion FITTED to this season's per-team-game run counts
           (method of moments on mean-scaled residuals: baseball runs are
           over-dispersed; Poisson thins the tails)
  teams  — per team: W/L/G, RS/RA (+ per game), home/away splits
  games  — every completed regular-season game (date, teams, final score):
           the backtest + dispersion sample
  probables — today's + tomorrow's scheduled games with probable starters and
           each starter's REAL season line (runs allowed per 9 = runs*9/IP,
           innings per start) — runs, not earned runs: unearned runs score too

Run: python3 scripts/fetch_mlb_data.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "mlb_game_data.json"
API = "https://statsapi.mlb.com/api/v1"
UA = {"User-Agent": "Mozilla/5.0"}
SEASON_START = "-03-15"     # regular season never starts earlier


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def _home_away(rec: dict) -> tuple[int, int, int, int]:
    hw = hl = aw = al = 0
    for s in (rec.get("records") or {}).get("splitRecords") or []:
        if s.get("type") == "home":
            hw, hl = int(s.get("wins", 0)), int(s.get("losses", 0))
        elif s.get("type") == "away":
            aw, al = int(s.get("wins", 0)), int(s.get("losses", 0))
    return hw, hl, aw, al


def fetch_teams(season: int) -> dict:
    # standings returns SHORT names ("Angels") but schedule uses FULL names
    # ("Los Angeles Angels") — key everything by full name via the teams directory
    directory = {t["id"]: t["name"]
                 for t in get(f"{API}/teams?sportId=1&season={season}").get("teams", [])}
    teams = {}
    for lid in (103, 104):                      # AL, NL
        payload = get(f"{API}/standings?leagueId={lid}&season={season}")
        for div in payload.get("records", []):
            for rec in div.get("teamRecords", []):
                g = int(rec.get("gamesPlayed", 0))
                if g <= 0:
                    continue
                hw, hl, aw, al = _home_away(rec)
                teams[directory.get(rec["team"]["id"], rec["team"]["name"])] = {
                    "w": int(rec["wins"]), "l": int(rec["losses"]), "g": g,
                    "rs": int(rec["runsScored"]), "ra": int(rec["runsAllowed"]),
                    "rs_pg": round(int(rec["runsScored"]) / g, 3),
                    "ra_pg": round(int(rec["runsAllowed"]) / g, 3),
                    "home_w": hw, "home_l": hl, "away_w": aw, "away_l": al,
                }
    return teams


def fetch_games(season: int, until: str) -> list[dict]:
    """Every completed regular-season game with a final score."""
    sched = get(f"{API}/schedule?sportId=1&season={season}&gameType=R"
                f"&startDate={season}{SEASON_START}&endDate={until}")
    games = []
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            if (g.get("status") or {}).get("codedGameState") != "F":
                continue
            ht, at = g["teams"]["home"], g["teams"]["away"]
            if "score" not in ht or "score" not in at:
                continue
            games.append({"date": day["date"],
                          "home": ht["team"]["name"], "away": at["team"]["name"],
                          "hs": int(ht["score"]), "as": int(at["score"])})
    return games


def fetch_probables(season: int, start: str, end: str) -> list[dict]:
    """Scheduled games w/ probable starters + each starter's real season line."""
    sched = get(f"{API}/schedule?sportId=1&season={season}&gameType=R"
                f"&startDate={start}&endDate={end}&hydrate=probablePitcher")
    pitcher_cache: dict = {}

    def pitcher_line(p: dict | None) -> dict | None:
        if not p or not p.get("id"):
            return None
        pid = p["id"]
        if pid not in pitcher_cache:
            line = None
            try:
                stats = get(f"{API}/people/{pid}/stats?stats=season"
                            f"&season={season}&group=pitching")
                splits = (stats.get("stats") or [{}])[0].get("splits") or []
                if splits:
                    st = splits[0]["stat"]
                    ip = float(st.get("inningsPitched", 0) or 0)
                    # statsapi IP uses .1/.2 for thirds — convert to true innings
                    whole = int(ip)
                    ip_true = whole + (ip - whole) * 10 / 3
                    gs = int(st.get("gamesStarted", 0) or 0)
                    runs = int(st.get("runs", 0) or 0)
                    if ip_true > 0:
                        line = {"name": p.get("fullName"), "id": pid,
                                "ra9": round(runs * 9 / ip_true, 3),
                                "ip_per_start": round(ip_true / gs, 2) if gs else None,
                                "innings": round(ip_true, 1), "starts": gs}
            except Exception:                                  # noqa: BLE001
                line = None
            pitcher_cache[pid] = line or {"name": p.get("fullName"), "id": pid,
                                          "ra9": None, "ip_per_start": None}
        return pitcher_cache[pid]

    out = []
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            ht, at = g["teams"]["home"], g["teams"]["away"]
            out.append({
                "date": day["date"], "gamePk": g.get("gamePk"),
                "home": ht["team"]["name"], "away": at["team"]["name"],
                "home_pitcher": pitcher_line(ht.get("probablePitcher")),
                "away_pitcher": pitcher_line(at.get("probablePitcher")),
            })
    return out


def fit_pyth_exponent(teams: dict, lo=0.5, hi=4.0, steps=350) -> float:
    best_x, best_err = lo, float("inf")
    for i in range(steps + 1):
        x = lo + (hi - lo) * i / steps
        err = sum((t["rs"] ** x / (t["rs"] ** x + t["ra"] ** x) - t["w"] / t["g"]) ** 2
                  for t in teams.values())
        if err < best_err:
            best_x, best_err = x, err
    return best_x


def fit_dispersion(games: list[dict], teams: dict, league_rpg: float) -> float:
    """Var/mean ratio of per-team-game runs after removing matchup means —
    the negative-binomial overdispersion phi (phi=1 would be pure Poisson)."""
    resid_num = resid_den = 0.0
    for g in games:
        for side, opp, runs in ((g["home"], g["away"], g["hs"]),
                                (g["away"], g["home"], g["as"])):
            ts, to = teams.get(side), teams.get(opp)
            if not ts or not to:
                continue
            lam = ts["rs_pg"] * to["ra_pg"] / league_rpg
            if lam <= 0:
                continue
            resid_num += (runs - lam) ** 2
            resid_den += lam
    return resid_num / resid_den if resid_den else 1.0


def league_home_win_pct(teams: dict) -> float | None:
    hw = sum(t["home_w"] for t in teams.values())
    hl = sum(t["home_l"] for t in teams.values())
    return round(hw / (hw + hl), 4) if hw + hl > 0 else None


def main() -> int:
    now = datetime.now(timezone.utc)
    season = now.year
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()

    teams = fetch_teams(season)
    if len(teams) < 28:
        print(f"only {len(teams)} MLB teams — aborting, keeping old file", file=sys.stderr)
        return 1
    games = fetch_games(season, today)
    if len(games) < 300:
        print(f"only {len(games)} completed games — aborting", file=sys.stderr)
        return 1
    total_g = sum(t["g"] for t in teams.values())
    league_rpg = sum(t["rs"] for t in teams.values()) / total_g

    doc = {
        "meta": {
            "fetched_at": now.isoformat(timespec="seconds"),
            "season": season,
            "source": "statsapi.mlb.com (standings + schedule + pitcher season stats)",
            "league_rpg": round(league_rpg, 3),
            "pyth_exponent": round(fit_pyth_exponent(teams), 3),
            "home_win_pct": league_home_win_pct(teams),
            "nb_dispersion": round(fit_dispersion(games, teams, league_rpg), 3),
            "n_games": len(games),
            "method": "all parameters fitted from this season's real games",
        },
        "teams": teams,
        "games": games,
        # whole season of probable starters (one schedule call; pitcher lines
        # cached per id) — feeds BOTH live predictions (dates >= today) and the
        # with-pitchers backtest (exact-date match on completed games)
        "probables": fetch_probables(season, f"{season}{SEASON_START}", tomorrow),
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    m = doc["meta"]
    n_prob = sum(1 for p in doc["probables"]
                 if (p["home_pitcher"] or {}).get("ra9") is not None)
    print(f"wrote {OUT.name}: {len(teams)} teams, {len(games)} completed games, "
          f"{len(doc['probables'])} upcoming ({n_prob} w/ probable-starter lines) | "
          f"league {m['league_rpg']} R/G, pyth {m['pyth_exponent']}, "
          f"home {m['home_win_pct']}, NB phi {m['nb_dispersion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
