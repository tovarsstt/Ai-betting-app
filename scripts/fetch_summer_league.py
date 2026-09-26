#!/usr/bin/env python3
"""
fetch_summer_league.py — NBA Summer League scouting data (Vegas 2026), free ESPN.

Why: SL BETTING stays hard-gated (no stable signal — rotations are random), but
SL is where rookies first show up in real box scores and where next season's
officiating point of emphasis first appears. This pulls every completed Vegas
SL game and writes data/summer_league_2026.json with:
  players     — per-player aggregates (games, mpg, ppg, rpg, apg, stocks, TO, PF)
  rookies     — the top-N producers whose ESPN profile says experience 0
                (profiles fetched only for the top producers — checked, not guessed)
  officiating — SL free-throw-attempts and fouls per game vs a REAL regular-season
                baseline measured from the last week of the 2025-26 NBA season
                (same source, same parser — apples to apples)

Run: python3 scripts/fetch_summer_league.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "summer_league_2026.json"
SL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba-summer-las-vegas"
NBA = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
UA = {"User-Agent": "Mozilla/5.0"}
SL_FIRST_DAY = date(2026, 7, 5)
BASELINE_DATES = ("20260405", "20260407", "20260409")   # late 2025-26 regular season
TOP_N_PROFILE = 40      # profile-check only the top producers (rookie flag)


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def completed_event_ids(base: str, dates: list[str]) -> list[str]:
    ids = []
    for d in dates:
        try:
            for e in get(f"{base}/scoreboard?dates={d}").get("events", []):
                if (e.get("status") or {}).get("type", {}).get("completed"):
                    ids.append(e["id"])
        except Exception:                                      # noqa: BLE001
            continue
    return ids


def _num(s, default=0.0) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _made_att(s: str) -> tuple[float, float]:
    try:
        m, a = str(s).split("-")
        return float(m), float(a)
    except (ValueError, AttributeError):
        return 0.0, 0.0


def parse_game(summary: dict) -> tuple[list[dict], dict]:
    """(player rows, game officiating counters) from one ESPN summary payload."""
    rows = []
    fta = pf = 0.0
    for side in (summary.get("boxscore") or {}).get("players", []):
        for block in side.get("statistics", []):
            names = block.get("names", [])
            idx = {n: i for i, n in enumerate(names)}
            for ath in block.get("athletes", []):
                st = ath.get("stats") or []
                if not st or len(st) != len(names):
                    continue
                _, ft_a = _made_att(st[idx["FT"]]) if "FT" in idx else (0, 0)
                row = {
                    "id": (ath.get("athlete") or {}).get("id"),
                    "name": (ath.get("athlete") or {}).get("displayName"),
                    "min": _num(st[idx["MIN"]]) if "MIN" in idx else 0.0,
                    "pts": _num(st[idx["PTS"]]) if "PTS" in idx else 0.0,
                    "reb": _num(st[idx["REB"]]) if "REB" in idx else 0.0,
                    "ast": _num(st[idx["AST"]]) if "AST" in idx else 0.0,
                    "stl": _num(st[idx["STL"]]) if "STL" in idx else 0.0,
                    "blk": _num(st[idx["BLK"]]) if "BLK" in idx else 0.0,
                    "to": _num(st[idx["TO"]]) if "TO" in idx else 0.0,
                    "pf": _num(st[idx["PF"]]) if "PF" in idx else 0.0,
                    "fta": ft_a,
                }
                if row["min"] > 0:
                    rows.append(row)
                fta += ft_a
                pf += row["pf"]
    return rows, {"fta": fta, "pf": pf}


def officiating_env(base: str, dates: list[str]) -> dict | None:
    """League-wide FTA + fouls per game across the given dates' completed games."""
    games = 0
    fta = pf = 0.0
    for eid in completed_event_ids(base, dates):
        try:
            _, off = parse_game(get(f"{base}/summary?event={eid}"))
        except Exception:                                      # noqa: BLE001
            continue
        games += 1
        fta += off["fta"]
        pf += off["pf"]
    if games == 0:
        return None
    return {"games": games, "fta_per_game": round(fta / games, 1),
            "fouls_per_game": round(pf / games, 1)}


def aggregate_players(all_rows: list[dict]) -> list[dict]:
    agg: dict = {}
    for r in all_rows:
        a = agg.setdefault(r["id"], {"name": r["name"], "id": r["id"], "g": 0,
                                     **{k: 0.0 for k in
                                        ("min", "pts", "reb", "ast", "stl", "blk", "to", "pf")}})
        a["g"] += 1
        for k in ("min", "pts", "reb", "ast", "stl", "blk", "to", "pf"):
            a[k] += r[k]
    out = []
    for a in agg.values():
        g = a["g"]
        out.append({"name": a["name"], "id": a["id"], "games": g,
                    **{f"{k}pg": round(a[k] / g, 1) for k in
                       ("min", "pts", "reb", "ast", "stl", "blk", "to", "pf")}})
    out.sort(key=lambda p: -p["ptspg"])
    return out


def flag_rookies(players: list[dict], top_n: int = TOP_N_PROFILE) -> list[dict]:
    """Profile-check the top producers; keep those ESPN says have 0 years exp."""
    rookies = []
    for p in players[:top_n]:
        try:
            prof = get("https://sports.core.api.espn.com/v2/sports/basketball"
                       f"/leagues/nba/athletes/{p['id']}")
            exp = (prof.get("experience") or {}).get("years")
        except Exception:                                      # noqa: BLE001
            exp = None
        if exp == 0:
            rookies.append({**p, "rookie_confirmed": True})
    return rookies


def main() -> int:
    today = datetime.now(timezone.utc).date()
    sl_dates = [(SL_FIRST_DAY + timedelta(days=i)).strftime("%Y%m%d")
                for i in range((today - SL_FIRST_DAY).days + 1)]
    all_rows = []
    games = 0
    fta = pf = 0.0
    for eid in completed_event_ids(SL, sl_dates):
        try:
            rows, off = parse_game(get(f"{SL}/summary?event={eid}"))
        except Exception:                                      # noqa: BLE001
            continue
        all_rows.extend(rows)
        games += 1
        fta += off["fta"]
        pf += off["pf"]
    if games < 5:
        print(f"only {games} completed SL games parsed — aborting", file=sys.stderr)
        return 1

    players = aggregate_players(all_rows)
    baseline = officiating_env(NBA, list(BASELINE_DATES))
    sl_env = {"games": games, "fta_per_game": round(fta / games, 1),
              "fouls_per_game": round(pf / games, 1)}
    doc = {
        "meta": {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "source": "ESPN nba-summer-las-vegas box scores (free)",
                 "note": "scouting data — Summer League BETTING stays gated (no stable signal)"},
        "officiating": {
            "summer_league": sl_env,
            "nba_regular_baseline": baseline,
            "read": (None if not baseline else
                     f"SL whistles {'tighter' if sl_env['fouls_per_game'] > baseline['fouls_per_game'] else 'looser'}: "
                     f"{sl_env['fouls_per_game']} fouls/g vs {baseline['fouls_per_game']} regular-season; "
                     f"FTA {sl_env['fta_per_game']} vs {baseline['fta_per_game']} — new points of "
                     f"emphasis usually debut here and carry into October"),
        },
        "rookies": flag_rookies(players),
        "players": players[:80],
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"wrote {OUT.name}: {games} SL games, {len(players)} players, "
          f"{len(doc['rookies'])} confirmed rookies in top {TOP_N_PROFILE} | "
          f"SL {sl_env['fouls_per_game']} fouls/g vs baseline "
          f"{baseline['fouls_per_game'] if baseline else '?'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
