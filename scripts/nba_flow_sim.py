"""
nba_flow_sim.py — quarter-by-quarter Monte Carlo of an NBA game (the "flow of the game"), 400k+ sims per game.

There is NO possession-level play-by-play feed in this repo, so the flow is simulated per quarter:
  quarter margin q_i ~ N(m/4, s_m) with equal correlation rho_q between quarters (rho_q<0 = comebacks / garbage time;
  taken from the halves fit in nba_halftime when available, else 0), s_m chosen so Var(margin) = sigma_m^2;
  quarter total ~ N(T/4, sigma_t/2), independent of the margin (corr(margin,total) ~ -0.01 on 18.5k closing lines).
Outputs per game: P(win incl. OT), P(cover) / P(over) for any line, team totals, margin buckets, halftime lead stats.
A regulation tie (|M|<0.5) goes to OT: home wins it with 0.5 + 0.3*(P(home)-0.5) (assumption).
"""
from __future__ import annotations

import numpy as np

import nba_halftime as nh

N_SIMS = 400_000


def simulate(m: float, T: float, sigma_m: float, sigma_t: float, rho_q: float = 0.0, n: int = N_SIMS, seed: int = 20261020) -> dict:
    rng = np.random.default_rng(seed)
    rho_q = max(min(rho_q, 0.3), -0.3)
    s_m = sigma_m / np.sqrt(4 + 12 * rho_q)
    cov = np.full((4, 4), rho_q * s_m * s_m) + np.eye(4) * (1 - rho_q) * s_m * s_m
    qm = rng.multivariate_normal(np.full(4, m / 4), cov, size=n)
    qt = rng.normal(T / 4, sigma_t / 2, size=(n, 4))
    M, S = qm.sum(1), qt.sum(1)
    h1 = qm[:, :2].sum(1)
    p_home = float((M > 0).mean())
    tie = np.abs(M) < 0.5
    p_ot_home = 0.5 + 0.3 * (p_home - 0.5)
    win_home = (M >= 0.5) | (tie & (rng.random(n) < p_ot_home))
    return {"M": M, "S": S, "H": (S + M) / 2, "A": (S - M) / 2, "h1": h1, "win_home": win_home, "n": n}


def p_cover_home(sim: dict, line: float) -> float:
    return float((sim["M"] + line > 0).mean())


def p_over(sim: dict, line: float) -> float:
    return float((sim["S"] > line).mean())


def p_team_over(sim: dict, side: str, line: float) -> float:
    return float((sim["H" if side == "home" else "A"] > line).mean())


def p_refund(sim: dict, side: str, lead: int = nh.LEAD) -> float:
    """Halftime-refund promo: team leads by `lead`+ at half but does not win."""
    h1 = sim["h1"] if side == "home" else -sim["h1"]
    won = sim["win_home"] if side == "home" else ~sim["win_home"]
    return float(((h1 >= lead - 0.5) & ~won).mean())
