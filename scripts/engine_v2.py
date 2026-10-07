#!/usr/bin/env python3
"""
engine_v2.py — MOTOR REJUVENECIDO. The engine the picks flow uses from now on.

What changed vs the old iid engine (each item was measured, see docs/ENGINE_V2.md):
  1. Hierarchical day-to-day serve-rate sd (0.05) replaces TWO fudge factors (the +1.7/+2.2-game
     totals offset and the 1.26 margin multiplier). Independently measured on 13,100 charted
     player-matches (Sackmann): 0.055 ATP / 0.051 WTA.
  2. Thin-data players get fatter tails automatically: per-player sd = sqrt(day_sd^2 + se^2),
     se from the number of matches behind the serve stats (12 matches => se ~0.019).
  3. Numba-compiled, antithetic, parallel kernel: ~9M matches/s (old loop ~90k/s).
  4. Power de-vig (best log-loss on 60k real closing lines) instead of the simple method.
  5. Final probability = 50/50 blend of simulation and the market's own de-vigged price (held-out
     winner of Brier on handicaps and totals).
  6. Uncertainty-aware Kelly: stake from the posterior of p, not the point estimate.
  7. GPD tail risk (CVaR of drawdown) for any repeated ticket; Shield-aware ticket maths.
  8. Heuristics are injected ONLY if real data calibrated them (data/heuristic_coefficients.json);
     NFL wind -> totals is calibrated; everything else is 0 by construction.
  9. Self-test: multi-replicate chi-square (Fisher-combined), numba==numpy equivalence, antithetic
     variance check, latency P50/P95/P99.

CLI:  python3 scripts/engine_v2.py selftest | scan | ticket | bench | nflwind
"""
from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm  # noqa: E402
import stochastic_engine as se  # noqa: E402
import tennis_games_model as tgm  # noqa: E402
import tennis_slate_scan as tss  # noqa: E402
import tennis_vec as tv  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
CAL = json.loads((DATA / "engine_v2_calibration.json").read_text()) if (DATA / "engine_v2_calibration.json").exists() else {}
DAY_SD: float = float(CAL.get("day_sd", 0.05))
TOTALS_OFFSET: Dict[str, float] = CAL.get("totals_offset", {"ATP": -0.067, "WTA": -0.564})
PTS_PER_MATCH = 60
_SIM = tv.simulate_nb if tv.HAVE_NUMBA else tv.simulate
CTX_PATH = DATA / "tennis_context_coefficients.json"
CTX = json.loads(CTX_PATH.read_text()) if CTX_PATH.exists() else {}


def context_effect(ctx: Optional[dict]) -> Dict[str, object]:
    """Apply ONLY data-validated context effects (never a guess). ctx keys (all optional):
    rest_days_a/b (days since last match), games_last7d_a/b, altitude_m, narratives={"birthday_a":True,...}.
    Win effects shift the ANCHOR logit (the price already contains most context; these are the
    measured incremental effects). Narrative flags are reported with what the data can rule out, but
    move nothing: no study has detected them."""
    out: Dict[str, object] = {"delta_logit": 0.0, "total_offset": 0.0, "applied": [], "narratives": []}
    if not ctx or not CTX:
        return out
    if "rest_days_a" in ctx and "rest_days_b" in ctx:
        d = min(float(ctx["rest_days_a"]), 7.0) - min(float(ctx["rest_days_b"]), 7.0)
        out["delta_logit"] += CTX["rest_days_logit_per_day"] * d
        out["applied"].append(f"rest_days diff {d:+.1f}d -> {CTX['rest_days_logit_per_day'] * d:+.4f} logit")
    if "games_last7d_a" in ctx and "games_last7d_b" in ctx:
        d = (float(ctx["games_last7d_a"]) - float(ctx["games_last7d_b"])) / 10.0
        out["delta_logit"] += CTX["load7_logit_per_10_games"] * d
        out["applied"].append(f"load7 diff {d * 10:+.0f} games -> {CTX['load7_logit_per_10_games'] * d:+.4f} logit")
    if float(ctx.get("altitude_m", 0.0)) >= 500:
        out["total_offset"] += CTX["altitude_500m_total_games"]
        out["applied"].append(f"altitude >=500m -> totals {CTX['altitude_500m_total_games']:+.2f} games")
    ns = CTX.get("not_supported", {})
    for flag, key in (("birthday_a", "win:birthday"), ("birthday_b", "win:birthday"), ("back_to_back", "win:rest_short"), ("long_prev_match", "win:prev_games")):
        if (ctx.get("narratives") or {}).get(flag) and key in ns:
            lo, hi = ns[key]["ci95"]
            out["narratives"].append(f"{flag}: no effect beyond the price detected; data rules out effects outside [{lo:+.3f}, {hi:+.3f}] logit -> applied 0")
    return out


# ── simulation ──────────────────────────────────────────────────────────────────────
def player_sd(n_matches: float, p: float) -> float:
    se_ = math.sqrt(max(p * (1 - p), 1e-6) / max(n_matches * PTS_PER_MATCH, 60.0))
    return math.sqrt(DAY_SD ** 2 + se_ ** 2)


def calibrate_level(pa: float, pb: float, sd: Tuple[float, float], target: float, iters: int = 16, n: int = 60_000) -> float:
    lo, hi = -0.10, 0.10
    for i in range(iters):
        d = (lo + hi) / 2
        w = _SIM(pa + d, pb - d, n, sd, 11 + i)["winner"]
        lo, hi = (d, hi) if (w == 0).mean() < target else (lo, d)
    return (lo + hi) / 2


def simulate_match(a: str, b: str, ml: Tuple[float, float], n: int = 400_000, seed: int = 5, ctx: Optional[dict] = None) -> Optional[dict]:
    """Level-anchored (to the power-devigged ML), hierarchical simulation of one match."""
    doc = tgm.load()["players"]
    ka, kb = tgm.player_key(a, doc), tgm.player_key(b, doc)
    if not ka or not kb:
        return None
    pa, pb = tgm.point_prob(doc[ka]), tgm.point_prob(doc[kb])
    sd = (player_sd(doc[ka].get("n", 30), pa), player_sd(doc[kb].get("n", 30), pb))
    target = float(bm.devig_power(list(ml))[0])
    ce = context_effect(ctx)
    if ce["delta_logit"]:
        target = float(1 / (1 + np.exp(-(np.log(target / (1 - target)) + ce["delta_logit"]))))
    d = calibrate_level(pa, pb, sd, target)
    r = _SIM(pa + d, pb - d, n, sd, seed)
    rows = np.column_stack([r["winner"], r["sets"][:, 0], r["sets"][:, 1], r["s1w"], r["s1g"], r["games"][:, 0], r["games"][:, 1]]).astype(np.int16)
    tour = (doc[ka].get("tour") or "ATP").upper()
    return {"rows": rows, "off": TOTALS_OFFSET.get(tour, 0.0) + ce["total_offset"], "context": ce, "k": 1.0, "ka": ka, "kb": kb, "sd": sd,
            "n_pts": (doc[ka].get("n", 0), doc[kb].get("n", 0)), "serve": (pa + d, pb - d)}


# ── staking / tickets ──────────────────────────────────────────────────────────────
def kelly_stake(p: float, model_p: float, market_p: Optional[float], odds: float, bankroll: float,
                n_eff: float = 4000.0, cap: float = 0.05) -> Dict[str, float]:
    """Uncertainty-aware Kelly. The posterior of p is Beta with mean p and variance from
    (a) disagreement between simulation and market, (b) sampling noise of n_eff points."""
    spread = abs(model_p - market_p) / 2 if market_p is not None else 0.05
    var = max(spread ** 2 + p * (1 - p) / n_eff, 1e-5)
    k = p * (1 - p) / var - 1
    a, b = max(p * k, 0.5), max((1 - p) * k, 0.5)
    f_star, f_point, g = bm.kelly_uncertain(stats.beta.rvs(a, b, size=4000, random_state=3), odds, cap=cap)
    return {"f_star": f_star, "f_point": f_point, "stake_usd": round(f_star * bankroll, 2), "growth": g}


@dataclass
class Leg:
    name: str
    p: float
    odds: float


def ticket(legs: Sequence[Leg], stake: float, shield: Optional[Tuple[int, float]] = None) -> Dict[str, object]:
    """Independent legs (different matches). shield=(min_legs_that_must_win, shield_odds)."""
    ps = np.array([l.p for l in legs])
    n = len(ps)
    outcomes = ((np.arange(2 ** n)[:, None] >> np.arange(n)[None, :]) & 1).astype(bool)      # all win/lose combos
    pr = np.prod(np.where(outcomes, ps, 1 - ps), axis=1)
    wins = outcomes.sum(1)
    full_odds = float(np.prod([l.odds for l in legs]))
    out: Dict[str, object] = {"p_all": float(pr[wins == n].sum()), "full_odds": full_odds,
                              "dist_legs_won": {int(k): float(pr[wins == k].sum()) for k in range(n + 1)}}
    out["ev_full_pct"] = (out["p_all"] * full_odds - 1) * 100
    out["fair_odds_full"] = 1 / out["p_all"]
    if shield:
        need, so = shield
        p_s = float(pr[wins >= need].sum())
        out.update({"shield_need": need, "shield_odds": so, "p_shield": p_s, "ev_shield_pct": (p_s * so - 1) * 100,
                    "fair_shield_odds": 1 / p_s})
    # repeated-ticket bankroll risk (GPD tail of max drawdown), staking 'stake' of a 60-dollar-ish bank
    rng = np.random.default_rng(2)
    p_use, o_use = (out.get("p_shield", out["p_all"]), out.get("shield_odds", full_odds))
    dd = se.bankroll_drawdowns(float(p_use), float(o_use), min(0.5, stake / 60.0), 120, 20_000, rng)
    out["drawdown_risk_120_tickets"] = se.gpd_tail_risk(dd)
    return out


# ── validation ─────────────────────────────────────────────────────────────────────
def fisher_p(ps: Sequence[float]) -> float:
    return float(stats.chi2.sf(-2 * np.sum(np.log(np.clip(ps, 1e-300, 1))), 2 * len(ps)))


def selftest() -> Dict[str, object]:
    ss = np.random.SeedSequence(2026)
    streams = [np.random.default_rng(s) for s in ss.spawn(24)]
    res: Dict[str, object] = {}
    # 1) game-hold generator vs closed form: 20 independent replicates, Fisher-combined (single tests false-alarm)
    h = float(tv.hold(np.array(0.62)))
    ps = []
    for rng in streams[:20]:
        k = int((rng.random(400_000) < h).sum())
        ps.append(se.chi_square(np.array([k, 400_000 - k]), np.array([h, 1 - h]))["p_value"])
    res["hold_generator"] = {"fisher_p": fisher_p(ps), "min_p": float(min(ps)), "biased": fisher_p(ps) < 0.01}
    # 2) numba kernel == numpy reference (win prob, total, tail) with z-tests
    n = 600_000
    a = tv.simulate(0.66, 0.62, n, 0.05, 3)
    b = _SIM(0.66, 0.62, n, 0.05, 4)
    z = lambda x, y: float((x.mean() - y.mean()) / math.sqrt(x.var() / x.size + y.var() / y.size))
    res["numba_vs_numpy"] = {"z_win": z(a["winner"] == 0, b["winner"] == 0), "z_total": z(a["total"].astype(float), b["total"].astype(float)),
                             "z_tail_m>5.5": z(a["margin"] > 5.5, b["margin"] > 5.5)}
    res["numba_vs_numpy"]["ok"] = bool(all(abs(v) < 3.5 for v in res["numba_vs_numpy"].values()))
    # 3) Hawkes alpha=0 collapses to Poisson (chi-square), 12 replicates
    pp = []
    mu = np.array([1.4 / 90.0, 1.1 / 90.0])
    for rng in streams[20:]:
        c = se.simulate_hawkes(mu, np.zeros((2, 2)), 0.1, 90.0, 50_000, rng)[:, 0]
        pmf = stats.poisson.pmf(np.arange(12), 1.4)
        pmf[-1] += stats.poisson.sf(11, 1.4)
        pp.append(se.chi_square(np.bincount(np.minimum(c, 11), minlength=12).astype(float), pmf)["p_value"])
    res["hawkes_alpha0_poisson"] = {"fisher_p": fisher_p(pp), "biased": fisher_p(pp) < 0.01}
    # 4) antithetic variates: variance of the tail-probability estimator, 150 batches each
    est = lambda anti, off: np.array([(lambda r: (r["margin"] > 5.5).mean())(tv.simulate(0.66, 0.62, 4000, 0.05, off + i, antithetic=anti)) for i in range(150)])
    va, vp = est(True, 0).var(), est(False, 1000).var()
    res["antithetic_variance_ratio"] = float(va / vp)
    # 5) exact identities
    res["streak_vs_simulation"] = {"exact": se.streak_before_successes(4, 3, 0.55)}
    sim_rng = streams[0]
    t = sim_rng.random((400_000, 40)) < 0.55
    cs = np.cumsum(t, axis=1)
    fails_run = np.zeros_like(cs)
    res["streak_vs_simulation"]["mc"] = float(_mc_streak(sim_rng, 4, 3, 0.55))
    # 6) latency
    res["latency_numba_20k_matches"] = se.latency(lambda: _SIM(0.66, 0.62, 20_000, 0.05, 1), 40)
    res["pass"] = bool(not res["hold_generator"]["biased"] and res["numba_vs_numpy"]["ok"] and not res["hawkes_alpha0_poisson"]["biased"])
    return res


def _mc_streak(rng: np.random.Generator, k: int, r: int, p: float, n: int = 300_000, T: int = 200) -> float:
    """Monte-Carlo check of streak_before_successes via vectorised run-length tracking."""
    x = rng.random((n, T)) < p                       # success flags
    succ = np.cumsum(x, axis=1)
    idx = np.arange(T)[None, :]
    last_succ = np.maximum.accumulate(np.where(x, idx, -1), axis=1)
    run_fail = idx - last_succ                        # current failure run length
    hit_streak = np.where(run_fail >= k, idx, T + 1).min(axis=1)
    reach_r = np.where(succ >= r, idx, T + 1).min(axis=1)
    return float((hit_streak < reach_r).mean())


# ── benchmark: old engine vs v2 on the SAME held-out matches ──────────────────────────
def benchmark() -> Dict[str, object]:
    import pickle
    import tennis_price_backtest as T
    recs = pickle.loads((DATA / "_hier_fit.pkl").read_bytes())
    recs.sort(key=lambda r: r["date"])
    te = recs[int(len(recs) * 0.6):]
    off_old = {"ATP": -1.70, "WTA": -2.15}

    def cover(mh, L, k=1.0):
        n = sum(mh.values())
        return sum(c for m, c in mh.items() if int(round(m * k)) + L > 0) / n

    def ladder(sd, k=1.0):
        ps, ys = [], []
        for r in te:
            m = r["ga"] - r["gb"]
            for L in T.LADDER:
                ps.append(cover(r["mh"][sd], L, k))
                ys.append(1 if m + L > 0 else 0)
        return bm.brier(ps, ys), bm.log_loss(ps, ys)

    def hand(sd, k=1.0):
        H = [r for r in te if r.get("H_ok")]
        y = [1 if r["ga"] - r["gb"] + r["H"] > 0 else 0 for r in H]
        mk = [T._devig(r["oha"], r["ohb"]) for r in H]
        mo = [cover(r["mh"][sd], r["H"], k) for r in H]
        bets = [od * w - 1 for r, p, yy in zip(H, mo, y) for pr, od, w in ((p, r["oha"], yy), (1 - p, r["ohb"], 1 - yy)) if pr * od - 1 >= 0.05]
        return {"brier_model": bm.brier(mo, y), "brier_market": bm.brier(mk, y), "brier_blend": bm.brier([(a + b) / 2 for a, b in zip(mk, mo)], y),
                "edge5_n": len(bets), "edge5_roi_pct": 100 * float(np.mean(bets)) if bets else None}

    def tot(sd, offs):
        def po(r):
            th = r["th"][sd]
            n = sum(th.values())
            mean = sum(t * c for t, c in th.items()) / n + offs[r["tour"]]
            return sum(c for t, c in th.items() if t + offs[r["tour"]] > r["L"]) / n
        ps = [po(r) for r in te]
        y = [1 if r["ga"] + r["gb"] > r["L"] else 0 for r in te]
        mk = [T._devig(r["oov"], r["oun"]) for r in te]
        bias = float(np.mean([sum(t * c for t, c in r["th"][sd].items()) / sum(r["th"][sd].values()) + offs[r["tour"]] - (r["ga"] + r["gb"]) for r in te]))
        return {"brier_model": bm.brier(ps, y), "brier_market": bm.brier(mk, y), "brier_blend": bm.brier([(a + b) / 2 for a, b in zip(mk, ps)], y), "mean_bias_games": bias}

    out = {"n_test": len(te), "ladder_brier_logloss": {"iid_old": ladder(0.0), "iid_k1.26": ladder(0.0, 1.26), "v2_hier": ladder(0.05)},
           "handicap": {"iid_old": hand(0.0), "iid_k1.26": hand(0.0, 1.26), "v2_hier": hand(0.05)},
           "totals": {"iid_old(offset -1.7/-2.15)": tot(0.0, off_old), "v2_hier(offset %.2f/%.2f)" % (TOTALS_OFFSET["ATP"], TOTALS_OFFSET["WTA"]): tot(0.05, TOTALS_OFFSET)}}
    t0 = time.perf_counter()
    _SIM(0.66, 0.62, 400_000, 0.05, 1)
    tn = time.perf_counter() - t0
    t0 = time.perf_counter()
    tgm.simulate_match(0.66, 0.62, 3, n_sims=20_000, seed=1)
    tl = time.perf_counter() - t0
    out["speed_matches_per_sec"] = {"old_python_loop": 20_000 / tl, "v2_numba": 400_000 / tn, "speedup": (400_000 / tn) / (20_000 / tl)}
    return out


# ── scan ───────────────────────────────────────────────────────────────────────────
def scan(board: Optional[list] = None, bankroll: float = 60.0) -> List[dict]:
    board = board or tss.BOARD
    allbets: List[dict] = []
    for m in board:
        S = simulate_match(m["A"], m["B"], m["ml"])
        if S is None:
            continue
        for b in tss.scan(m, S):
            b["thin_data"] = min(S["n_pts"]) < 30
            b.update({f"kelly_{k}": v for k, v in kelly_stake(b["p"], b["model"], b["market"], b["odds"], bankroll).items()})
            allbets.append(b)
    return allbets


def nflwind(week_json: Optional[str] = None) -> None:
    """Forecast wind for the next NFL slate (Open-Meteo, free) vs the validated Under rule."""
    import datetime
    import urllib.parse
    import urllib.request
    j = lambda u: json.load(urllib.request.urlopen(u, timeout=30))
    sb = j("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=50")
    print("kickoff(UTC)      match          roof     total  wind(OpenMeteo) ~recorded | rule: recorded wind>=15mph = Open-Meteo >=13.2mph. In-sample 57.9% (1990-2016) but 2022-25 with FORECAST wind only 50.8% (n=63): WATCH, not a bet")
    for e in sb["events"]:
        c = e["competitions"][0]
        v = c.get("venue", {})
        a = v.get("address", {})
        teams = [x["team"]["abbreviation"] for x in c["competitors"]]
        o = (c.get("odds") or [{}])[0]
        g = j("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=5&country_code=US" % urllib.parse.quote(a.get("city", "")))
        r0 = g["results"][0]
        t = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        w = j("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=wind_speed_10m,wind_gusts_10m&wind_speed_unit=mph&forecast_days=7&timezone=UTC" % (r0["latitude"], r0["longitude"]))
        i = [k for k, x in enumerate(w["hourly"]["time"]) if x[:13] == t.strftime("%Y-%m-%dT%H")]
        ws, gu = (w["hourly"]["wind_speed_10m"][i[0]], w["hourly"]["wind_gusts_10m"][i[0]]) if i else (None, None)
        rec = (2.41 + 0.74 * ws) if ws is not None else None          # data/wind_scale_map.json OLS, R2=0.51
        flag = "  <-- WIND WATCH (forward-test only)" if (not v.get("indoor") and ws is not None and ws >= 13.2) else ""
        print(f"{e['date'][:16]} {'@'.join(teams):<10} {'indoor ' if v.get('indoor') else 'outdoor'} {o.get('overUnder')}  {ws} (gust {gu}) ~{rec:.0f} mph recorded-scale{flag}" if rec is not None else f"{e['date'][:16]} {'@'.join(teams)} no wind")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        print(json.dumps(selftest(), indent=1, default=float))
    elif cmd == "bench":
        print(json.dumps(benchmark(), indent=1, default=float))
    elif cmd == "scan":
        bets = scan()
        json.dump(bets, open(DATA / "_slate_scan_v2.json", "w"), indent=1, default=float)
        print(len(bets), "markets priced; saved data/_slate_scan_v2.json")
    elif cmd == "nflwind":
        nflwind()
