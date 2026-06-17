#!/usr/bin/env python3
"""
fetch_tennis_surface.py — build per-player SURFACE affinity for the tennis model.

Tennis is surface-driven: a grass specialist (Maria) is far better on grass than
their overall ranking suggests. The points model is blind to this, so it misreads
them. This builds a `surface_aff` logit nudge per player per surface from REAL,
up-to-date match results.

Source: tennis-data.co.uk (free, current — has Surface / Winner / Loser / odds).
We use it instead of GitHub/Sackmann because GitHub is unreachable from some
sandboxes; tennis-data is plain HTTP and stays current through the live season.

surface_aff[surface] = SCALE * (surface_win_rate - overall_win_rate), recency-
weighted (this season heaviest), only when the player has enough surface matches.
The model adds it to the win-prob logit (edge_api tennis branch). Re-run weekly.
"""
import datetime
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

RATINGS = Path(__file__).parent.parent / "data" / "all_ratings.json"
SCALE = 3.0
CAP = 0.8
MIN_MATCHES = 10          # weighted surface matches needed to trust a rate
CUR = datetime.date.today().year
YEAR_WEIGHT = {CUR: 3.0, CUR - 1: 2.0, CUR - 2: 1.0}   # recent form weighted up
ATP = "http://www.tennis-data.co.uk/{y}/{y}.xlsx"
WTA = "http://www.tennis-data.co.uk/{y}w/{y}.xlsx"


def load_year(url: str, year: int) -> pd.DataFrame:
    tmp = f"/tmp/td_{year}_{'w' if 'w' in url else 'm'}.xlsx"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        f.write(r.read())
    df = pd.read_excel(tmp)
    return df[["Surface", "Winner", "Loser"]].dropna()


def matches() -> list:
    rows = []
    for tmpl, tour in ((ATP, "atp"), (WTA, "wta")):
        for yr, wt in YEAR_WEIGHT.items():
            try:
                df = load_year(tmpl.format(y=yr), yr)
                for _, m in df.iterrows():
                    rows.append((str(m.Surface).title(), str(m.Winner), str(m.Loser), wt))
                print(f"  {tour} {yr}: {len(df)} matches (w={wt})")
            except Exception as e:
                print(f"  {tour} {yr}: skip ({e})")
    return rows


def name_key(full: str):
    """Match 'Tiafoe F.' (tennis-data) and 'Frances Tiafoe' (ratings) to one key:
    (last surname word, first initial)."""
    toks = full.replace(".", "").split()
    if len(toks) < 2:
        return None
    if len(toks[-1]) == 1:                 # 'Tiafoe F' -> initial is the last token
        return (toks[-2].lower(), toks[-1][0].lower())
    return (toks[-1].lower(), toks[0][0].lower())   # 'Frances Tiafoe'


def main() -> None:
    rows = matches()
    if not rows:
        raise SystemExit("no match data — tennis-data.co.uk unreachable?")
    w = defaultdict(float); l = defaultdict(float)
    sw = defaultdict(lambda: defaultdict(float)); sl = defaultdict(lambda: defaultdict(float))
    for surf, win, los, wt in rows:
        if surf not in ("Hard", "Clay", "Grass"):
            continue
        kw, kl = name_key(win), name_key(los)
        if kw:
            w[kw] += wt; sw[kw][surf] += wt
        if kl:
            l[kl] += wt; sl[kl][surf] += wt

    allr = json.load(open(RATINGS))
    tennis = dict(allr.get("Tennis") or {})
    rating_key = {}
    for name in tennis:
        k = name_key(name)
        if k:
            rating_key.setdefault(k, name)   # first wins on collision

    hit = 0
    for k, fullname in rating_key.items():
        tot = w[k] + l[k]
        if tot < 10:
            continue
        overall = w[k] / tot
        surfs = {}
        for s in ("Hard", "Clay", "Grass"):
            n = sw[k][s] + sl[k][s]
            if n >= MIN_MATCHES:
                nudge = max(-CAP, min(CAP, SCALE * (sw[k][s] / n - overall)))
                if abs(nudge) > 0.01:
                    surfs[s] = round(nudge, 3)
        if surfs:
            tennis[fullname] = {**tennis[fullname], "surface_aff": surfs}
            hit += 1
    allr["Tennis"] = tennis
    json.dump(allr, open(RATINGS, "w"), ensure_ascii=False)
    print(f"surface_aff set for {hit} rated players")
    print("restart edge_api (kill :8001) to load; pass surface=Grass|Clay|Hard to /predict")


if __name__ == "__main__":
    main()
