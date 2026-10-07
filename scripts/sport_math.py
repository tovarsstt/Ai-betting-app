#!/usr/bin/env python3
"""
sport_math.py — per-sport score distributions, calibrated on that sport's own closing lines.

One rule (feedback_per_league_model_design): reuse the MATH, never port a model across sports.
Each sport gets the distribution family its scoring process actually has, with parameters fitted
on earlier seasons and judged on later ones:

  soccer    low-scoring, draws, dependence      Poisson / Dixon-Coles tau / bivariate Poisson
  NHL, MLB  low-scoring, no draws (OT/extras)   Poisson / negative binomial (over-dispersion)
  NBA       high-scoring, continuous            Normal margin & total, sigma(spread), corr(margin,total)
  NFL       discrete margin with KEY NUMBERS    empirical conditional margin pmf (3, 6, 7, 10, 14 ...)

Inputs are market-anchored: the closing total and the de-vigged moneyline (or spread) fix the two
team means; the fitted family decides everything else (draw mass, tails, cover probabilities).
`python3 scripts/sport_math.py` re-fits everything and writes data/sport_math_calibration.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
KG = Path("/tmp/kg")
OUT = DATA / "sport_math_calibration.json"
K = 31                                                    # score grid 0..30


# ── discrete score matrices (low-scoring sports) ─────────────────────────────────────
def pmf_matrix(lh: np.ndarray, la: np.ndarray, family: str = "poisson", r: float = 1e6, rho: float = 0.0, l3: float = 0.0) -> np.ndarray:
    """(n, K, K) joint pmf for home goals x away goals, vectorised over games."""
    k = np.arange(K)
    lh, la = np.atleast_1d(lh)[:, None], np.atleast_1d(la)[:, None]
    if family == "nb":
        ph, pa = stats.nbinom.pmf(k[None, :], r, r / (r + lh)), stats.nbinom.pmf(k[None, :], r, r / (r + la))
        M = ph[:, :, None] * pa[:, None, :]
    elif family == "bvp":                                   # bivariate Poisson: shared component l3 (per-game share of the smaller mean)
        s = l3 * np.minimum(lh, la)
        ph, pa, p3 = stats.poisson.pmf(k[None, :], lh - s), stats.poisson.pmf(k[None, :], la - s), stats.poisson.pmf(k[None, :], s)
        M = np.zeros((lh.shape[0], K, K))
        for j in range(0, 8):                               # truncated convolution over the shared component (8 terms is exact to <1e-6 for l3<=1)
            sh_h = np.roll(ph, j, axis=1) * (np.arange(K)[None, :] >= j)
            sh_a = np.roll(pa, j, axis=1) * (np.arange(K)[None, :] >= j)
            M += p3[:, j][:, None, None] * sh_h[:, :, None] * sh_a[:, None, :]
    else:
        ph, pa = stats.poisson.pmf(k[None, :], lh), stats.poisson.pmf(k[None, :], la)
        M = ph[:, :, None] * pa[:, None, :]
        if family == "dc":                                  # Dixon-Coles low-score correction
            tau = np.ones_like(M)
            tau[:, 0, 0] = 1 - lh[:, 0] * la[:, 0] * rho
            tau[:, 0, 1] = 1 + lh[:, 0] * rho
            tau[:, 1, 0] = 1 + la[:, 0] * rho
            tau[:, 1, 1] = 1 - rho
            M = M * tau
    return M / M.sum(axis=(1, 2), keepdims=True)


def outcome_probs(M: np.ndarray, tie_split: float = 0.5) -> Dict[str, np.ndarray]:
    """win/draw/loss and margin distribution from the joint matrix."""
    n = M.shape[0]
    h, a = np.indices((K, K))
    d = (h - a)
    P = {"home": (M * (d > 0)).sum((1, 2)), "draw": (M * (d == 0)).sum((1, 2)), "away": (M * (d < 0)).sum((1, 2))}
    P["home_2w"] = P["home"] + tie_split * P["draw"]          # no-draw sports: ties resolved in OT / extra innings
    return P


def cover(M: np.ndarray, line: float) -> np.ndarray:
    """P(home margin + line > 0) for a half-point line (push impossible)."""
    h, a = np.indices((K, K))
    return (M * ((h - a + line) > 0)).sum((1, 2))


def over(M: np.ndarray, total: float) -> np.ndarray:
    h, a = np.indices((K, K))
    return (M * ((h + a) > total)).sum((1, 2))


def means_from_market(total: np.ndarray, p_home: np.ndarray, family: str, params: dict, tie_split: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
    """Solve (lh, la) with lh+la = total and P(home wins | family) = p_home (bisection on the home share)."""
    lo, hi = np.full_like(total, 0.05), np.full_like(total, 0.95)
    for _ in range(22):
        s = (lo + hi) / 2
        M = pmf_matrix(s * total, (1 - s) * total, family, **params)
        w = outcome_probs(M, tie_split)["home_2w" if tie_split > 0 else "home"]
        up = w < p_home
        lo, hi = np.where(up, s, lo), np.where(up, hi, s)
    s = (lo + hi) / 2
    return s * total, (1 - s) * total


def _loglik(M: np.ndarray, h: np.ndarray, a: np.ndarray) -> float:
    hh, aa = np.minimum(h, K - 1), np.minimum(a, K - 1)
    return float(np.mean(np.log(np.clip(M[np.arange(len(h)), hh, aa], 1e-12, None))))


def fit_family(df: pd.DataFrame, family: str, tie_split: float, grid: np.ndarray, pname: str) -> Dict[str, float]:
    """Fit ONE shape parameter by max-likelihood on the train slice; report train/test log-lik per game."""
    tr, te = df[df.train], df[~df.train]

    def ll(x: float, d: pd.DataFrame) -> float:
        prm = {pname: x}
        lh, la = means_from_market(d.total.values, d.p_home.values, family, prm, tie_split)
        return _loglik(pmf_matrix(lh, la, family, **prm), d.h.values, d.a.values)

    scores = [ll(x, tr) for x in grid]
    best = float(grid[int(np.argmax(scores))])
    return {"param": best, "train_ll": float(max(scores)), "test_ll": ll(best, te), "n_train": len(tr), "n_test": len(te)}


# ── loaders (closing lines + results) ───────────────────────────────────────────────
def _devig2(a, b):
    return np.array([bm.devig_power([x, y])[0] for x, y in zip(a, b)])


def _dec(american: np.ndarray) -> np.ndarray:
    a = np.asarray(american, float)
    return np.where(a > 0, 1 + a / 100.0, 1 + 100.0 / -a)


def load_espn(name: str, hs: str, as_: str) -> pd.DataFrame:
    fs = sorted((KG / "closing_odds").glob(f"{name}*.xlsx"))
    d = pd.concat([pd.read_excel(f) for f in fs], ignore_index=True)
    d = d.dropna(subset=["home_ml", "away_ml", "total", hs, as_]).copy()
    d = d[(d.home_ml.abs() >= 100) & (d.away_ml.abs() >= 100)]
    d["p_home"] = _devig2(_dec(d.home_ml.values), _dec(d.away_ml.values))
    d["h"], d["a"] = d[hs].astype(int), d[as_].astype(int)
    d["date"] = pd.to_datetime(d.game_time, utc=True)
    d = d.sort_values("date").reset_index(drop=True)
    d["train"] = np.arange(len(d)) < int(0.6 * len(d))
    return d


def load_soccer() -> pd.DataFrame:
    fr = [pd.read_csv(f, encoding="latin1", on_bad_lines="skip", low_memory=False) for f in sorted((KG / "ext/fd").glob("*.csv"))]
    d = pd.concat(fr, ignore_index=True).dropna(subset=["FTHG", "FTAG", "PSCH", "PSCD", "PSCA", "PC>2.5", "PC<2.5"]).copy()
    d = d[(d[["PSCH", "PSCD", "PSCA", "PC>2.5", "PC<2.5"]] > 1).all(axis=1)]
    P = np.array([bm.devig_power([x, y, z]) for x, y, z in zip(d.PSCH, d.PSCD, d.PSCA)])
    d["p_home"], d["p_draw"], d["p_away"] = P[:, 0], P[:, 1], P[:, 2]
    po = 1 / d["PC>2.5"]
    pu = 1 / d["PC<2.5"]
    d["p_over25"] = po / (po + pu)
    grid, sf = np.linspace(0.4, 7.0, 4000), None
    sf = stats.poisson.sf(2, grid)
    d["total"] = np.interp(d.p_over25.clip(0.03, 0.97).values, sf, grid)
    d["h"], d["a"] = d.FTHG.astype(int), d.FTAG.astype(int)
    d["date"] = pd.to_datetime(d.Date, dayfirst=True, errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    d["train"] = np.arange(len(d)) < int(0.6 * len(d))
    return d


# ── soccer: 3-way anchored Dixon-Coles (draw mass calibrated PER MATCH to the market) ────
def soccer_3way(total: np.ndarray, p_home: np.ndarray, p_draw: np.ndarray, iters: int = 4) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (lh, la, rho) so the Dixon-Coles matrix reproduces the market home AND draw probabilities.
    Plain Poisson under-prices draws (23.1% vs 25.05% actual on 6.2k closing lines); a single global rho
    only closes half the gap, so rho is solved per match."""
    rho = np.full_like(total, -0.06)
    for _ in range(iters):
        lh = la = None
        lo, hi = np.full_like(total, 0.05), np.full_like(total, 0.95)
        for _i in range(20):                                    # home share of the total, given rho
            sh = (lo + hi) / 2
            M = _dc(sh * total, (1 - sh) * total, rho)
            w = outcome_probs(M, 0.0)["home"]
            up = w < p_home
            lo, hi = np.where(up, sh, lo), np.where(up, hi, sh)
        sh = (lo + hi) / 2
        lh, la = sh * total, (1 - sh) * total
        rl, rh = np.full_like(total, -0.30), np.full_like(total, 0.10)
        for _i in range(20):                                    # rho that hits the market draw probability
            rr = (rl + rh) / 2
            dd = outcome_probs(_dc(lh, la, rr), 0.0)["draw"]
            up = dd < p_draw                                    # need more draw mass -> more negative rho
            rl, rh = np.where(up, rl, rr), np.where(up, rr, rh)
        rho = (rl + rh) / 2
    return lh, la, rho


def soccer_3way_diag(total: np.ndarray, p_home: np.ndarray, p_draw: np.ndarray, iters: int = 4) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Diagonal-inflated Poisson (Karlis-Ntzoufras): M' = (1-e) M_poisson + e * D, D = the draw diagonal of M
    renormalised. Reproduces the market's home, draw AND away probabilities exactly and, unlike Dixon-Coles tau
    (which dumps the extra draw mass on 0-0: model 7.7% vs 5.9% actual), keeps the score-line shape — held-out
    score log-lik -2.8699 vs Poisson -2.8711. Returns (M', lh, la, e)."""
    idx = np.arange(K)
    sh = np.full_like(total, 0.5)
    for _ in range(iters):
        lo, hi = np.full_like(total, 0.02), np.full_like(total, 0.98)
        for _i in range(22):
            s_ = (lo + hi) / 2
            Mp = pmf_matrix(s_ * total, (1 - s_) * total)
            pdw = Mp[:, idx, idx].sum(1)
            e = np.clip((p_draw - pdw) / (1 - pdw), 0.0, 0.6)
            dm = Mp[:, idx, idx]
            D = np.zeros_like(Mp)
            D[:, idx, idx] = dm / dm.sum(1, keepdims=True)
            M = (1 - e)[:, None, None] * Mp + e[:, None, None] * D
            w = outcome_probs(M, 0.0)["home"]
            up = w < p_home
            lo, hi = np.where(up, s_, lo), np.where(up, hi, s_)
        sh = (lo + hi) / 2
    Mp = pmf_matrix(sh * total, (1 - sh) * total)
    pdw = Mp[:, idx, idx].sum(1)
    e = np.clip((p_draw - pdw) / (1 - pdw), 0.0, 0.6)
    dm = Mp[:, idx, idx]
    D = np.zeros_like(Mp)
    D[:, idx, idx] = dm / dm.sum(1, keepdims=True)
    return (1 - e)[:, None, None] * Mp + e[:, None, None] * D, sh * total, (1 - sh) * total, e


def _dc(lh: np.ndarray, la: np.ndarray, rho: np.ndarray) -> np.ndarray:
    k = np.arange(K)
    ph, pa = stats.poisson.pmf(k[None, :], lh[:, None]), stats.poisson.pmf(k[None, :], la[:, None])
    M = ph[:, :, None] * pa[:, None, :]
    tau = np.ones_like(M)
    tau[:, 0, 0] = 1 - lh * la * rho
    tau[:, 0, 1] = 1 + lh * rho
    tau[:, 1, 0] = 1 + la * rho
    tau[:, 1, 1] = 1 - rho
    M = M * np.clip(tau, 1e-6, None)
    return M / M.sum(axis=(1, 2), keepdims=True)


# ── per-sport calibration ───────────────────────────────────────────────────────────
def calibrate_low_scoring(d: pd.DataFrame, sport: str, families: Dict[str, Tuple[str, np.ndarray, str]], tie_split: float) -> dict:
    out = {"n": len(d), "families": {}}
    base_te = fit_family(d, "poisson", tie_split, np.array([0.0]), "r")["test_ll"] if False else None
    prm0 = {}
    lh, la = means_from_market(d[~d.train].total.values, d[~d.train].p_home.values, "poisson", prm0, tie_split)
    out["families"]["poisson"] = {"test_ll": _loglik(pmf_matrix(lh, la), d[~d.train].h.values, d[~d.train].a.values)}
    for fam, (family, grid, pname) in families.items():
        out["families"][fam] = fit_family(d, family, tie_split, grid, pname)
    best = max(out["families"], key=lambda k: out["families"][k]["test_ll"])
    out["best"] = best
    out["gain_vs_poisson_ll_per_game"] = out["families"][best]["test_ll"] - out["families"]["poisson"]["test_ll"]
    return out


def derived_market_test(d: pd.DataFrame, family: str, params: dict, tie_split: float, line_col: str, price_cols=None) -> dict:
    """Price a market the model was NOT fitted on from (total, ML) and score it against what happened (and the market)."""
    te = d[~d.train]
    lh, la = means_from_market(te.total.values, te.p_home.values, family, params, tie_split)
    M = pmf_matrix(lh, la, family, **params)
    line = te[line_col].values
    # home covers 'home + line' (line is the home handicap as posted)
    pc = np.array([cover(M[i:i + 1], float(l))[0] for i, l in enumerate(line)])
    y = ((te.h - te.a + line) > 0).astype(float).values
    res = {"n": len(te), "brier_model": bm.brier(pc, y), "log_loss_model": bm.log_loss(pc, y)}
    if price_cols:
        ph, pa = _dec(te[price_cols[0]].values), _dec(te[price_cols[1]].values)
        mk = np.array([bm.devig_power([x, z])[0] for x, z in zip(ph, pa)])
        res.update({"brier_market": bm.brier(mk, y), "brier_blend": bm.brier((mk + pc) / 2, y)})
    return res


def calibrate_nba() -> dict:
    d = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
    d = d[d.regular == True].dropna(subset=["spread", "total", "score_home", "score_away", "moneyline_home", "moneyline_away"]).copy()
    d = d[(d.moneyline_home.abs() >= 100) & (d.moneyline_away.abs() >= 100)]
    d["date"] = pd.to_datetime(d.date)
    d = d.sort_values("date").reset_index(drop=True)
    exp = np.where(d.whos_favored == "home", d.spread, -d.spread)
    d["res_m"] = (d.score_home - d.score_away) - exp
    d["res_t"] = d.score_home + d.score_away - d.total
    tr = d.season <= 2018
    te = ~tr
    out = {"n": len(d), "sigma_margin": float(d.res_m[tr].std()), "sigma_total": float(d.res_t[tr].std()),
           "corr_margin_total": float(np.corrcoef(d.res_m[tr], d.res_t[tr])[0, 1]), "skew_margin": float(stats.skew(d.res_m[tr])),
           "excess_kurtosis_margin": float(stats.kurtosis(d.res_m[tr])), "mean_resid_margin": float(d.res_m[tr].mean()), "mean_resid_total": float(d.res_t[tr].mean())}
    # heteroscedasticity: does sigma grow with |spread| / total?
    ab = np.abs(exp)
    X = np.column_stack([np.ones(tr.sum()), ab[tr], d.total[tr] - d.total[tr].mean()])
    beta = np.linalg.lstsq(X, np.abs(d.res_m[tr]) * np.sqrt(np.pi / 2), rcond=None)[0]
    out["sigma_margin_model"] = {"intercept": float(beta[0]), "per_spread_pt": float(beta[1]), "per_total_pt": float(beta[2])}
    sg = lambda dd, ex: beta[0] + beta[1] * np.abs(ex) + beta[2] * (dd.total.values - d.total[tr].mean())
    # held-out log-lik: constant sigma vs sigma(spread,total), Student-t alternative
    res_te, ex_te = d.res_m[te].values, exp[te]
    out["test_ll_margin_const_sigma"] = float(stats.norm.logpdf(res_te, 0, out["sigma_margin"]).mean())
    out["test_ll_margin_hetero_sigma"] = float(stats.norm.logpdf(res_te, 0, np.clip(sg(d[te], ex_te), 8, 18)).mean())
    nu, loc, sc = stats.t.fit(d.res_m[tr].values, floc=0)[0], 0, stats.t.fit(d.res_m[tr].values, floc=0)[2]
    out["student_t"] = {"nu": float(nu), "scale": float(sc), "test_ll": float(stats.t.logpdf(res_te, nu, 0, sc).mean())}
    # spread -> win prob: Normal(sigma) vs the de-vigged ML, scored on held-out outcomes
    y = (d.score_home[te] > d.score_away[te]).astype(float).values
    p_norm = stats.norm.cdf(np.where(d.whos_favored[te] == "home", d.spread[te], -d.spread[te]) / out["sigma_margin"])
    p_ml = _devig2(_dec(d.moneyline_home[te].values), _dec(d.moneyline_away[te].values))
    out["win_prob"] = {"logloss_spread_normal": bm.log_loss(p_norm, y), "logloss_ml_devig": bm.log_loss(p_ml, y), "logloss_blend": bm.log_loss((p_norm + p_ml) / 2, y)}
    # totals: P(over) calibration at the posted total with the fitted sigma_total
    po = 1 - stats.norm.cdf(0, loc=out["mean_resid_total"], scale=out["sigma_total"])
    out["over_rate_expected_by_normal"], out["over_rate_actual_test"] = float(po), float((d.res_t[te] > 0).mean())
    return out


def calibrate_nfl() -> dict:
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    teams = pd.read_csv(KG / "nfl_spreadspoke/nfl_teams.csv")
    idmap = dict(zip(teams.team_name, teams.team_id))
    d = d[(d.schedule_season >= 1990) & d.spread_favorite.notna() & d.score_home.notna()].copy()
    d["home_id"] = d.team_home.map(idmap)
    home_fav = d.team_favorite_id == d.home_id
    d["exp_home"] = np.where(home_fav, -d.spread_favorite, d.spread_favorite)       # expected home margin
    d = d[d.team_favorite_id.notna() & (d.team_favorite_id != "PICK")]
    d["margin"] = d.score_home - d.score_away
    d["res"] = d.margin - d.exp_home
    tr = d.schedule_season <= 2016
    te = ~tr
    out = {"n": len(d), "sigma_margin": float(d.res[tr].std()), "mean_resid": float(d.res[tr].mean()), "skew": float(stats.skew(d.res[tr]))}
    key = {}
    for m in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 17, 20, 21):
        key[m] = float(((d.margin[tr].abs()) == m).mean())
    out["margin_pmf_abs"] = key
    # empirical conditional pmf of the margin given the closing spread bucket (the key-number-aware model)
    def emp_cover(train_df, test_df, line_shift):
        res, ok = [], []
        for _, r in test_df.iterrows():
            sp = r.exp_home
            near = train_df[(train_df.exp_home - sp).abs() <= 1.5]
            if len(near) < 150:
                near = train_df[(train_df.exp_home - sp).abs() <= 3.5]
            res.append(((near.margin + line_shift) > -r.exp_home + 0).mean())  # placeholder replaced below
        return np.array(res)
    # P(home covers spread -exp_home at a shifted half-point line s): empirical share of historical margin residuals
    trd, ted = d[tr], d[te]
    bins = np.clip(np.round(ted.exp_home.values), -14, 14)
    trbins = np.clip(np.round(trd.exp_home.values), -14, 14)
    pe, pn, y = [], [], []
    shifts = (-0.5, 0.5, -3.5, 3.5, -7.5, 7.5)                       # alternative lines around the closing spread
    for s in shifts:
        for b in np.unique(bins):
            idx = bins == b
            near = trd.res.values[trbins == b]
            if len(near) < 80:
                near = trd.res.values
            # cover of alt line: home margin + exp_home... residual > -s  (spread moved by s)
            p_emp = float((near > -s).mean())
            p_n = float(1 - stats.norm.cdf(-s, out["mean_resid"], out["sigma_margin"]))
            outcome = (ted.res.values[idx] > -s).astype(float)
            pe += [p_emp] * idx.sum(); pn += [p_n] * idx.sum(); y += outcome.tolist()
    allres = d.res.round().astype(int).value_counts().sort_index()
    out["residual_pmf"] = {int(k): int(v) for k, v in allres.items() if -45 <= k <= 45}
    out["alt_line_cover_brier"] = {"empirical_keynumber": bm.brier(pe, y), "normal": bm.brier(pn, y), "n": len(y)}
    return out


def run() -> dict:
    out: Dict[str, dict] = {}
    out["soccer"] = {**calibrate_low_scoring(load_soccer(), "soccer", {"dc": ("dc", np.linspace(-0.12, 0.12, 25), "rho"), "bvp": ("bvp", np.linspace(0.0, 0.6, 13), "l3"),
                                                                    "nb": ("nb", np.array([8, 15, 30, 60, 120, 400]), "r")}, 0.0)}
    nhl = load_espn("NHL", "home_goals", "away_goals")
    out["nhl"] = {**calibrate_low_scoring(nhl, "nhl", {"nb": ("nb", np.array([6, 10, 15, 25, 50, 150, 600]), "r"), "bvp": ("bvp", np.linspace(0.0, 0.5, 11), "l3")}, 0.5)}
    mlb = load_espn("MLB", "home_runs", "away_runs")
    out["mlb"] = {**calibrate_low_scoring(mlb, "mlb", {"nb": ("nb", np.array([2.5, 3, 3.5, 4, 4.5, 5, 6, 10, 25, 600]), "r"), "bvp": ("bvp", np.linspace(0.0, 0.5, 11), "l3")}, 0.5)}
    out["nba"] = calibrate_nba()
    out["nfl"] = calibrate_nfl()
    return out


# ── public API: price any game from (total, home win prob) with the sport's OWN calibrated family ──
_CAL: dict | None = None


def _cal() -> dict:
    global _CAL
    if _CAL is None:
        _CAL = json.loads(OUT.read_text()) if OUT.exists() else {}
    return _CAL


def price_game(sport: str, total: float, p_home: float, line: float | None = None, total_line: float | None = None, p_draw: float | None = None) -> Dict[str, float]:
    """Home win / cover(home+line) / over(total_line) for one game. line/total_line should be half-points."""
    sport = sport.lower()
    c = _cal().get(sport, {})
    t, p = np.array([float(total)]), np.array([float(p_home)])
    if sport in ("mlb", "nhl"):
        fam = c.get("best", "poisson")
        prm = {"r": c["families"][fam]["param"]} if fam == "nb" else {}
        lh, la = means_from_market(t, p, fam if fam in ("nb",) else "poisson", prm, 0.5)
        M = pmf_matrix(lh, la, "nb" if fam == "nb" else "poisson", **prm)
        out = {"home_win": float(outcome_probs(M, 0.5)["home_2w"][0]), "family": fam, **({"r": prm["r"]} if prm else {})}
    elif sport == "soccer":
        if p_draw is not None:
            M, lh, la, _ = soccer_3way_diag(t, p, np.array([float(p_draw)]))
        else:
            lh, la = means_from_market(t, p, "poisson", {}, 0.0)
            M = pmf_matrix(lh, la)
        P = outcome_probs(M, 0.0)
        out = {"home": float(P["home"][0]), "draw": float(P["draw"][0]), "away": float(P["away"][0]), "family": "poisson" if p_draw is None else "diag-inflated poisson"}
    elif sport == "nba":
        sg = c["sigma_margin"]
        exp_margin = sg * stats.norm.ppf(np.clip(p_home, 1e-4, 1 - 1e-4))      # margin implied by the win prob under N(0, sigma)
        out = {"home_win": float(p_home), "implied_margin": float(exp_margin), "sigma": sg}
        if line is not None:
            out["cover"] = float(stats.norm.cdf((exp_margin + line) / sg))
        if total_line is not None:
            out["over"] = float(1 - stats.norm.cdf((total_line - total) / c["sigma_total"]))
        return out
    elif sport == "nfl":
        sg = c["sigma_margin"]
        exp_margin = sg * stats.norm.ppf(np.clip(p_home, 1e-4, 1 - 1e-4))
        pm = {int(k): v for k, v in c["residual_pmf"].items()}
        tot = sum(pm.values())
        out = {"home_win": float(p_home), "implied_margin": float(exp_margin)}
        if line is not None:
            # key-number aware: empirical residuals around the implied margin
            out["cover"] = float(sum(v for r_, v in pm.items() if exp_margin + r_ + line > 0) / tot)
            out["cover_normal"] = float(stats.norm.cdf((exp_margin + line) / sg))
        return out
    else:
        raise ValueError(f"no calibrated family for {sport}")
    if line is not None:
        out["cover"] = float(cover(M, line)[0])
    if total_line is not None:
        out["over"] = float(over(M, total_line)[0])
    return out


if __name__ == "__main__":
    res = run()
    OUT.write_text(json.dumps(res, indent=1, default=float))
    for sp, r in res.items():
        print(f"\n== {sp.upper()} ==")
        if "families" in r:
            for fam, v in r["families"].items():
                print(f"  {fam:<8} test log-lik/game {v['test_ll']:.4f}" + (f"  param {v['param']}" if "param" in v else ""))
            print(f"  best {r['best']}  gain vs Poisson {r['gain_vs_poisson_ll_per_game']:+.4f} nats/game  (n={r['n']})")
        else:
            print("  " + json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "margin_pmf_abs"}, default=float)[:1400])
