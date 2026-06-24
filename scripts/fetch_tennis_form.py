#!/usr/bin/env python3
"""
fetch_tennis_form.py — build H2H + recent-form + psych + partial-clutch signals
for the tennis model, from the same free source we already use.

The points+surface model is blind to: who beats whom (H2H), who's hot/cold
(recent form), who folds or fights after losing set 1 (psych), and who wins the
decider / tiebreak (clutch). This builds those four signal groups per player from
REAL match results and writes them to data/tennis_form.json. edge_api adds them as
small, capped logit nudges so they refine the line without flipping a clear fav.

Source: tennis-data.co.uk (free, current — Surface / Winner / Loser / set scores /
Best of / Date). Has NO serve/break-point/ace stats, so clutch here = deciding-set
win-rate + tiebreak-set win-rate only (the buildable slice). Re-run weekly.

Output (data/tennis_form.json):
  {
    "players": { name_key: {
        "name", "form": winrate-recency-wtd, "comeback": win% after losing set 1,
        "decider": deciding-set win%, "tb": tiebreak-set win%, "streak": signed,
        "n": matches counted } },
    "h2h": { name_key: { opp_key: {"all": share, "Hard":, "Clay":, "Grass":,
        "n": meetings} } }   # share = recency-wtd win share of THIS player vs opp
  }
"""
import datetime
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent.parent / "data" / "tennis_form.json"
CUR = datetime.date.today().year
YEAR_WEIGHT = {CUR: 3.0, CUR - 1: 2.0, CUR - 2: 1.0}   # recent form weighted up
ATP = "http://www.tennis-data.co.uk/{y}/{y}.xlsx"
WTA = "http://www.tennis-data.co.uk/{y}w/{y}.xlsx"

MIN_MATCHES = 8       # weighted matches before we trust form/psych/clutch rates
MIN_DECIDER = 5       # deciding-set matches before we trust the decider rate
MIN_TB = 6            # tiebreak sets before we trust the tb rate
MIN_H2H = 2           # meetings before we trust an H2H share
STREAK_CAP = 6        # cap reported streak magnitude

SET_COLS = [("W1", "L1"), ("W2", "L2"), ("W3", "L3"), ("W4", "L4"), ("W5", "L5")]


def name_key(full: str):
    """Match 'Tiafoe F.' (source) and 'Frances Tiafoe' (ratings) to one key:
    (last surname word, first initial). Mirrors fetch_tennis_surface.py exactly."""
    toks = str(full).replace(".", "").split()
    if len(toks) < 2:
        return None
    if len(toks[-1]) == 1:                      # 'Tiafoe F' -> initial is last token
        return (toks[-2].lower(), toks[-1][0].lower())
    return (toks[-1].lower(), toks[0][0].lower())   # 'Frances Tiafoe' / 'F Tiafoe'


def load_year(url: str, year: int) -> pd.DataFrame:
    suffix = "w" if url.endswith("w/{y}.xlsx".format(y=year)) or f"{year}w" in url else "m"
    tmp = f"/tmp/tdform_{year}_{suffix}.xlsx"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        f.write(r.read())
    df = pd.read_excel(tmp)
    keep = ["Date", "Surface", "Winner", "Loser", "Best of"] + [c for p in SET_COLS for c in p]
    have = [c for c in keep if c in df.columns]
    return df[have]


def load_matches() -> list:
    """Return chronologically sorted match rows with weights."""
    frames = []
    for tmpl, tour in ((ATP, "atp"), (WTA, "wta")):
        for yr, wt in YEAR_WEIGHT.items():
            try:
                df = load_year(tmpl.format(y=yr), yr)
                df = df.copy()
                df["__wt"] = wt
                frames.append(df)
                print(f"  {tour} {yr}: {len(df)} matches (w={wt})")
            except Exception as e:
                print(f"  {tour} {yr}: skip ({e})")
    if not frames:
        return []
    allm = pd.concat(frames, ignore_index=True)
    allm["Date"] = pd.to_datetime(allm.get("Date"), errors="coerce")
    return allm.sort_values("Date", na_position="first").to_dict("records")


def set_scores(m: dict):
    """Yield (winner_games, loser_games) per completed set in the match."""
    for wc, lc in SET_COLS:
        wv, lv = m.get(wc), m.get(lc)
        if pd.isna(wv) or pd.isna(lv):
            continue
        try:
            yield int(wv), int(lv)
        except (TypeError, ValueError):
            continue


def build():
    rows = load_matches()
    if not rows:
        raise SystemExit("no match data — tennis-data.co.uk unreachable?")

    # Per-player weighted accumulators.
    wins = defaultdict(float); losses = defaultdict(float)
    cb_chance = defaultdict(float); cb_win = defaultdict(float)     # comeback after set 1
    dec_played = defaultdict(float); dec_won = defaultdict(float)   # deciding set
    tb_played = defaultdict(float); tb_won = defaultdict(float)     # tiebreak sets
    seq = defaultdict(list)                                          # chronological W/L for streak
    # H2H: hh[(player, opp)][surface] = weighted wins of player over opp.
    hh = defaultdict(lambda: defaultdict(float))
    hh_n = defaultdict(float)

    for m in rows:
        kw, kl = name_key(m.get("Winner")), name_key(m.get("Loser"))
        if not kw or not kl:
            continue
        wt = float(m.get("__wt", 1.0))
        surf = str(m.get("Surface")).title()
        surf = surf if surf in ("Hard", "Clay", "Grass") else "Other"
        sets = list(set_scores(m))

        wins[kw] += wt; losses[kl] += wt
        seq[kw].append(1); seq[kl].append(0)

        # H2H (player-relative win share, overall + per surface).
        hh[(kw, kl)]["all"] += wt; hh[(kl, kw)]["all"] += 0.0
        if surf in ("Hard", "Clay", "Grass"):
            hh[(kw, kl)][surf] += wt
            hh[(kl, kw)][surf] += 0.0
        hh_n[(kw, kl)] += wt; hh_n[(kl, kw)] += wt

        if sets:
            # Comeback after dropping set 1 (winner's view, then loser's view).
            w1, l1 = sets[0]
            if w1 < l1:                     # winner lost set 1 but won match
                cb_chance[kw] += wt; cb_win[kw] += wt
            if l1 < w1:                     # loser lost set 1 and lost match
                cb_chance[kl] += wt
            # Deciding set: match reached the max set for its format.
            bo = m.get("Best of")
            try:
                bo = int(bo)
            except (TypeError, ValueError):
                bo = 3
            need = 5 if bo == 5 else 3
            if len(sets) >= need:
                dec_played[kw] += wt; dec_won[kw] += wt
                dec_played[kl] += wt
            # Tiebreak sets (a set decided 7-6 / 6-7).
            for wg, lg in sets:
                if {wg, lg} == {7, 6}:
                    tb_played[kw] += wt; tb_won[kw] += wt
                    tb_played[kl] += wt

    players = {}
    everyone = set(wins) | set(losses)
    for k in everyone:
        tot = wins[k] + losses[k]
        if tot < MIN_MATCHES:
            continue
        rec = {"name": None, "n": round(tot, 1), "form": round(wins[k] / tot - 0.5, 3)}
        if cb_chance[k] >= 3:
            rec["comeback"] = round(cb_win[k] / cb_chance[k], 3)
        if dec_played[k] >= MIN_DECIDER:
            rec["decider"] = round(dec_won[k] / dec_played[k], 3)
        if tb_played[k] >= MIN_TB:
            rec["tb"] = round(tb_won[k] / tb_played[k], 3)
        s = seq[k][-STREAK_CAP:]
        streak = 0
        for r in reversed(seq[k]):
            if not s:
                break
            if streak == 0:
                streak = 1 if r == 1 else -1
                last = r
            elif r == last and abs(streak) < STREAK_CAP:
                streak += 1 if r == 1 else -1
            else:
                break
        rec["streak"] = streak
        players["%s|%s" % k] = rec

    h2h = defaultdict(dict)
    for (p, o), surfmap in hh.items():
        n = hh_n[(p, o)]
        if n < MIN_H2H:
            continue
        entry = {"n": round(n, 1), "all": round(surfmap["all"] / n - 0.5, 3)}
        for s in ("Hard", "Clay", "Grass"):
            # per-surface meetings count = this player's + opp's surface meetings
            sn = hh[(p, o)][s] + hh[(o, p)][s]
            if sn >= MIN_H2H:
                entry[s] = round(hh[(p, o)][s] / sn - 0.5, 3)
        h2h["%s|%s" % p]["%s|%s" % o] = entry

    out = {"players": players, "h2h": h2h,
           "built": datetime.date.today().isoformat()}
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"form/psych/clutch for {len(players)} players, "
          f"H2H for {len(h2h)} players -> {OUT.name}")
    print("restart edge_api (kill :8001) to load; H2H uses match surface when available")


if __name__ == "__main__":
    build()
