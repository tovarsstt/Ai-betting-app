"""
ucl_model.py — price Champions League ties across leagues.

Problem: club_ratings.json attack/defense are per-league (not comparable), so a
Ligue 1 side vs a La Liga side (or Slavia/Sabah/Slovan, absent from the big-5)
can't be priced. Bridge: ClubElo is ONE scale for all of Europe. Goal rates:

    log λ_home = a + h + b * (Elo_home - Elo_away) / 400   (h=0 if neutral)
    log λ_away = a     - b * (Elo_home - Elo_away) / 400

(a, h, b) are fit by Poisson regression on real results where both clubs have
an Elo (`calibrate`). Until calibrated, PRIORS are used and every output says
`calibrated: False` — they are assumptions, not measurements.

Then the existing Dixon-Coles matrix / market derivation (soccer_markets) turns
λ into 1X2, totals and BTTS, and `blend_with_market` shrinks toward the de-vigged
market (the market is the stronger prior; default model weight 0.35).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

import soccer_markets as sm

# Uncalibrated priors (assumption). `calibrate()` replaces them.
PRIOR_A, PRIOR_H, PRIOR_B = math.log(1.30), 0.12, 0.30
MODEL_WEIGHT = 0.35


@dataclass(frozen=True)
class EloGoalModel:
    a: float = PRIOR_A
    h: float = PRIOR_H
    b: float = PRIOR_B
    calibrated: bool = False
    n_matches: int = 0


def lambdas(m: EloGoalModel, elo_home: float, elo_away: float, neutral: bool = False) -> tuple[float, float]:
    d = (elo_home - elo_away) / 400.0
    lh = math.exp(m.a + (0.0 if neutral else m.h) + m.b * d)
    la = math.exp(m.a - m.b * d)
    return max(0.15, lh), max(0.15, la)


def calibrate(rows: list[dict], elo: dict[str, float], l2: float = 1e-3, min_matches: int = 200) -> EloGoalModel:
    """Fit (a,h,b) from real results. rows: dicts with home_team, away_team,
    home_score, away_score, neutral. Matches where either club has no Elo are
    dropped (never imputed). Falls back to priors (calibrated=False) if too few."""
    X, GH, GA, NEU = [], [], [], []
    for r in rows:
        eh, ea = elo.get(r["home_team"]), elo.get(r["away_team"])
        if eh is None or ea is None:
            continue
        X.append((eh - ea) / 400.0)
        GH.append(float(r["home_score"])); GA.append(float(r["away_score"]))
        NEU.append(str(r.get("neutral", "FALSE")).upper() == "TRUE")
    if len(X) < min_matches:
        return EloGoalModel()
    X, GH, GA, NEU = map(np.array, (X, GH, GA, NEU))
    home = (~NEU).astype(float)

    def nll(p: np.ndarray) -> float:
        a, h, b = p
        eh = a + h * home + b * X
        ea = a - b * X
        return float(np.sum(np.exp(eh) - GH * eh) + np.sum(np.exp(ea) - GA * ea) + l2 * (b * b))

    res = minimize(nll, x0=np.array([PRIOR_A, PRIOR_H, PRIOR_B]), method="L-BFGS-B")
    a, h, b = (float(v) for v in res.x)
    return EloGoalModel(a=a, h=h, b=b, calibrated=True, n_matches=len(X))


def build_elo(rows: list[dict], k_dom: float = 20.0, k_eur: float = 40.0, hfa: float = 65.0,
              burn_in: int = 8) -> tuple[dict[str, float], list[dict]]:
    """Own cross-league Elo from real results (no ClubElo dependency). Domestic leagues are
    linked ONLY through UEFA-competition matches (league starts with 'UEFA'), which get a
    higher K so league strength propagates. Returns (final Elo, training samples) where each
    sample carries the PRE-match ratings (no look-ahead) and is kept only after both clubs
    have `burn_in` games."""
    elo: dict[str, float] = {}
    gp: dict[str, int] = {}
    samples: list[dict] = []
    for r in sorted(rows, key=lambda x: x["date"]):
        h, a = r["home_team"], r["away_team"]
        eh, ea = elo.setdefault(h, 1500.0), elo.setdefault(a, 1500.0)
        neutral = str(r.get("neutral", "FALSE")).upper() == "TRUE"
        hg, ag = int(r["home_score"]), int(r["away_score"])
        if gp.get(h, 0) >= burn_in and gp.get(a, 0) >= burn_in:
            samples.append({"home_team": h, "away_team": a, "home_score": hg, "away_score": ag,
                            "neutral": r.get("neutral", "FALSE"), "eh": eh, "ea": ea})
        exp = 1 / (1 + 10 ** (-(eh - ea + (0 if neutral else hfa)) / 400))
        gd = abs(hg - ag)
        mult = 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8)
        k = k_eur if str(r.get("league", "")).startswith("UEFA") else k_dom
        delta = k * mult * ((1.0 if hg > ag else 0.5 if hg == ag else 0.0) - exp)
        elo[h], elo[a] = eh + delta, ea - delta
        gp[h], gp[a] = gp.get(h, 0) + 1, gp.get(a, 0) + 1
    return elo, samples


def calibrate_pre(samples: list[dict], l2: float = 1e-3, min_matches: int = 200) -> EloGoalModel:
    """Same Poisson fit as `calibrate`, using the pre-match Elo stored in each sample."""
    if len(samples) < min_matches:
        return EloGoalModel()
    X = np.array([(r["eh"] - r["ea"]) / 400.0 for r in samples])
    GH = np.array([float(r["home_score"]) for r in samples])
    GA = np.array([float(r["away_score"]) for r in samples])
    home = np.array([0.0 if str(r.get("neutral", "FALSE")).upper() == "TRUE" else 1.0 for r in samples])

    def nll(p: np.ndarray) -> float:
        a, h, b = p
        eh, ea = a + h * home + b * X, a - b * X
        return float(np.sum(np.exp(eh) - GH * eh) + np.sum(np.exp(ea) - GA * ea) + l2 * b * b)

    res = minimize(nll, x0=np.array([PRIOR_A, PRIOR_H, PRIOR_B]), method="L-BFGS-B")
    a, h, b = (float(v) for v in res.x)
    return EloGoalModel(a=a, h=h, b=b, calibrated=True, n_matches=len(samples))


def blend_with_market(model: dict[str, float], market: dict[str, float] | None, w: float = MODEL_WEIGHT) -> dict[str, float]:
    if not market:
        return dict(model)
    return {k: w * model[k] + (1 - w) * market[k] for k in ("home", "draw", "away")}


def price_match(home: str, away: str, elo: dict[str, float], model: EloGoalModel | None = None,
                neutral: bool = False, market_odds: tuple[float, float, float] | None = None) -> dict:
    """Output order: P(win) first, then odds, EV last (project rule)."""
    model = model or EloGoalModel()
    eh, ea = elo.get(home), elo.get(away)
    if eh is None or ea is None:
        missing = home if eh is None else away
        return {"error": f"no Elo rating for {missing} (club absent from fetched results; never imputed)"}
    lh, la = lambdas(model, eh, ea, neutral)
    book = sm.derive_markets(sm.score_matrix(lh, la))
    raw = {"home": book.home_win, "draw": book.draw, "away": book.away_win}
    mkt = None
    out: dict = {"lambda_home": lh, "lambda_away": la, "calibrated": model.calibrated,
                 "elo": {"home": eh, "away": ea}}
    if market_odds:
        inv = [1 / o for o in market_odds]
        s = sum(inv)
        mkt = {"home": inv[0] / s, "draw": inv[1] / s, "away": inv[2] / s}
        out["market_fair"] = mkt
        out["overround_pct"] = (s - 1) * 100
    final = blend_with_market(raw, mkt)
    out.update({"p_win": final, "model_only": raw,
                "over_2_5": book.over_under[2.5]["over"], "btts": book.btts_yes})
    if market_odds:
        out["ev_per_unit"] = {k: final[k] * (o - 1) - (1 - final[k])
                              for k, o in zip(("home", "draw", "away"), market_odds)}
    return out
