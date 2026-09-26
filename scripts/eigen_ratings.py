"""
Eigenvector team ratings (Keener's method) — Caveman Locks.

A team's rating is the dominant eigenvector of a "who dominated whom, and by
how much" matrix built from real results — the same family of technique as
Google PageRank (eigenvector centrality) and the Colley/Keener methods used
in real college-football and March Madness ranking systems. The self-
consistency is the point: beating a strong team lifts your rating more than
beating a weak one, and that "strength" is itself defined by the same
eigenvector, solved jointly rather than hand-assigned.

Reference: J.P. Keener, "The Perron-Frobenius theorem and the ranking of
football teams", SIAM Review 35(1), 1993.

Construction:
    1. For each ordered pair (i, j) that has met, compute a Laplace-smoothed
       goal-share s_ij = (goals_for + 1) / (goals_for + goals_against + 2)
       in (0, 1) — how convincingly i outscored j across their meetings.
    2. Apply Keener's concavity transform h(s) = 1/2 + sign(s-1/2)*sqrt(|2s-1|)/2
       — this DAMPENS blowouts (an 8-0 counts barely more than a 3-0) so one
       lopsided result can't dominate the rating the way raw goal difference
       would.
    3. Build A[i][j] = decayed-weighted average of h_ij, plus a small uniform
       floor epsilon so every entry is strictly positive — this is what makes
       Perron-Frobenius apply: a strictly positive matrix has a real, simple,
       positive dominant eigenvalue with a unique positive eigenvector.
    4. Solve for that eigenvector via power iteration: v_{k+1} = A v_k / ||A v_k||,
       which provably converges to the Perron eigenvector for a positive matrix.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np

EPSILON_FLOOR = 0.02   # strictly-positive floor on A — guarantees Perron-Frobenius applies
POWER_ITER_MAX = 500
POWER_ITER_TOL = 1e-10


@dataclass(frozen=True)
class EigenRatings:
    ratings: dict[str, float]  # team -> normalized strength (sums to 1 across teams)
    teams: list[str]
    n_matches: int


def _keener_transform(s: float) -> float:
    return 0.5 + math.copysign(math.sqrt(abs(2 * s - 1)), s - 0.5) / 2


def _decay_weight(match_date: date, as_of: date, halflife_days: float = 730.0) -> float:
    days = max(0, (as_of - match_date).days)
    return float(0.5 ** (days / halflife_days))


def fit(
    rows: list[dict],
    as_of: Optional[date] = None,
    lookback_years: int = 6,
    epsilon: float = EPSILON_FLOOR,
) -> EigenRatings:
    as_of = as_of or date.today()
    cutoff = date(as_of.year - lookback_years, as_of.month, as_of.day)

    goals_for: dict[tuple[str, str], float] = {}
    goals_against: dict[tuple[str, str], float] = {}
    weight_sum: dict[tuple[str, str], float] = {}
    teams_seen: set[str] = set()
    n_matches = 0

    for r in rows:
        hs, aws = r.get("home_score"), r.get("away_score")
        if hs in (None, "", "NA") or aws in (None, "", "NA"):
            continue
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if d > as_of or d < cutoff:
            continue
        h, a = r["home_team"], r["away_team"]
        hg, ag = float(hs), float(aws)
        w = _decay_weight(d, as_of)
        teams_seen.add(h)
        teams_seen.add(a)
        n_matches += 1

        for key, gf, ga in ((( h, a), hg, ag), ((a, h), ag, hg)):
            goals_for[key] = goals_for.get(key, 0.0) + w * gf
            goals_against[key] = goals_against.get(key, 0.0) + w * ga
            weight_sum[key] = weight_sum.get(key, 0.0) + w

    teams = sorted(teams_seen)
    if not teams:
        return EigenRatings(ratings={}, teams=[], n_matches=0)
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)

    A = np.full((T, T), epsilon)
    for (i_team, j_team), gf in goals_for.items():
        ga = goals_against[(i_team, j_team)]
        s = (gf + 1) / (gf + ga + 2)
        h = _keener_transform(s)
        A[idx[i_team], idx[j_team]] += h

    # Power iteration for the dominant (Perron) eigenvector — guaranteed real,
    # positive, and unique because A is strictly positive by construction.
    v = np.full(T, 1.0 / T)
    for _ in range(POWER_ITER_MAX):
        v_next = A @ v
        v_next = v_next / v_next.sum()
        if np.max(np.abs(v_next - v)) < POWER_ITER_TOL:
            v = v_next
            break
        v = v_next

    return EigenRatings(
        ratings={t: round(float(v[idx[t]]), 6) for t in teams},
        teams=teams,
        n_matches=n_matches,
    )
