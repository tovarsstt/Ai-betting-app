#!/usr/bin/env python3
"""
fetch_tennis_serve_stats.py — real serve/break-point stats for the tennis
clutch model, ATP + WTA.

fetch_tennis_form.py's clutch signal is deciding-set + tiebreak win-rate ONLY,
because its source (tennis-data.co.uk) has no point-level stats. Sackmann's
original tennis_atp/tennis_wta GitHub repos (which had them) are gone from his
account (verified 404 2026-07-14), but two mirrors of the exact same schema
(w_ace, w_svpt, w_1stIn, w_1stWon, w_2ndWon, w_SvGms, w_bpSaved, w_bpFaced,
mirrored l_*) are reachable:
  ATP  Tennismylife/TML-Database          — live-updated
  WTA  Aneeshers/tennis-sackmann-archive  — archival mirror, updates lag weeks
        (verified 2026-07-14: wta_matches_2026.csv present, 1112 stat rows
        through 2026-05-25). Lag is fine — these are multi-season career
        rates, not form. Never invented.

Builds, per player (weighted like fetch_tennis_form.py — CUR season heaviest):
  ace_rate              = ace / svpt
  first_serve_pct       = 1stIn / svpt
  first_serve_win_pct   = 1stWon / 1stIn
  second_serve_win_pct  = 2ndWon / (svpt - 1stIn)
  bp_save_pct           = bpSaved / bpFaced                       (serving under pressure)
  bp_convert_pct        = (opp_bpFaced - opp_bpSaved) / opp_bpFaced  (returning under pressure)

Output (data/tennis_serve.json):
  { "players": { "surname|initial": { ace_rate, first_serve_pct,
        first_serve_win_pct, second_serve_win_pct, bp_save_pct,
        bp_convert_pct, n, tour } }, "tours": {"ATP": n, "WTA": n},
    "built": "YYYY-MM-DD" }
A surname|initial key that exists on BOTH tours is ambiguous and dropped from
both — wrong-tour stats are worse than no stats.

Re-run weekly, same cadence as fetch_tennis_form.py.
"""
import datetime
import json
import urllib.request
from collections import defaultdict
from io import StringIO
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent.parent / "data" / "tennis_serve.json"
CUR = datetime.date.today().year
YEAR_WEIGHT = {CUR: 3.0, CUR - 1: 2.0, CUR - 2: 1.0}
SOURCES = {
    "ATP": "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/{y}.csv",
    "WTA": "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/wta/wta_matches_{y}.csv",
}

MIN_SVPT = 200        # weighted service points before trusting a player's serve rates
MIN_BP_FACED = 10     # weighted break points faced before trusting bp_save_pct
MIN_BP_OPP_FACED = 10 # weighted opponent break points before trusting bp_convert_pct

STAT_COLS = ["ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]


def name_key(full: str):
    """(surname, first_initial) — mirrors fetch_tennis_form.name_key exactly,
    so both files' keys line up in edge_api without a shared import."""
    toks = str(full).replace(".", "").split()
    if len(toks) < 2:
        return None
    if len(toks[-1]) == 1:
        return (toks[-2].lower(), toks[-1][0].lower())
    return (toks[-1].lower(), toks[0][0].lower())


def load_year(year: int, tour: str) -> pd.DataFrame:
    url = SOURCES[tour].format(y=year)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="replace")
    df = pd.read_csv(StringIO(text))
    keep = ["winner_name", "loser_name"] + [f"w_{c}" for c in STAT_COLS] + [f"l_{c}" for c in STAT_COLS]
    have = [c for c in keep if c in df.columns]
    return df[have]


def load_matches(tour: str) -> list:
    frames = []
    for yr, wt in YEAR_WEIGHT.items():
        try:
            df = load_year(yr, tour).copy()
            df["__wt"] = wt
            frames.append(df)
            print(f"  {tour.lower()} {yr}: {len(df)} matches (w={wt})")
        except Exception as e:
            print(f"  {tour.lower()} {yr}: skip ({e})")
    if not frames:
        return []
    return pd.concat(frames, ignore_index=True).to_dict("records")


def aggregate(rows: list) -> dict:
    """Pure aggregation — no network. `rows` are dicts shaped like
    load_matches()'s output: winner_name/loser_name + w_*/l_* stat cols + __wt."""
    acc: dict = defaultdict(lambda: defaultdict(float))

    def add(key, prefix: str, m: dict, wt: float) -> None:
        for c in STAT_COLS:
            v = m.get(f"{prefix}_{c}")
            if v is None or pd.isna(v):
                return  # incomplete row for this player — skip entirely, never half-count
        for c in STAT_COLS:
            acc[key][c] += float(m[f"{prefix}_{c}"]) * wt
        acc[key]["__wt"] += wt
        opp_prefix = "l" if prefix == "w" else "w"
        obf, obs = m.get(f"{opp_prefix}_bpFaced"), m.get(f"{opp_prefix}_bpSaved")
        if obf is not None and obs is not None and not pd.isna(obf) and not pd.isna(obs):
            acc[key]["opp_bpFaced"] += float(obf) * wt
            acc[key]["opp_bpSaved"] += float(obs) * wt

    for m in rows:
        wt = float(m.get("__wt", 1.0))
        kw, kl = name_key(m.get("winner_name")), name_key(m.get("loser_name"))
        if kw:
            add(kw, "w", m, wt)
        if kl:
            add(kl, "l", m, wt)

    players = {}
    for key, a in acc.items():
        svpt = a.get("svpt", 0.0)
        if svpt < MIN_SVPT:
            continue
        rec = {
            "ace_rate": round(a["ace"] / svpt, 4),
            "first_serve_pct": round(a["1stIn"] / svpt, 4),
            "n": round(a["__wt"], 1),
        }
        if a["1stIn"] > 0:
            rec["first_serve_win_pct"] = round(a["1stWon"] / a["1stIn"], 4)
        second_pts = svpt - a["1stIn"]
        if second_pts > 0:
            rec["second_serve_win_pct"] = round(a["2ndWon"] / second_pts, 4)
        if a.get("bpFaced", 0.0) >= MIN_BP_FACED:
            rec["bp_save_pct"] = round(a["bpSaved"] / a["bpFaced"], 4)
        if a.get("opp_bpFaced", 0.0) >= MIN_BP_OPP_FACED:
            rec["bp_convert_pct"] = round((a["opp_bpFaced"] - a["opp_bpSaved"]) / a["opp_bpFaced"], 4)
        players["%s|%s" % key] = rec
    return players


def merge_tours(atp: dict, wta: dict) -> tuple[dict, list[str]]:
    """Pure: flatten both tours into one surname|initial dict, tagging each
    entry with its tour. Keys present on BOTH tours are ambiguous — dropped
    from the merge entirely and returned as the collision list."""
    collisions = sorted(set(atp) & set(wta))
    merged = {}
    for tour, players in (("ATP", atp), ("WTA", wta)):
        for key, rec in players.items():
            if key in collisions:
                continue
            merged[key] = {**rec, "tour": tour}
    return merged, collisions


def build() -> None:
    atp_rows = load_matches("ATP")
    if not atp_rows:
        raise SystemExit("no ATP match data — Tennismylife/TML-Database unreachable?")
    wta_rows = load_matches("WTA")  # mirror may lag or vanish — WTA is best-effort
    atp, wta = aggregate(atp_rows), aggregate(wta_rows)
    players, collisions = merge_tours(atp, wta)
    out = {"players": players, "tours": {"ATP": len(atp), "WTA": len(wta)},
           "built": datetime.date.today().isoformat(),
           "note": "ATP from Tennismylife/TML-Database (live); WTA from "
                   "Aneeshers/tennis-sackmann-archive (archival mirror, lags weeks); "
                   f"{len(collisions)} ambiguous cross-tour keys dropped",
           "dropped_cross_tour_keys": collisions}
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"serve stats: {len(atp)} ATP + {len(wta)} WTA "
          f"({len(collisions)} cross-tour collisions dropped) -> {OUT.name}")
    print("restart edge_api (kill :8001) to load")


if __name__ == "__main__":
    build()
