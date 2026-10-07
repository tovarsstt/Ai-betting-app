#!/usr/bin/env python3
"""
parlay_deep_sim.py — full-depth simulation of a tennis games-handicap parlay.

Layers (each one fixes a specific way a plain point-by-point sim lies):
  1. Bernoulli point process — every point is a Bernoulli trial, games/sets/match
     built bottom-up (tennis_games_model.simulate_match).
  2. Beta-posterior parameter uncertainty — a serve-point rate measured on 12
     matches is NOT 0.518, it is 0.518 +/- ~0.02, and hold% is steep in that rate.
     Each outer draw samples both players' serve-point rates from Beta(p*n, (1-p)*n)
     (n = serve points ~ matches*60), re-anchors the level to the market ML, then
     runs the inner Monte Carlo. The reported probability is the posterior mean,
     with a credible interval — thin-data matches get honestly wider.
  3. Measured margin-tail widening (data/tennis_margin_calibration.json) applied to
     every inner sample.
  4. Market blend — the held-out price test showed the corrected model only reaches
     PARITY with the market's own devigged handicap price (Brier 0.2522 vs 0.2511,
     blend best at 0.2506), so the final leg probability is the 50/50 blend.
  5. Parlay maths — legs are different matches (independent): joint = product of
     leg probabilities; exact binomial-style enumeration of every leg combination
     plus a Monte Carlo of the ticket, EV and bankroll outcomes.

Usage: python3 scripts/parlay_deep_sim.py   (legs defined at the bottom)
"""
from __future__ import annotations

import itertools
import multiprocessing as mp
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402

POINTS_PER_MATCH = 60          # serve points a player contributes per match (approx)
OUTER, CAL_SIMS, INNER = 240, 500, 3000


def _beta(rng: random.Random, p: float, n: float) -> float:
    n = max(n, 50.0)
    return min(0.85, max(0.35, rng.betavariate(p * n, (1 - p) * n)))


def _draw(args):
    a, b, target_a, line, seed = args
    rng = random.Random(seed)
    doc = tgm.load()["players"]
    ka, kb = tgm.player_key(a, doc), tgm.player_key(b, doc)
    pa0, pb0 = tgm.point_prob(doc[ka]), tgm.point_prob(doc[kb])
    pa = _beta(rng, pa0, doc[ka].get("n", 30) * POINTS_PER_MATCH)
    pb = _beta(rng, pb0, doc[kb].get("n", 30) * POINTS_PER_MATCH)
    lo, hi = -0.08, 0.08                      # re-anchor level to the market ML
    for _ in range(10):
        d = (lo + hi) / 2
        m = tgm.simulate_match(pa + d, pb - d, 3, n_sims=CAL_SIMS, seed=rng.randint(1, 10**6))["match_prob_a"]
        lo, hi = (d, hi) if m < target_a else (lo, d)
    d = (lo + hi) / 2
    sim = tgm.simulate_match(pa + d, pb - d, 3, n_sims=INNER, seed=rng.randint(1, 10**6))
    margins = tgm.scale_margins(sim["margins"])
    cover = sum(1 for m in margins if m + line > 0) / len(margins)
    return cover, sim["match_prob_a"]


def leg_probability(a, b, target_a, line, market_p, pool) -> dict:
    jobs = [(a, b, target_a, line, 1000 + i) for i in range(OUTER)]
    res = pool.map(_draw, jobs, chunksize=4)
    covers = sorted(c for c, _ in res)
    sim_mean = st.fmean(covers)
    return {"sim_mean": sim_mean, "sim_p05": covers[int(.05 * len(covers))],
            "sim_p95": covers[int(.95 * len(covers))], "sim_sd": st.pstdev(covers),
            "market": market_p, "blend": (sim_mean + market_p) / 2}


def ticket(legs: list[dict], odds: list[float], stake: float, n_mc: int = 200_000) -> dict:
    ps = [l["blend"] for l in legs]
    combos = {}
    for outcome in itertools.product((1, 0), repeat=len(ps)):
        pr = 1.0
        for o, p in zip(outcome, ps):
            pr *= p if o else 1 - p
        combos[outcome] = pr
    total_odds = 1.0
    for o in odds:
        total_odds *= o
    p_win = combos[tuple([1] * len(ps))]
    rng = random.Random(7)
    wins = sum(all(rng.random() < p for p in ps) for _ in range(n_mc))
    ev = p_win * total_odds - 1
    # risk of ruin style: how many such tickets until the bankroll is gone
    return {"combos": combos, "p_win": p_win, "p_win_mc": wins / n_mc, "odds": total_odds,
            "ev_pct": ev * 100, "profit_if_win": stake * (total_odds - 1),
            "fair_odds": 1 / p_win, "stake": stake}


if __name__ == "__main__":
    # (name, A, B, devig market P(A wins), line for A, Stake odds, market devig P(cover))
    LEGS = [
        ("Li +5.5", "Li, Ann", "Svitolina, Elina", 0.256, 5.5, 1.51, (1 / 1.51) / (1 / 1.51 + 1 / 2.40)),
        ("Charaeva +5.5", "Charaeva, Alina", "Zheng, Qinwen", 0.240, 5.5, 1.53, (1 / 1.53) / (1 / 1.53 + 1 / 2.35)),
    ]
    STAKE = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    print(f"margin-tail scale in use: {tgm.margin_scale()}  (1.0 = raw sim)")
    out = []
    with mp.Pool(max(1, mp.cpu_count() - 2)) as pool:
        for name, a, b, tgt, line, odds, mkt in LEGS:
            r = leg_probability(a, b, tgt, line, mkt, pool)
            out.append(r)
            print(f"\n{name} @ {odds}: sim {r['sim_mean']:.3f} (90% CI {r['sim_p05']:.3f}-{r['sim_p95']:.3f}) | "
                  f"market devig {r['market']:.3f} | BLEND {r['blend']:.3f} | fair odds {1 / r['blend']:.2f} | "
                  f"EV {(r['blend'] * odds - 1) * 100:+.1f}%")
    t = ticket(out, [l[5] for l in LEGS], STAKE)
    print(f"\nTICKET x{t['odds']:.2f} stake ${STAKE:.2f}: P(win)={t['p_win']:.3f} (MC {t['p_win_mc']:.3f}) "
          f"fair odds {t['fair_odds']:.2f} | EV {t['ev_pct']:+.1f}% | pays +${t['profit_if_win']:.2f} / loses -${STAKE:.2f}")
    for k, v in t["combos"].items():
        print(f"   legs {k}: {v:.3f}")
