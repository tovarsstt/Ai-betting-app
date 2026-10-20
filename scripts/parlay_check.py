"""
parlay_check.py — price a multi-leg ticket with the FULL toolkit (CLAUDE.md P(win) Rule + Total-Anchor Rule).

Per leg, every goal-rate tool gives a Dixon-Coles score matrix, anchored to the market total:
  elo (+Monte Carlo of its matrix), poisson_regression, eigenvector, market-anchored DC (from the sheet's 1X2 + O/U);
  pure 1X2 legs add Skellam and the binomial W-D-L rates. Leg P = 50% mean of model groups + 50% market-anchored view.
Leg kinds: dc (1X/X2/12), win, over, team_total_over, win_and_over, 1up.
1UP (paid as won if the team is ever 1+ goal ahead): exact — final score from the matrix, then the probability that a
uniformly random ordering of the goals ever puts the team ahead (lattice-path count). Assumes constant goal rates
over the match (no score effects) and Stake's usual 1UP rule: both are approximations, stated, not verified.
Report order: P(win) first -> odds/payout -> EV last. The legs are different matches, so P(ticket) = product of legs;
a 400k-simulation of the whole ticket re-checks it.

    python3 scripts/parlay_check.py data/slips/<file>.json data/sheets/<file>.json
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

import betting_math as bm
import pwin_ensemble as pe
import sheet_picks as sp
import soccer_markets as sm

DATA = Path(__file__).parent.parent / "data"
SEED = 20261020


@lru_cache(maxsize=None)
def _never_ahead_paths(h: int, a: int) -> int:
    """# of orderings of h 'team' goals and a 'opp' goals where the team is never strictly ahead at any prefix."""
    @lru_cache(maxsize=None)
    def f(x: int, y: int) -> int:           # x team goals, y opp goals placed so far (team never ahead => x <= y always)
        if x > y:
            return 0
        if x == h and y == a:
            return 1
        return (f(x + 1, y) if x < h else 0) + (f(x, y + 1) if y < a else 0)
    return f(0, 0)


def p_ever_ahead(h: int, a: int) -> float:
    """P(team ever leads) given final goal counts and a uniformly random order of the h+a goals."""
    if h == 0:
        return 0.0
    return 1.0 - _never_ahead_paths(h, a) / math.comb(h + a, h)


def leg_prob(M: list[list[float]], leg: dict) -> float:
    n = len(M)
    kind = leg["kind"]
    tot = 0.0
    for i in range(n):
        for j in range(n):
            p = M[i][j]
            if p <= 0:
                continue
            if kind == "dc":
                ok = {"1X": i >= j, "X2": j >= i, "12": i != j}[leg["sel"]]
                tot += p if ok else 0
            elif kind == "win":
                tot += p if (i > j if leg["team"] == "home" else j > i) else 0
            elif kind == "over":
                tot += p if i + j > leg["line"] else 0
            elif kind == "team_total_over":
                tot += p if (i if leg["team"] == "home" else j) > leg["line"] else 0
            elif kind == "win_and_over":
                tot += p if ((i > j) if leg["team"] == "home" else (j > i)) and i + j > leg["line"] else 0
            elif kind == "1up":
                h, a = (i, j) if leg["team"] == "home" else (j, i)
                tot += p * (1.0 if h > a else p_ever_ahead(h, a))
            else:
                raise ValueError(kind)
    return tot


def sample_leg(M: list[list[float]], leg: dict, n: int, rng: np.random.Generator) -> np.ndarray:
    """Boolean outcome per simulation: sample the final score, then (for 1UP) a random goal order."""
    flat = np.array([x for r in M for x in r]); flat /= flat.sum()
    k = len(M)
    idx = rng.choice(len(flat), size=n, p=flat)
    hs, as_ = idx // k, idx % k
    kind = leg["kind"]
    if kind == "dc":
        return {"1X": hs >= as_, "X2": as_ >= hs, "12": hs != as_}[leg["sel"]]
    if kind == "win":
        return hs > as_ if leg["team"] == "home" else as_ > hs
    if kind == "over":
        return hs + as_ > leg["line"]
    if kind == "team_total_over":
        return (hs if leg["team"] == "home" else as_) > leg["line"]
    if kind == "win_and_over":
        return ((hs > as_) if leg["team"] == "home" else (as_ > hs)) & (hs + as_ > leg["line"])
    h, a = (hs, as_) if leg["team"] == "home" else (as_, hs)
    out = h > a
    for hh, aa in set(zip(h[~out].tolist(), a[~out].tolist())):
        m = (~out) & (h == hh) & (a == aa)
        cnt = int(m.sum())
        if hh == 0 or cnt == 0:
            continue
        seq = np.array([1] * hh + [-1] * aa)
        shuf = rng.permuted(np.tile(seq, (cnt, 1)), axis=1)
        out[np.where(m)[0]] = (np.cumsum(shuf, axis=1).max(axis=1) > 0)
    return out


def leg_views(ctx, match: str, sheet: dict, leg: dict) -> dict:
    """tool name -> leg probability (all anchored to the market total) for one leg, plus the market-anchored view."""
    m = sheet[match]
    ml_dec = m["x12"]
    pw = bm.devig_power(ml_dec)
    ou = sp.two_way(m["ou"]["2.5"])
    mtotal = pe.market_total_from_ou(float(pw[0]), float(pw[2]), ou[0], 2.5)
    to_am = lambda d: int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))
    tools = pe.soccer_tools(ctx, m["home"], m["away"], {"home": to_am(ml_dec[0]), "draw": to_am(ml_dec[1]), "away": to_am(ml_dec[2])},
                            2.5, market_total=mtotal)
    views, groups = {}, {}
    for t in tools:
        if t.kind == "model" and t.lam:
            views[t.name] = leg_prob(sm.score_matrix(*t.lam), leg)
    lh, la = sp.anchored_lambdas(pw, ou[0])
    mkt = leg_prob(sm.score_matrix(lh, la), leg)
    # extra 1X2-only views for pure result legs
    if leg["kind"] in ("dc", "win"):
        for t in tools:
            if t.kind == "model" and t.name in ("elo_skellam", "binomial_wdl_rates", "elo_monte_carlo_200k") and t.probs:
                pr = sp.from_1x2(t.probs)
                key = leg["sel"] if leg["kind"] == "dc" else ("H" if leg["team"] == "home" else "A")
                views[t.name] = pr[key]
    groups = {"elo": [v for k, v in views.items() if k in ("elo_poisson_dixon_coles", "elo_skellam", "elo_monte_carlo_200k")],
              "poisson_regression": [views[k] for k in ("poisson_regression",) if k in views],
              "eigenvector": [views[k] for k in ("eigenvector_keener",) if k in views],
              "binomial": [views[k] for k in ("binomial_wdl_rates",) if k in views]}
    gm = [float(np.mean(v)) for v in groups.values() if v]
    p_model = float(np.mean(gm))
    final = pe.MODEL_WEIGHT * p_model + (1 - pe.MODEL_WEIGHT) * mkt
    return {"views": views, "market_anchored": mkt, "p_model": p_model, "final": final, "mtotal": mtotal,
            "lam_mkt": (lh, la), "lams": {t.name: t.lam for t in tools if t.lam}}


def mc_ticket(ctx, slip: dict, sheet: dict, n: int = 400_000) -> float:
    """Joint simulation of the whole ticket using, per leg, the FINAL-blend matrix (market-anchored λ mixed with the
    model-mean λ at the same 50/50 weight)."""
    rng = np.random.default_rng(SEED)
    ok = np.ones(n, bool)
    for leg in slip["legs"]:
        m = sheet[leg["match"]]
        pw = bm.devig_power(m["x12"]); ou = sp.two_way(m["ou"]["2.5"])
        lh, la = sp.anchored_lambdas(pw, ou[0])
        to_am = lambda d: int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))
        tools = pe.soccer_tools(ctx, m["home"], m["away"], {"home": to_am(m["x12"][0]), "draw": to_am(m["x12"][1]), "away": to_am(m["x12"][2])},
                                2.5, market_total=lh + la)
        lams = [t.lam for t in tools if t.kind == "model" and t.lam]
        mh, ma = (float(np.mean([x[0] for x in lams])), float(np.mean([x[1] for x in lams]))) if lams else (lh, la)
        # 50/50 mixture of the two matrices (model mean vs market) = the same blend the legs use
        Mm, Mk = np.array(sm.score_matrix(mh, ma)), np.array(sm.score_matrix(lh, la))
        mix = (pe.MODEL_WEIGHT * Mm + (1 - pe.MODEL_WEIGHT) * Mk).tolist()
        ok &= sample_leg(mix, leg, n, rng)
    return float(ok.mean())


def main() -> None:
    slip = json.loads(Path(sys.argv[1]).read_text())
    sheet = json.loads(Path(sys.argv[2]).read_text())["matches"]
    soc = DATA / "soccer"
    ctx = pe.build_soccer_ctx([soc / "club_results.csv", soc / "extra_league_results.csv", soc / "uefa_results.csv"])
    legs = []
    for leg in slip["legs"]:
        v = leg_views(ctx, leg["match"], sheet, leg)
        legs.append({**leg, **v, "implied": 1 / leg["odds"], "ev": v["final"] * leg["odds"] - 1})
    p_all = math.prod(l["final"] for l in legs)
    odds = math.prod(l["odds"] for l in legs)
    print(f"=== UCL — ticket de {len(legs)} tramos, cuota total {odds:.2f} ===\n")
    print("PROBABILIDAD DE GANAR CADA TRAMO (P(win) primero, EV al final)")
    for k, l in enumerate(legs, 1):
        print(f"{k}. {l['pick']}  [{l['match']}]\n   P(win) {l['final']*100:.1f}%  (herramientas del modelo {l['p_model']*100:.1f}% | mercado-anclado {l['market_anchored']*100:.1f}%)"
              f"  | cuota {l['odds']:.2f} (el precio implica {l['implied']*100:.1f}%) | EV del tramo {l['ev']*100:+.1f}%")
        print("   por herramienta: " + ", ".join(f"{k2.replace('_dixon_coles','').replace('_',' ')} {v*100:.0f}%" for k2, v in l["views"].items()))
    print(f"\nTICKET COMPLETO: P(ganar los 7) = {p_all*100:.2f}%  | cuota {odds:.2f} -> $10 pagan ${10*odds:.2f} | EV {(p_all*odds-1)*100:+.1f}%")
    print(f"   rango por herramienta (solo modelo / solo mercado): {math.prod(l['p_model'] for l in legs)*100:.2f}% / {math.prod(l['market_anchored'] for l in legs)*100:.2f}%")
    print(f"   verificación: simulación conjunta de 400.000 tickets = {mc_ticket(ctx, slip, sheet)*100:.2f}%")
    probs = [l["final"] for l in legs]
    # distribution of number of legs hit (Poisson-binomial)
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    print("   tramos acertados: " + " | ".join(f"{k}:{dist[k]*100:.1f}%" for k in range(len(dist) - 1, -1, -1) if dist[k] > 0.0005))
    print(f"   falla exactamente 1 tramo: {dist[len(probs)-1]*100:.1f}%  (relevante si tu 'Stake Shield' cubre un tramo; no conozco sus reglas)")
    print("\nQUITANDO TRAMOS (P(win) primero):")
    rows = []
    for r in range(len(legs) - 1, 2, -1):
        for combo in itertools.combinations(range(len(legs)), r):
            p = math.prod(legs[i]["final"] for i in combo); o = math.prod(legs[i]["odds"] for i in combo)
            rows.append((p, o, combo))
    best = {}
    for p, o, c in rows:
        best.setdefault(len(c), []).append((p, o, c))
    for size in sorted(best, reverse=True):
        top_p = sorted(best[size], key=lambda x: -x[0])[0]
        top_ev = sorted(best[size], key=lambda x: -(x[0] * x[1]))[0]
        print(f"  {size} tramos: mayor P(win) = {top_p[0]*100:.1f}% (cuota {top_p[1]:.2f}, EV {(top_p[0]*top_p[1]-1)*100:+.1f}%) sin los tramos {[i+1 for i in range(len(legs)) if i not in top_p[2]]}"
              f" | mejor EV = {(top_ev[0]*top_ev[1]-1)*100:+.1f}% sin {[i+1 for i in range(len(legs)) if i not in top_ev[2]]}")
    print("\nDETALLE POR TRAMO (λ usados):")
    for k, l in enumerate(legs, 1):
        print(f"  {k}. total de mercado {l['mtotal']:.2f}; " + "; ".join(f"{n} λ {a:.2f}-{b:.2f}" for n, (a, b) in l["lams"].items()))


if __name__ == "__main__":
    main()
