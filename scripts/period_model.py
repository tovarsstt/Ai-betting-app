#!/usr/bin/env python3
"""
period_model.py — quarter / half / OT / full-game markets, from REAL games.

The engine could only price full-game lines. Period markets were refused because
the only tool available was an independent-increments proxy (halve the margin,
divide sigma by root two). That is defensible for basketball and wrong for
football: game script couples the quarters hard. A team three scores ahead runs
the ball and the 4th goes quiet; a team trailing throws and it does not. Treating
quarters as independent draws prices exactly the games that matter most wrong.

METHOD — importance-weighted bootstrap over whole historical games.

  1. Every candidate is a REAL game's per-period scoreline from
     data/period_scores.json (fetch_period_scores.py).
  2. Each is weighted by a Gaussian kernel on how closely its full-game TOTAL and
     MARGIN match the projection for the match being priced.
  3. Simulate by resampling those games with those weights, orienting home/away
     to our fixture.

Three things fall out of resampling whole games that a period-by-period model has
to fake, and usually fakes badly:

  * CORRELATION between periods is carried automatically — the sample is a real
    game, so the 4th quarter already knows what the 3rd did.
  * DISCRETENESS survives. NFL points arrive in 3s and 7s, which is precisely
    what decides a −2.5 first-quarter line. Nothing here is rescaled into
    fractional points.
  * OVERTIME is priced off its real observed frequency, not a guess.

The honest limitation, stated rather than buried: this reweights a league-wide
sample toward the projected total and margin. It does NOT know that THIS team is
a fast starter or a second-half team. It prices the shape of a typical game with
this total and margin, not this fixture's personality.

Run: python3 scripts/period_model.py --sport nfl --total 45 --margin -6.5
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Optional, Sequence

DATA = Path(__file__).parent.parent / "data"
SCORES = DATA / "period_scores.json"

# Kernel widths for the importance weights, in points. Wide enough to keep the
# effective sample size usable, tight enough that the games resampled actually
# resemble the one being priced.
TOTAL_BANDWIDTH = {"nfl": 7.0, "nba": 12.0, "nhl": 1.6, "wnba": 10.0}
MARGIN_BANDWIDTH = {"nfl": 7.0, "nba": 10.0, "nhl": 1.6, "wnba": 9.0}
DEFAULT_SIMS = 20_000
MIN_ESS = 25.0     # effective sample size below this = too thin to price


def load(sport: str) -> Optional[dict]:
    try:
        return json.loads(SCORES.read_text()).get(sport.lower())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _weights(games: Sequence[dict], total: float, margin: float,
             bw_t: float, bw_m: float) -> list[float]:
    """Gaussian kernel on (full-game total, full-game margin) distance."""
    out = []
    for g in games:
        h, a = sum(g["home_periods"]), sum(g["away_periods"])
        dt = (h + a - total) / bw_t
        dm = ((h - a) - margin) / bw_m
        out.append(math.exp(-0.5 * (dt * dt + dm * dm)))
    return out


def simulate(sport: str, proj_total: float, proj_margin: float,
             n_sims: int = DEFAULT_SIMS, seed: Optional[int] = None) -> dict:
    """Price every period market for one fixture.

    `proj_margin` is HOME minus AWAY, so a home favourite by 6.5 is +6.5.
    """
    doc = load(sport)
    if not doc or not doc.get("games"):
        return {"error": "NO_DATA",
                "note": f"no period scores for {sport} — run fetch_period_scores.py"}

    games = doc["games"]
    reg = int(doc.get("regulation_periods", 4))
    bw_t = TOTAL_BANDWIDTH.get(sport.lower(), 8.0)
    bw_m = MARGIN_BANDWIDTH.get(sport.lower(), 8.0)
    w = _weights(games, proj_total, proj_margin, bw_t, bw_m)
    tw = sum(w)
    if tw <= 0:
        return {"error": "NO_COMPARABLE_GAMES",
                "note": "no historical game resembles this projection"}

    # Kish effective sample size — how many real games this price actually rests
    # on. A weighted mean of 300 games can be worth 4; say so rather than
    # implying 300.
    ess = (tw ** 2) / sum(x * x for x in w)
    if ess < MIN_ESS:
        return {"error": "TOO_THIN", "effective_sample": round(ess, 1),
                "note": f"only ~{ess:.0f} comparable games — refusing to price"}

    rng = random.Random(seed)
    n_periods = max(len(g["home_periods"]) for g in games)
    hp_tot = [0.0] * n_periods
    ap_tot = [0.0] * n_periods
    # margins[p] / totals[p] hold one simulated value per draw, per period.
    margins: list[list[float]] = [[] for _ in range(n_periods)]
    totals: list[list[float]] = [[] for _ in range(n_periods)]
    cum_margin: list[list[float]] = [[] for _ in range(n_periods)]
    cum_total: list[list[float]] = [[] for _ in range(n_periods)]
    ot_hits = 0

    for _ in range(n_sims):
        g = rng.choices(games, weights=w, k=1)[0]
        hp, ap = g["home_periods"], g["away_periods"]
        if g.get("ot"):
            ot_hits += 1
        ch = ca = 0.0
        for p in range(n_periods):
            h = hp[p] if p < len(hp) else 0.0
            a = ap[p] if p < len(ap) else 0.0
            hp_tot[p] += h
            ap_tot[p] += a
            margins[p].append(h - a)
            totals[p].append(h + a)
            ch += h
            ca += a
            cum_margin[p].append(ch - ca)
            cum_total[p].append(ch + ca)

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    periods = []
    for p in range(n_periods):
        label = (f"P{p + 1}" if p < reg else f"OT{p - reg + 1}")
        periods.append({
            "period": label,
            "mean_total": round(_mean(totals[p]), 2),
            "mean_margin_home": round(_mean(margins[p]), 2),
            "margins": margins[p],
            "totals": totals[p],
        })

    segments = {}
    for p in range(min(reg, n_periods)):
        segments[f"through_P{p + 1}"] = {"margins": cum_margin[p],
                                         "totals": cum_total[p]}
    if reg >= 4 and n_periods >= 4:
        segments["1H"] = {"margins": cum_margin[1], "totals": cum_total[1]}
        h2m = [cum_margin[3][i] - cum_margin[1][i] for i in range(n_sims)]
        h2t = [cum_total[3][i] - cum_total[1][i] for i in range(n_sims)]
        segments["2H"] = {"margins": h2m, "totals": h2t}
    segments["FULL"] = {"margins": cum_margin[n_periods - 1],
                        "totals": cum_total[n_periods - 1]}

    return {
        "sport": sport.lower(),
        "projection": {"total": proj_total, "margin_home": proj_margin},
        "n_sims": n_sims,
        "historical_games": len(games),
        "effective_sample": round(ess, 1),
        "regulation_periods": reg,
        "p_overtime": round(ot_hits / n_sims, 4),
        "league_ot_rate": doc.get("ot_rate"),
        "periods": [{k: v for k, v in p.items() if k not in ("margins", "totals")}
                    for p in periods],
        "_segments": segments,
        "method": "importance-weighted bootstrap over real games — period "
                  "correlation and integer scoring preserved, not modelled",
    }


def price(sim: dict, segment: str, market: str, line: float) -> dict:
    """Probability for one line on one segment.

    segment: "P1".."P4", "through_P2", "1H", "2H", "FULL"
    market:  "spread" (home line, e.g. -2.5) or "total" (over/under)
    """
    if "error" in sim:
        return sim
    segs = sim.get("_segments") or {}
    key = (segment if segment in segs
           else f"through_{segment}" if f"through_{segment}" in segs else None)
    if key is None:
        return {"error": "BAD_SEGMENT", "segment": segment, "have": sorted(segs)}
    vals = segs[key]["margins" if market == "spread" else "totals"]

    n = len(vals)
    if market == "spread":
        # Home covers -x when the home margin exceeds x.
        hit = sum(1 for v in vals if v + line > 0)
        push = sum(1 for v in vals if v + line == 0)
        side = f"home {line:+g}"
    else:
        hit = sum(1 for v in vals if v > line)
        push = sum(1 for v in vals if v == line)
        side = f"over {line}"
    p = hit / n
    return {
        "segment": segment, "market": market, "line": line, "side": side,
        "win_prob": round(p, 4),
        "opposite_prob": round((n - hit - push) / n, 4),
        "push_prob": round(push / n, 4),
        "min_odds": round(1.05 / p, 2) if p > 0 else None,
        "effective_sample": sim.get("effective_sample"),
    }


def board(sport: str, proj_total: float, proj_margin: float,
          seed: Optional[int] = None) -> dict:
    """Every period market for a fixture, graded and ranked winning-first."""
    sim = simulate(sport, proj_total, proj_margin, seed=seed)
    if "error" in sim:
        return sim
    import win_simulator as wsim

    rows = []
    segs = ["through_P1", "1H", "through_P3", "FULL"]
    labels = {"through_P1": "1Q", "1H": "1H", "through_P3": "3Q", "FULL": "GAME"}
    for seg in segs:
        if seg not in (sim.get("_segments") or {}):
            continue
        vals_m = sim["_segments"][seg]["margins"]
        vals_t = sim["_segments"][seg]["totals"]
        mid_m = sorted(vals_m)[len(vals_m) // 2]
        mid_t = sorted(vals_t)[len(vals_t) // 2]
        for ln in (mid_m - 3.5, mid_m - 0.5, mid_m + 3.5):
            r = price(sim, seg, "spread", -round(ln * 2) / 2)
            v, note = wsim._verdict(r["win_prob"])
            rows.append({**r, "label": f"{labels[seg]} spread", "verdict": v, "note": note})
        for ln in (mid_t - 4.5, mid_t + 0.5, mid_t + 4.5):
            r = price(sim, seg, "total", round(ln * 2) / 2)
            v, note = wsim._verdict(r["win_prob"])
            rows.append({**r, "label": f"{labels[seg]} total", "verdict": v, "note": note})
    rows.sort(key=lambda r: -r["win_prob"])
    return {k: v for k, v in sim.items() if k != "_segments"} | {"markets": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--margin", type=float, required=True,
                    help="HOME minus AWAY; home favourite by 6.5 is +6.5")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    print(json.dumps(board(a.sport, a.total, a.margin, a.seed), indent=1))
