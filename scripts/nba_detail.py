"""
nba_detail.py — parse one ESPN NBA `summary` JSON into compact rows: team box (+possessions, pace), player box, shot
coordinates and per-player on-court time / points for-against rebuilt from the play-by-play substitutions.

Court coordinates (ESPN): x = 0..50 across the court, y = feet from the baseline; the basket sits at (25, 5.25).
On/off is rebuilt from starters + "X enters the game for Y" plays; a game is flagged lineup_ok only if the rebuilt minutes
match the box-score minutes of every player within MAX_MIN_ERR (otherwise its on/off rows must not be used).
"""
from __future__ import annotations

import math

BASKET = (25.0, 5.25)
MAX_MIN_ERR = 2.0
NO_COORD = -1000


def _pair(s: str) -> tuple[int, int]:
    a, _, b = s.partition("-")
    return int(a) if a.isdigit() else 0, int(b) if b.isdigit() else 0


def _num(s, cast=int):
    """ESPN writes '--' for stats of players who did not play."""
    try:
        return cast(str(s).replace("+", ""))
    except ValueError:
        return cast(0)


def _clock_sec(c: str) -> float:
    if ":" in c:
        m, s = c.split(":")
        return int(m) * 60 + float(s)
    return float(c or 0)


def _elapsed(period: int, clock: str) -> float:
    """Seconds since tip-off at the moment shown by (period, clock)."""
    done = 720 * min(period - 1, 4) + 300 * max(period - 5, 0)
    length = 720 if period <= 4 else 300
    return done + length - _clock_sec(clock)


def shot_zone(x: float, y: float, pts: int) -> str:
    """rim (<=4.5 ft) / paint / mid / corner3 / above3 from ESPN coordinates."""
    d = math.hypot(x - BASKET[0], y - BASKET[1])
    if pts == 3:
        return "corner3" if y <= 14 and (x <= 3 or x >= 47) else "above3"
    return "rim" if d <= 4.5 else ("paint" if d <= 8 else "mid")


def team_rows(d: dict, n_periods: int) -> list[dict]:
    comp = d["header"]["competitions"][0]
    comps = {c["team"]["id"]: c for c in comp["competitors"]}
    stats = {}
    for t in d["boxscore"]["teams"]:
        s = {x["name"]: x["displayValue"] for x in t["statistics"]}
        fgm, fga = _pair(s["fieldGoalsMade-fieldGoalsAttempted"])
        tpm, tpa = _pair(s["threePointFieldGoalsMade-threePointFieldGoalsAttempted"])
        ftm, fta = _pair(s["freeThrowsMade-freeThrowsAttempted"])
        stats[t["team"]["id"]] = {"fgm": fgm, "fga": fga, "fg3m": tpm, "fg3a": tpa, "ftm": ftm, "fta": fta, "oreb": int(s["offensiveRebounds"]),
                                  "dreb": int(s["defensiveRebounds"]), "tov": int(s["totalTurnovers"]), "ast": int(s["assists"]), "paint": int(s.get("pointsInPaint", 0)),
                                  "fastbreak": int(s.get("fastBreakPoints", 0)), "pts_off_tov": int(s.get("turnoverPoints", 0)), "fouls": int(s.get("fouls", 0))}
    ids = list(stats)
    poss = {i: stats[i]["fga"] + 0.44 * stats[i]["fta"] - stats[i]["oreb"] + stats[i]["tov"] for i in ids}
    game_poss = sum(poss.values()) / 2
    minutes = 48 + 5 * max(n_periods - 4, 0)
    out = []
    for i in ids:
        o = [j for j in ids if j != i][0]
        out.append({"game_id": comp["id"] if "id" in comp else d["header"]["id"], "date": comp["date"][:10], "team_id": i, "team": comps[i]["team"]["displayName"],
                    "home": int(comps[i]["homeAway"] == "home"), "opp_id": o, "pts": int(comps[i]["score"]), "opp_pts": int(comps[o]["score"]),
                    "periods": n_periods, **stats[i], "poss": round(game_poss, 2), "pace": round(game_poss * 48 / minutes, 2),
                    "opp_fga": stats[o]["fga"], "opp_oreb": stats[o]["oreb"], "opp_dreb": stats[o]["dreb"]})
    return out


def player_rows(d: dict) -> tuple[list[dict], dict]:
    rows, by_id = [], {}
    gid = d["header"]["id"]
    for t in d["boxscore"]["players"]:
        tid = t["team"]["id"]
        blk = t["statistics"][0]
        keys = blk["keys"]
        for a in blk["athletes"]:
            ath = a["athlete"]
            r = {"game_id": gid, "team_id": tid, "athlete_id": ath["id"], "name": ath["displayName"], "starter": int(bool(a.get("starter"))),
                 "dnp": int(bool(a.get("didNotPlay"))), "reason": a.get("reason", "") if a.get("didNotPlay") else "", "min": 0.0, "pts": 0, "reb": 0, "ast": 0,
                 "fgm": 0, "fga": 0, "fg3m": 0, "fg3a": 0, "ftm": 0, "fta": 0, "tov": 0, "stl": 0, "blk": 0, "oreb": 0, "pf": 0, "pm": 0}
            if a.get("stats"):
                s = dict(zip(keys, a["stats"]))
                r["fgm"], r["fga"] = _pair(s["fieldGoalsMade-fieldGoalsAttempted"])
                r["fg3m"], r["fg3a"] = _pair(s["threePointFieldGoalsMade-threePointFieldGoalsAttempted"])
                r["ftm"], r["fta"] = _pair(s["freeThrowsMade-freeThrowsAttempted"])
                r.update(min=_num(s["minutes"], float), pts=_num(s["points"]), reb=_num(s["rebounds"]), ast=_num(s["assists"]), tov=_num(s["turnovers"]), stl=_num(s["steals"]),
                         blk=_num(s["blocks"]), oreb=_num(s["offensiveRebounds"]), pf=_num(s["fouls"]), pm=_num(s["plusMinus"]))
            rows.append(r)
            by_id[ath["id"]] = r
    return rows, by_id


def shot_rows(d: dict) -> list[dict]:
    gid = d["header"]["id"]
    out = []
    for p in d["plays"]:
        c = p.get("coordinate") or {}
        if not p.get("shootingPlay") or p.get("pointsAttempted") not in (2, 3) or c.get("x", NO_COORD) < 0 or c.get("y", NO_COORD) < 0 or not p.get("participants"):
            continue
        out.append({"game_id": gid, "team_id": p["team"]["id"], "athlete_id": p["participants"][0]["athlete"]["id"], "period": p["period"]["number"],
                    "x": c["x"], "y": c["y"], "pts_att": p["pointsAttempted"], "made": int(bool(p.get("scoringPlay")))})
    return out


def onoff_rows(d: dict, by_id: dict) -> tuple[list[dict], bool]:
    """Seconds on court and points for / against while on court, from starters + substitutions."""
    gid = d["header"]["id"]
    teams = [t["team"]["id"] for t in d["boxscore"]["teams"]]
    on = {t: {a for a, r in by_id.items() if r["team_id"] == t and r["starter"]} for t in teams}
    acc = {a: {"sec": 0.0, "pf": 0, "pa": 0} for a in by_id}
    home_id = [c["team"]["id"] for c in d["header"]["competitions"][0]["competitors"] if c["homeAway"] == "home"][0]
    away_id = [t for t in teams if t != home_id][0]
    last_t, last_h, last_a = 0.0, 0, 0
    for p in d["plays"]:
        t = _elapsed(p["period"]["number"], p["clock"]["displayValue"])
        dt = max(t - last_t, 0.0)
        dh, da = p.get("homeScore", last_h) - last_h, p.get("awayScore", last_a) - last_a
        for tid in teams:
            for a in on[tid]:
                acc[a]["sec"] += dt
                mine, theirs = (dh, da) if tid == home_id else (da, dh)
                acc[a]["pf"] += mine
                acc[a]["pa"] += theirs
        last_t, last_h, last_a = max(t, last_t), p.get("homeScore", last_h), p.get("awayScore", last_a)
        if p["type"]["text"] == "Substitution" and len(p.get("participants", [])) == 2:
            tid = p["team"]["id"]
            enter, leave = (q["athlete"]["id"] for q in p["participants"])
            on[tid].discard(leave)
            on[tid].add(enter)
    ok = all(abs(acc[a]["sec"] / 60 - r["min"]) <= MAX_MIN_ERR for a, r in by_id.items() if not r["dnp"] and r["min"] > 0)
    rows = [{"game_id": gid, "team_id": by_id[a]["team_id"], "athlete_id": a, "sec_on": round(v["sec"], 1), "pf_on": v["pf"], "pa_on": v["pa"], "lineup_ok": int(ok)}
            for a, v in acc.items() if v["sec"] > 0]
    return rows, ok


def parse_summary(d: dict) -> dict:
    n_periods = max(p["period"]["number"] for p in d["plays"])
    players, by_id = player_rows(d)
    onoff, ok = onoff_rows(d, by_id)
    return {"team": team_rows(d, n_periods), "player": players, "shot": shot_rows(d), "onoff": onoff, "lineup_ok": ok}
