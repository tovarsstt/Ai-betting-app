"""
Generic Poisson scoring model — Caveman Locks.

Sport-agnostic engine for any two-side "count" market (goals, runs, corners,
cards...). Given two Poisson scoring rates (lambda_home, lambda_away) it
builds the joint score matrix, the most likely exact scorelines (correct
score), and runs a Monte Carlo match simulator for probabilities that the
closed-form matrix can't give directly — joint/correlated same-game markets
(e.g. P(home win AND BTTS yes) together, not multiplied as if independent).

soccer_markets.py is the soccer-specific consumer of this engine (adds the
Dixon-Coles draw correction and derives soccer markets). This module has no
sport knowledge and should stay that way — best suited to low/moderate-count
events (soccer goals, hockey goals, corners, cards), not high-scoring totals
like a full NBA/NFL score (those are already modelled with a normal
distribution around the spread in math_engine.py / edge_api.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

MAX_COUNT = 10


# ── Closed-form score matrix ───────────────────────────────────────────────
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def dixon_coles_tau(hg: int, ag: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles low-score correlation adjustment; 1.0 outside the 4 cells it touches."""
    if hg == 0 and ag == 0:
        return 1.0 - lh * la * rho
    if hg == 0 and ag == 1:
        return 1.0 + lh * rho
    if hg == 1 and ag == 0:
        return 1.0 + la * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(
    lh: float, la: float, max_count: int = MAX_COUNT, rho: float = 0.0
) -> list[list[float]]:
    """P(home=i, away=j) for i,j in [0, max_count], renormalized to sum to 1."""
    matrix = [
        [
            poisson_pmf(i, lh) * poisson_pmf(j, la) * dixon_coles_tau(i, j, lh, la, rho)
            for j in range(max_count + 1)
        ]
        for i in range(max_count + 1)
    ]
    total = sum(cell for row in matrix for cell in row)
    if total <= 0:
        return matrix
    return [[cell / total for cell in row] for row in matrix]


def win_draw_loss(matrix: list[list[float]]) -> tuple[float, float, float]:
    """Home win / draw (tie) / away win probabilities from the matrix."""
    home = draw = away = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def correct_score_probs(matrix: list[list[float]], top_n: int = 10) -> list[dict]:
    """
    Most likely exact scorelines, sorted by probability. Includes fair (vig-free)
    decimal odds for each — the "correct score" market.
    """
    cells = [
        {"home": i, "away": j, "prob": p}
        for i, row in enumerate(matrix)
        for j, p in enumerate(row)
        if p > 0
    ]
    cells.sort(key=lambda c: c["prob"], reverse=True)
    out = []
    for c in cells[:top_n]:
        dec = round(1.0 / c["prob"], 2) if c["prob"] > 0 else None
        out.append({
            "score": f"{c['home']}-{c['away']}",
            "home": c["home"],
            "away": c["away"],
            "prob": round(c["prob"], 4),
            "fair_decimal_odds": dec,
        })
    return out


# ── Monte Carlo match simulator ────────────────────────────────────────────
@dataclass(frozen=True)
class SimResult:
    home_goals: np.ndarray
    away_goals: np.ndarray
    n_sims: int


def simulate_matches(
    matrix: list[list[float]], n_sims: int = 120_000, seed: Optional[int] = None
) -> SimResult:
    """
    Draw n_sims scorelines from the (Dixon-Coles adjusted) joint distribution
    in `matrix` — a true Monte Carlo sample from the same model the closed-form
    markets are priced off, not independent Poisson draws. This is what lets
    correlated same-game markets (hit_rate / combo_hit_rate below) be evaluated
    correctly instead of naively multiplying marginal probabilities.
    """
    rng = np.random.default_rng(seed)
    flat = np.array([p for row in matrix for p in row])
    flat = flat / flat.sum()
    n = len(matrix)
    idx = rng.choice(len(flat), size=n_sims, p=flat)
    home_goals = idx // n
    away_goals = idx % n
    return SimResult(home_goals=home_goals, away_goals=away_goals, n_sims=n_sims)


def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — better than normal approx at small hit counts."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def hit_rate(sim: SimResult, predicate: Callable[[int, int], bool]) -> dict:
    """Simulated probability + 95% CI that a (home_goals, away_goals) predicate holds."""
    hits = int(sum(
        1 for h, a in zip(sim.home_goals, sim.away_goals) if predicate(int(h), int(a))
    ))
    prob = hits / sim.n_sims if sim.n_sims else 0.0
    lo, hi = _wilson_ci(hits, sim.n_sims)
    return {"prob": round(prob, 4), "ci_95": [lo, hi], "hits": hits, "n_sims": sim.n_sims}


def combo_hit_rate(sim: SimResult, predicates: list[Callable[[int, int], bool]]) -> dict:
    """
    Joint (AND) probability that ALL predicates hold on the same simulated match —
    the real value-add over the closed-form matrix: correlated same-game-parlay
    legs (e.g. home win AND BTTS yes) instead of naively multiplying marginals.
    """
    return hit_rate(sim, lambda h, a: all(pred(h, a) for pred in predicates))


# ── Common market predicates (home_goals, away_goals) -> bool ─────────────────
def home_win(h: int, a: int) -> bool:
    return h > a


def draw(h: int, a: int) -> bool:
    return h == a


def away_win(h: int, a: int) -> bool:
    return h < a


def btts_yes(h: int, a: int) -> bool:
    return h >= 1 and a >= 1


def over(line: float) -> Callable[[int, int], bool]:
    return lambda h, a: (h + a) > line


def under(line: float) -> Callable[[int, int], bool]:
    return lambda h, a: (h + a) < line


def exact_score(home: int, away: int) -> Callable[[int, int], bool]:
    return lambda h, a: h == home and a == away
