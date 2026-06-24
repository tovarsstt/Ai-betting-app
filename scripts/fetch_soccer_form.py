#!/usr/bin/env python3
"""
fetch_soccer_form.py — national-team comparative profile for the WC / soccer model.

The soccer model prices markets from MARKET-CALIBRATED Poisson lambdas (solved from
the devigged 1X2), which is robust. What it lacks is the comparative READ a sharp
uses: recent form, goals for/against trend, scoring/clean-sheet rates, and real H2H.
The club-based attack/defense ratings are unreliable for nations (Haiti > Brazil), so
this builds those signals from REAL international results — never invented.

Source: martj42/international_results (GitHub, reachable) — every international since
1872 incl. the 2026 WC fixtures, with tournament + neutral flags. Re-run weekly.

Output (data/soccer_form.json):
  { "teams": { name: { form_ppg, win_rate, gf, ga, over25, btts, clean_sheet,
        failed_to_score, streak, last5, n } },
    "h2h":   { name: { opp: { n, w, d, l, gf, ga, last } } } }
Weights: recency (recent years up) × competitiveness (friendly 0.5, qualifier/NL 1.0,
major finals 1.5) — friendlies are noise, tournament form is signal.
"""
import datetime
import io
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent.parent / "data" / "soccer_form.json"
URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CUR = datetime.date.today().year
LOOKBACK = 8                 # years of history to consider (squads churn — bound it)
MIN_W = 3.0                  # weighted matches before we report a team
RECENCY = {0: 1.0, 1: 0.85, 2: 0.7, 3: 0.5, 4: 0.35, 5: 0.22, 6: 0.14, 7: 0.09}
MAJORS = ("fifa world cup", "uefa euro", "copa américa", "copa america",
          "african cup of nations", "afc asian cup", "gold cup", "confederations")


def competitiveness(tournament: str) -> float:
    t = str(tournament).lower()
    if "friendly" in t:
        return 0.5
    if "qualif" in t:
        return 1.0
    if any(m in t for m in MAJORS):
        return 1.5
    if "nations league" in t:
        return 1.0
    return 1.0


def weight(year: int, tournament: str) -> float:
    return RECENCY.get(CUR - year, 0.0) * competitiveness(tournament)


def result_char(gf: int, ga: int) -> str:
    return "W" if gf > ga else "L" if gf < ga else "D"


def streak_from(results: list) -> str:
    """Most-recent run, e.g. 'W3' (3 wins), 'U5' (5 unbeaten), 'L2', 'N4' (winless)."""
    if not results:
        return "—"
    last = results[-1]
    if last == "W":
        n = 0
        for r in reversed(results):
            if r == "W":
                n += 1
            else:
                break
        return f"W{n}"
    if last == "L":
        n = 0
        for r in reversed(results):
            if r == "L":
                n += 1
            else:
                break
        return f"L{n}"
    # draw at the tip → report unbeaten or winless run length
    unbeaten = 0
    for r in reversed(results):
        if r in ("W", "D"):
            unbeaten += 1
        else:
            break
    return f"U{unbeaten}"


def build() -> None:
    raw = urllib.request.urlopen(urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    df = pd.read_csv(io.BytesIO(raw))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df[df["date"].dt.year >= CUR - LOOKBACK]
    played = df.dropna(subset=["home_score", "away_score"]).sort_values("date")
    print(f"  {len(played)} completed internationals in last {LOOKBACK}y")

    agg = defaultdict(lambda: defaultdict(float))   # team -> weighted sums
    recent = defaultdict(list)                       # team -> chronological result chars
    hh = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))   # team->opp->sums
    hh_last = defaultdict(dict)                       # team->opp-> "date score"

    for m in played.itertuples(index=False):
        yr = m.date.year
        w = weight(yr, m.tournament)
        if w <= 0:
            continue
        hs, as_ = int(m.home_score), int(m.away_score)
        for team, opp, gf, ga in ((m.home_team, m.away_team, hs, as_),
                                  (m.away_team, m.home_team, as_, hs)):
            a = agg[team]
            a["w"] += w
            a["gf"] += gf * w; a["ga"] += ga * w
            a["pts"] += (3 if gf > ga else 1 if gf == ga else 0) * w
            a["win"] += (gf > ga) * w
            a["over25"] += ((gf + ga) > 2.5) * w
            a["btts"] += (gf > 0 and ga > 0) * w
            a["cs"] += (ga == 0) * w
            a["fts"] += (gf == 0) * w
            recent[team].append(result_char(gf, ga))
            h = hh[team][opp]
            h["n"] += w
            h["w"] += (gf > ga) * w; h["d"] += (gf == ga) * w; h["l"] += (gf < ga) * w
            h["gf"] += gf * w; h["ga"] += ga * w
            hh_last[team][opp] = f"{m.date.date()} {gf}-{ga}"

    teams = {}
    for team, a in agg.items():
        w = a["w"]
        if w < MIN_W:
            continue
        res = recent[team]
        teams[team] = {
            "form_ppg": round(a["pts"] / w, 2),
            "win_rate": round(a["win"] / w, 3),
            "gf": round(a["gf"] / w, 2),
            "ga": round(a["ga"] / w, 2),
            "over25": round(a["over25"] / w, 3),
            "btts": round(a["btts"] / w, 3),
            "clean_sheet": round(a["cs"] / w, 3),
            "failed_to_score": round(a["fts"] / w, 3),
            "streak": streak_from(res),
            "last5": "".join(res[-5:]),
            "n": round(w, 1),
        }

    h2h = defaultdict(dict)
    for team, opps in hh.items():
        if team not in teams:
            continue
        for opp, h in opps.items():
            if h["n"] < 1.0:
                continue
            h2h[team][opp] = {
                "n": round(h["n"], 1),
                "w": round(h["w"], 1), "d": round(h["d"], 1), "l": round(h["l"], 1),
                "gf": round(h["gf"] / h["n"], 2), "ga": round(h["ga"] / h["n"], 2),
                "last": hh_last[team][opp],
            }

    out = {"teams": teams, "h2h": h2h, "built": datetime.date.today().isoformat()}
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"form for {len(teams)} teams, H2H for {len(h2h)} teams -> {OUT.name}")
    print("restart edge_api (kill :8001) to load; predict-soccer returns a `profile` block")


if __name__ == "__main__":
    build()
