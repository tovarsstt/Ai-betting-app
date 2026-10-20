#!/usr/bin/env python3
"""
stochastic_engine.py — heuristic-injection stochastic simulator.

Layers (all calculation routines are vectorised numpy — no per-element Python loops; the
only `while` is the Hawkes generation recursion, whose body is itself array-wide, and
stays <= ~12 passes because the branching ratio is < 1):

  1. HEURISTIC INJECTION (Strategy pattern)
       Heuristic.modifiers(payload) -> Modifiers   one strategy per heuristic family:
       WeatherHeuristic   sigmoid wind / rain penalty, altitude+temperature fatigue
       StyleHeuristic     offence x defence collision tensor (replaces flat averages)
       PressureHeuristic  birthday / goals / press index -> multiplicative sd (tail) factor
       CompositeHeuristic combines strategies in LOGIT space (so effects stack without
                          ever leaving (0,1)).
     CoefficientStore: every beta is looked up in data/heuristic_coefficients.json and
     passed through EMPIRICAL-BAYES SHRINKAGE  beta_eff = beta * n/(n+n0).  An
     UNCALIBRATED coefficient is 0 — an invented effect size is a fabricated edge
     (global rule 13), so the engine ships with the mechanism and only the effects that
     real data has justified.
  2. CORE (Template Method: SimulationEngine.run is the fixed skeleton)
       tennis point process   tennis_vec (Bernoulli points -> exact hold -> set -> match)
                              with the hierarchical day-to-day serve-rate sd
       Hawkes                 self/cross-exciting scoring bursts as a Poisson cluster process
       NegativeBinomial       P(k fails before r successes) and the exact probability of a
                              k-in-a-row failure streak before r successes (absorbing chain)
       GPD tail risk          peaks-over-threshold fit -> VaR / CVaR / drawdown of a bankroll
  3. VARIANCE REDUCTION + VALIDATION
       antithetic uniforms (U, 1-U); latency P50/P95/P99 per batch; chi-square goodness of
       fit of the generators against closed forms (a p < .05 means the generator is BIASED).

Run: python3 scripts/stochastic_engine.py [payload.json]
"""
from __future__ import annotations

import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import tennis_vec as tv  # noqa: E402

try:                                   # optional accelerator; numpy path is the reference
    from numba import njit             # type: ignore
except Exception:                      # pragma: no cover
    njit = None

COEF_PATH = Path(__file__).parent.parent / "data" / "heuristic_coefficients.json"
Array = np.ndarray


# ════════════════════════════════════════════════════════════════════════════════════
# payload + coefficients
# ════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Entity:
    id: str = "?"
    style: str = "neutral"
    base_lambda_offense: float = 1.3
    base_lambda_defense: float = 1.3
    base_serve_p: Optional[float] = None       # serve-POINT win probability
    base_hold_p: Optional[float] = None        # game HOLD probability (inverted to serve p)
    personal_goals_pending: int = 0


@dataclass(frozen=True)
class Payload:
    sim_id: str
    wind_kmh: float
    rain_mm: float
    temp_c: float
    altitude_m: float
    surface: str
    is_special_day: bool
    is_birthday: bool
    press_index: float
    a: Entity
    b: Entity

    @staticmethod
    def parse(d: Dict[str, Any]) -> "Payload":
        c = d.get("contextual_heuristics", {})
        cl, ca = c.get("clima", {}), c.get("calendario", {})
        t = d.get("tactical_heuristics", {})

        def ent(k: str) -> Entity:
            e = t.get(k, {})
            return Entity(id=e.get("id", k), style=e.get("estilo_playbook", "neutral"),
                          base_lambda_offense=float(e.get("base_lambda_offense", 1.3)),
                          base_lambda_defense=float(e.get("base_lambda_defense", 1.3)),
                          base_serve_p=e.get("base_bernoulli_serve_p"),
                          base_hold_p=e.get("base_bernoulli_hold_p"),
                          personal_goals_pending=int(e.get("personal_goals_pending", 0)))

        return Payload(sim_id=d.get("metadata", {}).get("simulation_id", "SIM"),
                       wind_kmh=float(cl.get("viento_kmh", 0.0)), rain_mm=float(cl.get("lluvia_mm", 0.0)),
                       temp_c=float(cl.get("temperatura_c", 20.0)), altitude_m=float(cl.get("altitud_m", 0.0)),
                       surface=str(cl.get("tipo_superficie", "hard")),
                       is_special_day=bool(ca.get("is_special_day", False)),
                       is_birthday=bool(ca.get("is_birthday_effect", False)),
                       press_index=float(ca.get("press_index_0_to_1", 0.0)), a=ent("entidad_A"), b=ent("entidad_B"))


class CoefficientStore:
    """name -> {value, n, n0, status}. Empirical-Bayes shrinkage; uncalibrated => 0."""

    def __init__(self, path: Path = COEF_PATH) -> None:
        self.raw: Dict[str, Dict[str, Any]] = json.loads(path.read_text()) if path.exists() else {}

    def beta(self, name: str) -> float:
        r = self.raw.get(name)
        if not r or r.get("status") != "calibrated":
            return 0.0
        n, n0 = float(r.get("n", 0)), float(r.get("n0", 50))
        return float(r["value"]) * n / (n + n0)

    def status(self, name: str) -> str:
        return self.raw.get(name, {}).get("status", "uncalibrated")


# ════════════════════════════════════════════════════════════════════════════════════
# heuristics (Strategy)
# ════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Modifiers:
    logit_a: float = 0.0          # shift on A's serve-point logit
    logit_b: float = 0.0
    sd_mult: float = 1.0          # multiplies the day-to-day serve-rate sd (tails)
    lambda_mult_a: float = 1.0    # scoring-rate multipliers for the goals engine
    lambda_mult_b: float = 1.0
    fatigue_rate: float = 0.0     # fraction of serve-point rate lost per extra set

    def combine(self, o: "Modifiers") -> "Modifiers":
        return Modifiers(self.logit_a + o.logit_a, self.logit_b + o.logit_b, self.sd_mult * o.sd_mult,
                         self.lambda_mult_a * o.lambda_mult_a, self.lambda_mult_b * o.lambda_mult_b,
                         self.fatigue_rate + o.fatigue_rate)


def sigmoid(x: Array | float) -> Array | float:
    return 1.0 / (1.0 + np.exp(-x))


class Heuristic(ABC):
    def __init__(self, coefs: CoefficientStore) -> None:
        self.coefs = coefs

    @abstractmethod
    def modifiers(self, p: Payload) -> Modifiers: ...


class WeatherHeuristic(Heuristic):
    """beta_wind = sigmoid(k (wind - thr)): ~0 below the critical threshold, saturating
    above it. Rain uses a steeper, lower-threshold sigmoid. Both hurt the SERVER (toss and
    serve accuracy) and widen the day-to-day spread; altitude/temperature set fatigue."""
    WIND_K, WIND_THR = 0.35, 25.0      # km/h  (shape constants; the EFFECT sizes come from the store)
    RAIN_K, RAIN_THR = 1.2, 2.0        # mm

    def modifiers(self, p: Payload) -> Modifiers:
        bw = float(sigmoid(self.WIND_K * (p.wind_kmh - self.WIND_THR)))
        br = float(sigmoid(self.RAIN_K * (p.rain_mm - self.RAIN_THR)))
        shift = -(self.coefs.beta("wind_serve_logit") * bw + self.coefs.beta("rain_serve_logit") * br)
        sd = 1.0 + self.coefs.beta("wind_sd") * bw + self.coefs.beta("rain_sd") * br
        heat = float(sigmoid(0.4 * (p.temp_c - 30.0)))
        fat = self.coefs.beta("heat_fatigue") * heat + self.coefs.beta("altitude_fatigue") * (p.altitude_m / 1000.0)
        lam = float(np.exp(-(self.coefs.beta("wind_scoring") * bw)))
        return Modifiers(shift, shift, sd, lam, lam, fat)


class StyleHeuristic(Heuristic):
    """Offence-vs-defence collision TENSOR: C[i, j] multiplies the attacker's scoring rate
    (style i) against defender style j, instead of a flat average. Identity unless the
    store supplies calibrated off-diagonals (key 'style_<off>__<def>')."""
    STYLES = ("neutral", "presion_alta", "contraataque_bloque_bajo", "posesion", "saque_volea", "fondo")

    def tensor(self) -> Array:
        k = len(self.STYLES)
        c = np.ones((k, k))
        for i, off in enumerate(self.STYLES):
            for j, de in enumerate(self.STYLES):
                c[i, j] = np.exp(self.coefs.beta(f"style_{off}__{de}"))
        return c

    def modifiers(self, p: Payload) -> Modifiers:
        idx = {s: i for i, s in enumerate(self.STYLES)}
        ia, ib = idx.get(p.a.style, 0), idx.get(p.b.style, 0)
        c = self.tensor()
        return Modifiers(lambda_mult_a=float(c[ia, ib]), lambda_mult_b=float(c[ib, ia]))


class PressureHeuristic(Heuristic):
    """Birthday / special day / pending personal goals / press index widen or narrow the
    tails through the sd multiplier (a variance effect, NOT a mean shift)."""

    def modifiers(self, p: Payload) -> Modifiers:
        z = (self.coefs.beta("press_sd") * p.press_index + self.coefs.beta("birthday_sd") * float(p.is_birthday)
             + self.coefs.beta("special_day_sd") * float(p.is_special_day)
             + self.coefs.beta("personal_goal_sd") * min(p.a.personal_goals_pending, 3))
        return Modifiers(sd_mult=float(np.exp(z)))


class CompositeHeuristic(Heuristic):
    def __init__(self, parts: List[Heuristic], coefs: CoefficientStore) -> None:
        super().__init__(coefs)
        self.parts = parts

    def modifiers(self, p: Payload) -> Modifiers:
        m = Modifiers()
        for h in self.parts:                       # <=3 strategies; trivially cheap, not a hot loop
            m = m.combine(h.modifiers(p))
        return m


# ════════════════════════════════════════════════════════════════════════════════════
# mathematical core
# ════════════════════════════════════════════════════════════════════════════════════
def antithetic_uniform(rng: np.random.Generator, shape: Tuple[int, ...]) -> Array:
    """(U, 1-U) pairs: negatively correlated draws halve the variance of monotone estimators."""
    half = rng.random((shape[0] // 2 + shape[0] % 2,) + shape[1:])
    return np.concatenate([half, 1.0 - half])[: shape[0]]


def hold_to_serve_point(h: float) -> float:
    """Invert game-hold probability to the serve-point rate (hold is monotone in p)."""
    grid = np.linspace(0.30, 0.90, 6001)
    return float(np.interp(h, tv.hold(grid), grid))


def simulate_hawkes(mu: Array, alpha: Array, beta: float, T: float, n_paths: int,
                    rng: np.random.Generator) -> Array:
    """Multivariate Hawkes via its Poisson-cluster representation. mu: (d,) baseline rates
    per unit time, alpha: (d,d) excitation (type j event raises type i intensity by
    alpha[i,j]*exp(-beta*dt)). Branching matrix N = alpha/beta (spectral radius must be <1).
    Returns counts (n_paths, d) over [0, T]."""
    d = mu.shape[0]
    N = alpha / beta
    if np.max(np.abs(np.linalg.eigvals(N))) >= 1.0:
        raise ValueError("Hawkes branching ratio >= 1: process explodes")
    n_imm = rng.poisson(mu[None, :] * T, (n_paths, d))                 # immigrants per path/type
    path = np.repeat(np.repeat(np.arange(n_paths), d), n_imm.ravel())
    typ = np.repeat(np.tile(np.arange(d), n_paths), n_imm.ravel())
    t = rng.uniform(0.0, T, path.size)
    all_path, all_typ = [path], [typ]
    pa, pt, pty = path, t, typ
    while pa.size:                                                     # one array-wide pass per generation
        kids = rng.poisson(N[:, pty].T)                                # (n_parents, d) children per type
        rep = kids.ravel()
        cpath = np.repeat(np.repeat(pa, d), rep)
        ctype = np.repeat(np.tile(np.arange(d), pa.size), rep)
        ctime = np.repeat(np.repeat(pt, d), rep) + rng.exponential(1.0 / beta, rep.sum())
        keep = ctime < T
        pa, pt, pty = cpath[keep], ctime[keep], ctype[keep]
        all_path.append(pa)
        all_typ.append(pty)
    ap, aty = np.concatenate(all_path), np.concatenate(all_typ)
    return np.bincount(ap * d + aty, minlength=n_paths * d).reshape(n_paths, d)


def nbinom_failures_before_successes(k: Array | int, r: int, p_success: float) -> Array:
    """P(exactly k failures before the r-th success) — scipy nbinom is exactly this."""
    return stats.nbinom.pmf(k, r, p_success)


def streak_before_successes(k: int, r: int, p_success: float) -> float:
    """Exact P(a run of k consecutive failures occurs BEFORE the r-th success), by solving
    the absorbing Markov chain (states: (successes so far, current fail run)) in closed form
    with one linear solve — no simulation, no loops."""
    S = r * k                                             # transient states idx = s*k + run
    s_idx, run_idx = np.divmod(np.arange(S), k)
    Q = np.zeros((S, S))
    q = 1.0 - p_success
    succ_next = np.where(s_idx + 1 < r, (s_idx + 1) * k, -1)          # success -> (s+1, 0)
    ok = succ_next >= 0
    Q[np.arange(S)[ok], succ_next[ok]] = p_success
    fail_next = np.where(run_idx + 1 < k, s_idx * k + run_idx + 1, -1)  # failure -> (s, run+1)
    okf = fail_next >= 0
    Q[np.arange(S)[okf], fail_next[okf]] = q
    absorb_streak = np.where(run_idx + 1 == k, q, 0.0)                # failure completing the streak
    return float(np.linalg.solve(np.eye(S) - Q, absorb_streak)[0])


def gpd_tail_risk(losses: Array, tail_frac: float = 0.10, q: Tuple[float, float] = (0.95, 0.99)) -> Dict[str, float]:
    """Peaks-over-threshold: fit a Generalised Pareto to the worst `tail_frac` of losses and
    return VaR/CVaR (expected shortfall) at the given levels, next to the empirical values."""
    n = losses.size
    u = float(np.quantile(losses, 1 - tail_frac))
    exc = losses[losses > u] - u
    xi, _, sigma = stats.genpareto.fit(exc, floc=0.0)
    out: Dict[str, float] = {"threshold": u, "xi": float(xi), "sigma": float(sigma), "n_exceed": int(exc.size)}
    for qq in q:
        p_exc = (n / exc.size) * (1 - qq)
        var = u + (sigma / xi) * (p_exc ** (-xi) - 1) if abs(xi) > 1e-9 else u - sigma * np.log(p_exc)
        es = var / (1 - xi) + (sigma - xi * u) / (1 - xi) if xi < 1 else float("inf")
        out[f"VaR{int(qq * 100)}"] = float(var)
        out[f"CVaR{int(qq * 100)}"] = float(es)
        out[f"emp_VaR{int(qq * 100)}"] = float(np.quantile(losses, qq))
        out[f"emp_CVaR{int(qq * 100)}"] = float(losses[losses >= np.quantile(losses, qq)].mean())
    return out


def bankroll_drawdowns(p: float, odds: float, stake_frac: float, n_bets: int, n_paths: int,
                       rng: np.random.Generator) -> Array:
    """Max drawdown (fraction of peak) of a flat-fraction bankroll over n_bets, per path."""
    u = antithetic_uniform(rng, (n_paths, n_bets))
    wins = u < p
    step = np.where(wins, np.log1p(stake_frac * (odds - 1.0)), np.log1p(-stake_frac))
    log_eq = np.cumsum(step, axis=1)
    peak = np.maximum.accumulate(np.maximum(log_eq, 0.0), axis=1)
    return 1.0 - np.exp((log_eq - peak).min(axis=1))


# ════════════════════════════════════════════════════════════════════════════════════
# validation + profiling
# ════════════════════════════════════════════════════════════════════════════════════
def chi_square(observed: Array, expected_p: Array, min_expected: float = 5.0) -> Dict[str, Any]:
    n = observed.sum()
    exp = expected_p * n
    ok = exp >= min_expected                                  # pool the sparse tail
    obs = np.append(observed[ok], observed[~ok].sum())
    ex = np.append(exp[ok], exp[~ok].sum())
    m = ex > 0
    stat = float(((obs[m] - ex[m]) ** 2 / ex[m]).sum())
    dof = int(m.sum() - 1)
    pv = float(stats.chi2.sf(stat, dof))
    return {"chi2": stat, "dof": dof, "p_value": pv, "biased": pv < 0.05}


def latency(fn, batches: int = 40) -> Dict[str, float]:
    ts = np.array([(lambda t0: (fn(), time.perf_counter() - t0)[1])(time.perf_counter()) for _ in range(batches)]) * 1e3
    return {"p50_ms": float(np.percentile(ts, 50)), "p95_ms": float(np.percentile(ts, 95)),
            "p99_ms": float(np.percentile(ts, 99)), "batches": batches}


# ════════════════════════════════════════════════════════════════════════════════════
# engine (Template Method)
# ════════════════════════════════════════════════════════════════════════════════════
@dataclass
class EngineResult:
    payload_id: str
    modifiers: Modifiers
    calibration_status: Dict[str, str]
    tennis: Dict[str, float] = field(default_factory=dict)
    goals: Dict[str, float] = field(default_factory=dict)
    streaks: Dict[str, float] = field(default_factory=dict)
    tail_risk: Dict[str, float] = field(default_factory=dict)
    validation: Dict[str, Any] = field(default_factory=dict)
    profiling: Dict[str, Any] = field(default_factory=dict)


class SimulationEngine:
    def __init__(self, heuristic: Optional[Heuristic] = None, coefs: Optional[CoefficientStore] = None,
                 seed: int = 12345) -> None:
        self.coefs = coefs or CoefficientStore()
        self.heuristic = heuristic or CompositeHeuristic(
            [WeatherHeuristic(self.coefs), StyleHeuristic(self.coefs), PressureHeuristic(self.coefs)], self.coefs)
        self.rng = np.random.default_rng(seed)

    # template method: the fixed order of steps
    def run(self, payload: Payload, n: int = 100_000) -> EngineResult:
        mods = self.heuristic.modifiers(payload)
        res = EngineResult(payload.sim_id, mods, {k: self.coefs.status(k) for k in self.coefs.raw})
        res.tennis = self._tennis(payload, mods, n)
        res.goals = self._goals(payload, mods, n)
        res.streaks = self._streaks()
        res.tail_risk = self._tail(res.tennis.get("p_win_a", 0.5))
        res.validation = self._validate(payload, mods)
        res.profiling = self._profile(payload, mods)
        return res

    def _serve_rates(self, p: Payload, m: Modifiers) -> Tuple[float, float]:
        def base(e: Entity) -> float:
            if e.base_serve_p is not None:
                return float(e.base_serve_p)
            if e.base_hold_p is not None:
                return hold_to_serve_point(float(e.base_hold_p))
            return 0.63
        lg = lambda x: np.log(x / (1 - x))
        return (float(sigmoid(lg(base(p.a)) + m.logit_a)), float(sigmoid(lg(base(p.b)) + m.logit_b)))

    def _tennis(self, p: Payload, m: Modifiers, n: int) -> Dict[str, float]:
        pa, pb = self._serve_rates(p, m)
        sd = 0.04 * m.sd_mult                                     # fitted day-to-day serve-rate sd * heuristic factor
        r = tv.simulate(pa, pb, n, sd=sd, seed=int(self.rng.integers(1 << 30)))
        return {"serve_a": pa, "serve_b": pb, "sd": sd, "p_win_a": float((r["winner"] == 0).mean()),
                "exp_total_games": float(r["total"].mean()), "p_a_straight_sets": float(((r["sets"][:, 0] == 2) & (r["sets"][:, 1] == 0)).mean()),
                "p_margin_a_gt_5.5": float((r["margin"] > 5.5).mean()), "p_margin_b_gt_5.5": float((r["margin"] < -5.5).mean())}

    def _goals(self, p: Payload, m: Modifiers, n: int) -> Dict[str, float]:
        T = 90.0
        mu = np.array([p.a.base_lambda_offense * p.b.base_lambda_defense / 1.3 * m.lambda_mult_a,
                       p.b.base_lambda_offense * p.a.base_lambda_defense / 1.3 * m.lambda_mult_b]) / T
        alpha = np.array([[0.05, 0.01], [0.01, 0.05]])           # shapes only; set to 0 for plain Poisson
        c = simulate_hawkes(mu, alpha, beta=1 / 10.0, T=T, n_paths=n, rng=self.rng)
        d = c[:, 0] - c[:, 1]
        return {"mean_goals_a": float(c[:, 0].mean()), "mean_goals_b": float(c[:, 1].mean()),
                "p_a_win": float((d > 0).mean()), "p_draw": float((d == 0).mean()), "p_b_win": float((d < 0).mean()),
                "p_over_2.5": float((c.sum(1) > 2.5).mean()), "var_over_mean_total": float(c.sum(1).var() / c.sum(1).mean())}

    @staticmethod
    def _streaks() -> Dict[str, float]:
        return {"P(5 fails in a row before 3 wins | p=.55)": streak_before_successes(5, 3, 0.55),
                "P(exactly 4 fails before 3rd win | p=.55)": float(nbinom_failures_before_successes(4, 3, 0.55))}

    def _tail(self, p_win: float) -> Dict[str, float]:
        dd = bankroll_drawdowns(max(0.05, min(0.95, p_win)), 1.0 / max(p_win, 0.05) * 0.96, 0.05, 200, 20_000, self.rng)
        return gpd_tail_risk(dd)

    def _validate(self, p: Payload, m: Modifiers) -> Dict[str, Any]:
        # (1) the vectorised game-hold generator vs its closed form
        ph = 0.62
        games = 400_000
        won = (self.rng.random(games) < tv.hold(np.array(ph))).sum()
        hold_test = chi_square(np.array([won, games - won]), np.array([float(tv.hold(np.array(ph))), 1 - float(tv.hold(np.array(ph)))]))
        # (2) alpha=0 Hawkes must collapse to Poisson counts
        mu = np.array([1.4 / 90.0, 1.1 / 90.0])
        c = simulate_hawkes(mu, np.zeros((2, 2)), 0.1, 90.0, 60_000, self.rng)[:, 0]
        k = np.arange(0, 12)
        pmf = stats.poisson.pmf(k, 1.4)
        obs = np.bincount(np.minimum(c, 11), minlength=12).astype(float)
        pmf[-1] += stats.poisson.sf(11, 1.4)
        hawkes_test = chi_square(obs, pmf)
        # (3) Hawkes mean vs theory  E[N] = (I - A/b)^-1 mu T
        A = np.array([[0.05, 0.01], [0.01, 0.05]])
        theory = np.linalg.solve(np.eye(2) - A / 0.1, mu * 90.0)
        sim = simulate_hawkes(mu, A, 0.1, 90.0, 60_000, self.rng).mean(0)
        return {"hold_generator_chi2": hold_test, "hawkes_alpha0_vs_poisson_chi2": hawkes_test,
                "hawkes_mean_sim": sim.tolist(), "hawkes_mean_theory": theory.tolist(),
                "any_biased": bool(hold_test["biased"] or hawkes_test["biased"])}

    def _profile(self, p: Payload, m: Modifiers) -> Dict[str, Any]:
        pa, pb = self._serve_rates(p, m)
        return {"tennis_20k_matches": latency(lambda: tv.simulate(pa, pb, 20_000, 0.04, 1), 25),
                "hawkes_20k_paths": latency(lambda: simulate_hawkes(np.array([.015, .012]), np.array([[.05, .01], [.01, .05]]), .1, 90.0, 20_000, self.rng), 25)}


DEMO = {"metadata": {"simulation_id": "STOC_HAWKES_992", "timestamp": "2026-10-07T04:12:00Z"},
        "contextual_heuristics": {"clima": {"viento_kmh": 28.5, "lluvia_mm": 4.0, "temperatura_c": 14.0, "tipo_superficie": "arcilla"},
                                  "calendario": {"is_special_day": True, "is_birthday_effect": True, "press_index_0_to_1": 0.85}},
        "tactical_heuristics": {"entidad_A": {"id": "J_TOVAR_01", "estilo_playbook": "presion_alta", "base_lambda_offense": 2.4,
                                              "base_bernoulli_serve_p": 0.68, "personal_goals_pending": 1},
                                "entidad_B": {"id": "RIVAL_TEAM_X", "estilo_playbook": "contraataque_bloque_bajo",
                                              "base_lambda_defense": 1.1, "base_bernoulli_hold_p": 0.72, "personal_goals_pending": 0}}}

if __name__ == "__main__":
    pl = Payload.parse(json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else DEMO)
    out = SimulationEngine().run(pl)
    print(json.dumps(out, default=lambda o: o.__dict__, indent=1))
