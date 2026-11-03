#!/usr/bin/env python3
"""
nfl_availability.py — starter-change detector from depth charts.

For every team-game it counts, per position group, how many of today's starters were NOT starters in the team's previous game:
    ol  (5 linemen)   dl (DE/DT/NT)   lb   cb (corners + nickel)   s (safeties)   wr (top-3)   te (TE1)   rb (RB1)   qb
Reason is irrelevant (injury, retirement, trade, benching) — it is the lineup the 2026 results were NOT produced with.
Sources (free, nflverse): depth_charts 2023-24 = weekly table; 2025-26 = daily ESPN snapshots; plus pbp for game dates.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AV = Path("/tmp/kg/nflverse/avail")
NFLV = Path("/tmp/kg/nflverse")
GROUPS = {
    "ol": ["LT", "LG", "C", "RG", "RT"],
    "dl": ["LDE", "RDE", "LDT", "RDT", "NT", "DE", "DT"],
    "lb": ["WLB", "SLB", "MLB", "LILB", "RILB", "OLB", "ILB"],
    "cb": ["LCB", "RCB", "NB", "CB"],
    "s": ["SS", "FS", "S"],
}
SKILL = {"wr": ("WR", 3), "te": ("TE", 1), "rb": ("RB", 1), "qb": ("QB", 1)}
TEAM_FIX = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LA", "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "SL": "LA"}


def _fix(t):
    return TEAM_FIX.get(t, t)


def games_table(years=(2023, 2024, 2025, 2026)) -> pd.DataFrame:
    rows = []
    for y in years:
        f = NFLV / f"pbp_{y}.csv.gz"
        if not f.exists():
            continue
        d = pd.read_csv(f, usecols=["game_id", "season_type", "week", "game_date", "home_team", "away_team"], low_memory=False)
        d = d[d.season_type == "REG"].drop_duplicates("game_id")
        for r in d.itertuples():
            for tm, opp in ((r.home_team, r.away_team), (r.away_team, r.home_team)):
                rows.append((y, int(r.week), r.game_id, tm, opp, pd.Timestamp(r.game_date)))
    return pd.DataFrame(rows, columns=["season", "week", "game_id", "team", "opp", "date"])


def _starters_weekly(depth: pd.DataFrame) -> dict:
    """2023-24 weekly schema -> {(team, week): {group: set(gsis)}}"""
    d = depth[(depth.game_type == "REG") & (depth.depth_team == 1)].copy()
    d["team"] = d.club_code.map(_fix)
    out = {}
    for (tm, wk), g in d.groupby(["team", "week"]):
        rec = {}
        for grp, slots in GROUPS.items():
            rec[grp] = set(g[g.depth_position.isin(slots)].gsis_id.dropna())
        for k, (pos, n) in SKILL.items():
            sub = g[g.depth_position == pos] if k != "wr" else g[g.depth_position.isin(["WR", "LWR", "RWR", "SWR"])]
            rec[k] = set(sub.gsis_id.dropna().head(n))
        out[(tm, int(wk))] = rec
    return out


def _starters_snapshot(depth: pd.DataFrame, team: str, asof: pd.Timestamp) -> dict | None:
    """2025-26 daily snapshots -> starters from the latest snapshot on/before `asof` (UTC date)."""
    g = depth[(depth.team == team) & (depth.date <= asof)]
    if g.empty:
        return None
    last = g.date.max()
    g = g[g.date == last]
    rec = {}
    for grp, slots in GROUPS.items():
        rec[grp] = set(g[g.pos_abb.isin(slots) & (g.pos_rank == 1)].gsis_id.dropna())
    for k, (pos, n) in SKILL.items():
        sub = g[(g.pos_abb == pos) & (g.pos_rank <= n)] if k == "wr" else g[(g.pos_abb == pos) & (g.pos_rank == 1)]
        rec[k] = set(sub.gsis_id.dropna().head(n))
    return rec


def injuries_out(years=(2023, 2024, 2025, 2026)) -> dict:
    """{(season, team, week): set(gsis)} of players listed Out/Doubtful on the game-week report (Questionable counts as available)."""
    out = {}
    for y in years:
        f = AV / f"injuries_{y}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f, low_memory=False)
        d = d[(d.game_type == "REG") & d.report_status.isin(["Out", "Doubtful"])]
        for (tm, wk), g in d.groupby(["team", "week"]):
            out[(y, _fix(tm), int(wk))] = set(g.gsis_id.dropna())
    return out


def lineup_changes(years=(2023, 2024, 2025, 2026)) -> pd.DataFrame:
    G = games_table(years).sort_values(["team", "date"]).reset_index(drop=True)
    INJ = injuries_out(years)
    snaps = {}
    wk = {}
    for y in years:
        if y in (2023, 2024):
            wk.update({(y,) + k: v for k, v in _starters_weekly(pd.read_csv(AV / f"depth_{y}.csv", low_memory=False)).items()})
        else:
            d = pd.read_csv(AV / f"depth_{y}.csv", low_memory=False)
            d["team"] = d.team.map(_fix)
            d["date"] = pd.to_datetime(d.dt.str[:10])
            snaps[y] = d
    rows = []
    for (tm, y), g in G.groupby(["team", "season"]):
        prev = None
        for r in g.itertuples():
            if y in (2023, 2024):
                cur = wk.get((y, tm, r.week))
            else:
                cur = _starters_snapshot(snaps[y], tm, r.date - pd.Timedelta(days=0))
            rec = {"season": y, "week": r.week, "game_id": r.game_id, "team": tm, "opp": r.opp}
            if cur is not None and prev is not None:
                out_now = INJ.get((y, tm, int(r.week)), set())
                for k in list(GROUPS) + list(SKILL):
                    rec[k + "_chg"] = float(len(cur[k] - prev[k]))                  # new faces in the lineup
                    rec[k + "_lost"] = float(len(prev[k] - (cur[k] - out_now)))      # last game's starters who are not starting AND available now
                rec["known"] = 1.0
            else:
                for k in list(GROUPS) + list(SKILL):
                    rec[k + "_chg"] = 0.0
                    rec[k + "_lost"] = 0.0
                rec["known"] = 0.0
            rows.append(rec)
            if cur is not None:
                prev = cur
    return pd.DataFrame(rows)


def current_changes(teams, asof=None) -> dict:
    """Upcoming-game view: starters in the latest 2026 snapshot vs the lineup of each team's last played game."""
    d = pd.read_csv(AV / "depth_2026.csv", low_memory=False)
    d["team"] = d.team.map(_fix)
    d["date"] = pd.to_datetime(d.dt.str[:10])
    G = games_table((2026,))
    out = {}
    for tm in teams:
        gg = G[G.team == tm].sort_values("date")
        if gg.empty:
            continue
        last = gg.iloc[-1]
        prev = _starters_snapshot(d, tm, last.date)
        cur = _starters_snapshot(d, tm, asof or d.date.max())
        if cur is None or prev is None:
            continue
        det = {}
        for k in list(GROUPS) + list(SKILL):
            det[k] = {"n": len(cur[k] - prev[k]), "in": sorted(cur[k] - prev[k]), "out": sorted(prev[k] - cur[k])}
        out[tm] = det
    return out


if __name__ == "__main__":
    ch = lineup_changes()
    print(ch.groupby("season")[["ol_lost", "dl_lost", "lb_lost", "cb_lost", "s_lost", "wr_lost", "te_lost", "rb_lost", "qb_lost", "known"]].mean().round(2))
    ch.to_pickle("/tmp/lineup_changes.pkl")


def _norm_name(s: str) -> str:
    import re
    return re.sub(r"[^a-z]", "", str(s).lower().replace(" jr.", "").replace(" sr.", "").replace(" iii", "").replace(" ii", ""))


# P(a "Questionable" regular actually plays), measured on 688 cases 2023-26 (players with >=5 touches in the previous 3 weeks): by practice status
Q_PLAY = {"Full": 0.88, "Limited": 0.65, "DNP": 0.46, "NA": 0.65}
Q_PLAY_QB = {"Full": 0.80, "Limited": 0.40, "DNP": 0.20, "NA": 0.42}


def _practice_key(s) -> str:
    s = str(s)
    return "DNP" if "Did Not" in s else ("Limited" if "Limited" in s else ("Full" if "Full" in s else "NA"))


def current_availability(teams, espn_injuries=None, force_active=None) -> dict:
    """For the upcoming game of each team: how many of LAST game's starters are not starting-and-available now, per group, with names.
    Out / Doubtful / IR / retired / traded = 1.0 missing; Questionable = expected loss (1 - P(plays | practice status)), measured from history.
    espn_injuries: list of {'team','player','pos','status'} (ESPN); nflverse's latest weekly report is always used too."""
    d = pd.read_csv(AV / "depth_2026.csv", low_memory=False)
    d["team"] = d.team.map(_fix)
    d["date"] = pd.to_datetime(d.dt.str[:10])
    G = games_table((2026,))
    inj = pd.read_csv(AV / "injuries_2026.csv", low_memory=False)
    inj = inj[inj.game_type == "REG"]
    wk = int(inj.week.max()) if len(inj) else 0
    inj["team"] = inj.team.map(_fix)
    names = d.drop_duplicates("gsis_id").set_index("gsis_id").player_name.to_dict()
    out = {}
    for tm in teams:
        gg = G[G.team == tm].sort_values("date")
        if gg.empty:
            continue
        prev = _starters_snapshot(d, tm, gg.iloc[-1].date)
        cur = _starters_snapshot(d, tm, d.date.max())
        if prev is None or cur is None:
            continue
        cw = inj[(inj.team == tm) & (inj.week == wk)]
        out_ids = set(cw[cw.report_status.isin(["Out", "Doubtful"])].gsis_id.dropna())
        qloss = {r.gsis_id: 1.0 - (Q_PLAY_QB if r.position == "QB" else Q_PLAY)[_practice_key(r.practice_status)] for r in cw[cw.report_status == "Questionable"].itertuples() if isinstance(r.gsis_id, str)}
        by_name = {_norm_name(r.player_name): r.gsis_id for r in d[d.team == tm].drop_duplicates("gsis_id").itertuples() if isinstance(r.player_name, str)}
        for it in (espn_injuries or []):
            if it.get("team") != tm:
                continue
            gid = by_name.get(_norm_name(it.get("player", "")))
            st = str(it.get("status", "")).lower()
            if gid and st in ("out", "injured reserve", "doubtful", "ir"):
                out_ids.add(gid)
            elif gid and st == "questionable" and gid not in qloss:
                qloss[gid] = 1.0 - (Q_PLAY_QB if str(it.get("pos")) == "QB" else Q_PLAY)["NA"]
        for nm in (force_active or []):                     # official inactives list: a player who is NOT inactive plays, whatever the (stale) weekly report says
            gid = by_name.get(_norm_name(nm))
            if gid:
                out_ids.discard(gid); qloss.pop(gid, None)
        counts, detail = {}, {}
        for k in list(GROUPS) + list(SKILL):
            gone = prev[k] - (cur[k] - out_ids)                                            # certain losses
            qs = {g: qloss[g] for g in (prev[k] & cur[k]) if g in qloss and g not in out_ids}  # starters who are only Questionable
            counts[k + "_lost"] = float(len(gone)) + float(sum(qs.values()))
            new = cur[k] - prev[k]
            if gone or new or qs:
                detail[k] = {"lost": sorted(names.get(g, g) for g in gone), "new_starters": sorted(names.get(g, g) for g in new),
                             "reason_flagged_out": sorted(names.get(g, g) for g in (gone & out_ids)),
                             "questionable": sorted((names.get(g, g), round(1 - v, 2)) for g, v in qs.items())}
        out[tm] = {"counts": counts, "detail": detail, "injury_report_week": wk, "snapshot": str(d.date.max().date())}
    return out
