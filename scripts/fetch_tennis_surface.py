#!/usr/bin/env python3
"""
fetch_tennis_surface.py — build per-player SURFACE affinity for the tennis model.

Tennis is surface-driven: a grass specialist (Maria) or clay grinder is far
better than their overall ranking on that surface. The points model is blind to
this, so it misreads those players. This builds a `surface_aff` nudge per player
per surface from real match results (Jeff Sackmann's tennis_atp / tennis_wta —
the standard open dataset, with `surface`, `winner_name`, `loser_name`).

surface_aff[surface] = SCALE * (surface_win_rate - overall_win_rate), only when
the player has >= MIN_MATCHES on that surface. The model adds it to the win-prob
logit (see edge_api tennis branch). Positive = overperforms on that surface.

Run on a machine with GitHub access (the sandbox here is firewalled to ESPN, so
this was NOT tested in-session — if a URL/year 404s, adjust YEARS and re-run):
    ./.venv/bin/python scripts/fetch_tennis_surface.py
"""
import csv
import io
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

RATINGS = Path(__file__).parent.parent / "data" / "all_ratings.json"
YEARS = (2024, 2025, 2026)
SCALE = 3.0          # surface-overperformance -> logit nudge
CAP = 0.8            # clamp the nudge
MIN_MATCHES = 12     # need enough surface matches to trust the rate
SOURCES = {
    "atp": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{}.csv",
    "wta": "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{}.csv",
}


def load_matches() -> list:
    rows = []
    for tour, tmpl in SOURCES.items():
        for yr in YEARS:
            url = tmpl.format(yr)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    text = r.read().decode("utf-8", "replace")
                rows += list(csv.DictReader(io.StringIO(text)))
                print(f"  {tour} {yr}: ok")
            except Exception as e:
                print(f"  {tour} {yr}: skip ({e})")
    return rows


def build_affinity(rows: list) -> dict:
    # per player: wins/losses overall and by surface
    w = defaultdict(int); l = defaultdict(int)
    sw = defaultdict(lambda: defaultdict(int)); sl = defaultdict(lambda: defaultdict(int))
    for m in rows:
        s = (m.get("surface") or "").title()
        win, los = m.get("winner_name"), m.get("loser_name")
        if not (win and los and s in ("Hard", "Clay", "Grass")):
            continue
        w[win] += 1; l[los] += 1
        sw[win][s] += 1; sl[los][s] += 1
    aff = {}
    players = set(w) | set(l)
    for p in players:
        tot = w[p] + l[p]
        if tot < 10:
            continue
        overall = w[p] / tot
        surfs = {}
        for s in ("Hard", "Clay", "Grass"):
            n = sw[p][s] + sl[p][s]
            if n >= MIN_MATCHES:
                rate = sw[p][s] / n
                nudge = max(-CAP, min(CAP, SCALE * (rate - overall)))
                if abs(nudge) > 0.01:
                    surfs[s] = round(nudge, 3)
        if surfs:
            aff[p] = surfs
    return aff


def main() -> None:
    rows = load_matches()
    if not rows:
        raise SystemExit("no match data fetched — check GitHub access / YEARS")
    aff = build_affinity(rows)
    allr = json.load(open(RATINGS))
    tennis = dict(allr.get("Tennis") or {})
    hit = 0
    for name, surfs in aff.items():
        if name in tennis:
            tennis[name] = {**tennis[name], "surface_aff": surfs}
            hit += 1
    allr["Tennis"] = tennis
    json.dump(allr, open(RATINGS, "w"), ensure_ascii=False)
    print(f"surface_aff built for {len(aff)} players, merged into {hit} rated players")
    print("restart edge_api (kill :8001) to load. Pass surface=Grass|Clay|Hard to /predict.")


if __name__ == "__main__":
    main()
