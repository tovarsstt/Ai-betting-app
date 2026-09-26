"""
Multivariate Poisson regression for national-team goal rates — Caveman Locks.

This is the statistically correct multivariate model for GOAL COUNTS: goals
are non-negative integers, not a continuous quantity, so ordinary least-
squares (linear regression) is the wrong tool — it can predict negative
goals and mis-weights variance (Poisson variance = mean, OLS assumes constant
variance). The right tool is a Poisson GLM (log link), fit here by maximum
likelihood over EVERY team's attack/defense parameter jointly (all ~200+
national teams solved simultaneously from the same match set — that joint,
many-parameter fit is what makes this "multivariate").

Model, per match (home h, away a):
    log(lambda_home) = mu + home_adv * is_not_neutral + attack[h] - defense[a]
    log(lambda_away) = mu +                            attack[a] - defense[h]

Fit by ridge-penalized MLE (Poisson negative log-likelihood + L2 shrinkage on
attack/defense). Ridge does two jobs here, not one: (1) it resolves the
classic identifiability problem in attack/defense models (raw MLE is only
identified up to an additive constant — shifting every attack up and every
defense up by the same amount leaves all lambdas unchanged; the ridge
penalty breaks that degeneracy by preferring the smallest-magnitude
solution), and (2) it shrinks teams with few matches (weak footballing
nations that rarely play) toward the average instead of producing wild,
overfit estimates from a handful of games.

Time-decay weighting (exp(-days_since / HALFLIFE_DAYS)) favors recent form
over a hard lookback cutoff — a team's 2019 squad says less about 2026 than
its 2025 squad, but old matches aren't thrown away, just down-weighted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np
from scipy.optimize import minimize

HALFLIFE_DAYS = 730.0   # 2 years — recent form weighted ~2x a 2-year-old result
RIDGE_ALPHA = 0.03      # L2 shrinkage on attack/defense; breaks identifiability + tames sparse teams
LOOKBACK_YEARS = 6      # matches older than this contribute negligible decayed weight anyway


@dataclass(frozen=True)
class PoissonRatings:
    teams: dict[str, dict[str, float]]  # team -> {"attack", "defense", "n_matches"}
    mu: float
    home_advantage: float
    n_matches: int
    n_teams: int


def _decay_weight(match_date: date, as_of: date, halflife_days: float = HALFLIFE_DAYS) -> float:
    days = max(0, (as_of - match_date).days)
    return float(0.5 ** (days / halflife_days))


def _parse_rows(
    rows: list[dict], as_of: Optional[date] = None, lookback_years: int = LOOKBACK_YEARS
) -> list[dict]:
    """Filter to scored, recent-enough matches and attach a decay weight."""
    as_of = as_of or date.today()
    cutoff = date(as_of.year - lookback_years, as_of.month, as_of.day)
    out = []
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
        out.append({
            "home_team": r["home_team"], "away_team": r["away_team"],
            "home_score": int(float(hs)), "away_score": int(float(aws)),
            "neutral": str(r.get("neutral", "FALSE")).strip().upper() == "TRUE",
            "weight": _decay_weight(d, as_of),
        })
    return out


def fit(
    rows: list[dict],
    as_of: Optional[date] = None,
    lookback_years: int = LOOKBACK_YEARS,
    ridge_alpha: float = RIDGE_ALPHA,
) -> PoissonRatings:
    """
    Fit attack/defense/home-advantage jointly from real match rows (as loaded
    by fetch_international_results.load_cached()). Analytic gradient — with
    ~250 teams (~500 free parameters) over thousands of matches, finite-
    difference gradients would be prohibitively slow.
    """
    matches = _parse_rows(rows, as_of=as_of, lookback_years=lookback_years)
    if not matches:
        return PoissonRatings(teams={}, mu=0.0, home_advantage=0.0, n_matches=0, n_teams=0)

    teams = sorted({m["home_team"] for m in matches} | {m["away_team"] for m in matches})
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)

    home_idx = np.array([idx[m["home_team"]] for m in matches])
    away_idx = np.array([idx[m["away_team"]] for m in matches])
    hg = np.array([m["home_score"] for m in matches], dtype=float)
    ag = np.array([m["away_score"] for m in matches], dtype=float)
    not_neutral = np.array([0.0 if m["neutral"] else 1.0 for m in matches])
    weight = np.array([m["weight"] for m in matches])
    n_matches_per_team = np.zeros(T)
    for m in matches:
        n_matches_per_team[idx[m["home_team"]]] += 1
        n_matches_per_team[idx[m["away_team"]]] += 1

    def unpack(x: np.ndarray):
        mu, home_adv = x[0], x[1]
        attack = x[2:2 + T]
        defense = x[2 + T:2 + 2 * T]
        return mu, home_adv, attack, defense

    def nll_and_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
        mu, home_adv, attack, defense = unpack(x)
        lam_h = np.exp(mu + home_adv * not_neutral + attack[home_idx] - defense[away_idx])
        lam_a = np.exp(mu + attack[away_idx] - defense[home_idx])
        lam_h = np.clip(lam_h, 1e-8, 1e6)
        lam_a = np.clip(lam_a, 1e-8, 1e6)

        nll = float(np.sum(weight * (lam_h - hg * np.log(lam_h)))
                     + np.sum(weight * (lam_a - ag * np.log(lam_a)))
                     + ridge_alpha * (np.sum(attack**2) + np.sum(defense**2)))

        res_h = weight * (lam_h - hg)   # d(nll)/d(log lam_h)
        res_a = weight * (lam_a - ag)

        g_mu = float(np.sum(res_h) + np.sum(res_a))
        g_home_adv = float(np.sum(res_h * not_neutral))
        g_attack = np.zeros(T)
        g_defense = np.zeros(T)
        np.add.at(g_attack, home_idx, res_h)
        np.add.at(g_attack, away_idx, res_a)
        np.add.at(g_defense, away_idx, -res_h)
        np.add.at(g_defense, home_idx, -res_a)
        g_attack += 2 * ridge_alpha * attack
        g_defense += 2 * ridge_alpha * defense

        return nll, np.concatenate([[g_mu, g_home_adv], g_attack, g_defense])

    x0 = np.zeros(2 + 2 * T)
    x0[0] = np.log(max(1e-3, float(np.mean(np.concatenate([hg, ag])))))
    x0[1] = 0.25  # sane home-advantage prior on the log scale

    result = minimize(nll_and_grad, x0, jac=True, method="L-BFGS-B",
                       options={"maxiter": 300})
    mu, home_adv, attack, defense = unpack(result.x)

    return PoissonRatings(
        teams={
            t: {"attack": round(float(attack[i]), 4),
                "defense": round(float(defense[i]), 4),
                "n_matches": int(n_matches_per_team[i])}
            for t, i in idx.items()
        },
        mu=round(float(mu), 4),
        home_advantage=round(float(home_adv), 4),
        n_matches=len(matches),
        n_teams=T,
    )


def lambdas_for(ratings: PoissonRatings, home_team: str, away_team: str, neutral: bool = True) -> tuple[float, float]:
    """Predicted (lambda_home, lambda_away) for a matchup from fitted ratings."""
    h = ratings.teams.get(home_team, {"attack": 0.0, "defense": 0.0})
    a = ratings.teams.get(away_team, {"attack": 0.0, "defense": 0.0})
    home_adv = 0.0 if neutral else ratings.home_advantage
    lh = np.exp(ratings.mu + home_adv + h["attack"] - a["defense"])
    la = np.exp(ratings.mu + a["attack"] - h["defense"])
    return float(lh), float(la)
