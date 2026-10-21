"""
nba_halftime.py — value of Stake's NBA "halftime refund" promo.

Promo: pre-game single on the Winner (incl. OT) market; if your team leads by 16+ at halftime but does NOT win the
game, the whole stake is refunded (first bet per game, no cash-out; Stake can disqualify promo abuse such as betting
both sides — we price ONE side only).

Bet outcome per unit stake: win -> +(dec-1); lose and no refund -> -1; lose after leading 16+ at half -> 0.
    EV = P(win)*dec - 1 + P(refund),   P(refund) = P(H1 margin >= 16 AND team does not win)

Model: game margin M = H1 + H2, M ~ N(m, sigma^2). H1 gets share `h1_var_share` of the variance (0.5 = independent
increments, the proxy already used in edge_api) with correlation `rho` between halves. DEFAULTS ARE ASSUMPTIONS until
validate_halftime.py fits them on real half-by-half scores (ESPN linescores); the report says which are in use.
Continuity: H1 >= 16 points -> integer margins, so the cut is 15.5. OT: a tied regulation is a coin flip (ignored: tiny).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import norm

DATA = Path(__file__).parent.parent / "data"
PARAMS_PATH = DATA / "nba_halftime_params.json"
DEFAULTS = {"sigma": 13.1, "h1_var_share": 0.5, "rho": 0.0, "fitted": False}
LEAD = 16


def load_params() -> dict:
    if PARAMS_PATH.exists():
        return {**DEFAULTS, **json.loads(PARAMS_PATH.read_text())}
    return dict(DEFAULTS)


def margin_from_pwin(p_win: float, sigma: float = 13.1) -> float:
    """Expected game margin implied by a win probability under M ~ N(m, sigma) (same inversion as sport_math)."""
    return float(sigma * norm.ppf(min(max(p_win, 1e-4), 1 - 1e-4)))


def refund_prob(m: float, params: dict | None = None, lead: int = LEAD) -> float:
    """P(team leads by >= `lead` at halftime AND does not win the game) for a team with expected margin m."""
    p = params or load_params()
    sig, share, rho = p["sigma"], p["h1_var_share"], p["rho"]
    s1, s2 = sig * np.sqrt(share), sig * np.sqrt(1 - share)
    # Var(M) = s1^2 + s2^2 + 2*rho*s1*s2 should stay near sigma^2; renormalise so the FULL-game sd is sigma
    tot = np.sqrt(s1 ** 2 + s2 ** 2 + 2 * rho * s1 * s2)
    s1, s2 = s1 * sig / tot, s2 * sig / tot
    h = np.linspace(lead - 0.5, lead - 0.5 + 8 * s1 + abs(m), 4000)          # H1 grid above the cut
    dens = norm.pdf(h, loc=m / 2, scale=s1)
    mean2 = m / 2 + rho * s2 / s1 * (h - m / 2)
    sd2 = s2 * np.sqrt(1 - rho ** 2)
    lose_given_h = norm.cdf((-h - mean2) / sd2)                                   # H2 <= -H1  (game not won)
    return float(np.trapezoid(dens * lose_given_h, h))


def ev_with_refund(p_win: float, decimal_odds: float, p_refund: float) -> float:
    return p_win * decimal_odds - 1 + p_refund


def fit_params(h1_margin: np.ndarray, h2_margin: np.ndarray) -> dict:
    """Fit half variances/correlation from real half-by-half margins (home perspective)."""
    v1, v2 = float(np.var(h1_margin)), float(np.var(h2_margin))
    rho = float(np.corrcoef(h1_margin, h2_margin)[0, 1])
    # note: np.var includes the spread of true team strengths, so these are UNCONDITIONAL; for the conditional
    # model we remove nothing here and compare model vs empirical refund frequency in validate_halftime.py
    sigma = float(np.sqrt(v1 + v2 + 2 * rho * np.sqrt(v1 * v2)))
    return {"sigma": sigma, "h1_var_share": v1 / (v1 + v2), "rho": rho, "fitted": True, "n": int(len(h1_margin))}
