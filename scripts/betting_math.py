#!/usr/bin/env python3
"""
betting_math.py — the probability toolkit the picks engine should share.

Everything here is pure numpy/scipy, vectorised where it matters, and each piece is
exercised against REAL data by scripts/math_kit_validation.py (devig methods scored
on 24k tennis and ~7k football closing lines, calibration judged out-of-sample).

  1. De-vigging       multiplicative, additive, power, Shin — for N-way markets.
                      Shin/power move the margin onto longshots (favourite-longshot
                      bias); which one wins is an EMPIRICAL question, so it is scored.
  2. Proper scoring   log-loss, Brier, ranked probability score (1X2), CLV.
  3. Calibration      isotonic (pool-adjacent-violators), beta calibration, Platt —
                      fit on one slice, judged on another.
  4. Intervals        Wilson and Beta-posterior credible intervals for hit rates.
  5. Kelly            plain, and UNCERTAINTY-AWARE: maximise expected log-growth over
                      the posterior of p instead of trusting a point estimate, which
                      is what stops a fat-edge-on-12-matches pick from being sized
                      like a fat-edge-on-1,200.
  6. Sampling         Latin-hypercube Beta draws (parameter uncertainty with ~5x
                      fewer outer samples than iid) and a chi-square RNG self-test.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy import optimize, stats

EPS = 1e-12


# ── 1. de-vigging ───────────────────────────────────────────────────────────────────
def implied(odds: Sequence[float]) -> np.ndarray:
    return 1.0 / np.asarray(odds, dtype=float)


def overround(odds: Sequence[float]) -> float:
    return float(implied(odds).sum() - 1.0)


def devig_multiplicative(odds):
    q = implied(odds)
    return q / q.sum()


def devig_additive(odds):
    q = implied(odds)
    p = q - (q.sum() - 1.0) / len(q)
    p = np.clip(p, EPS, None)
    return p / p.sum()


def devig_power(odds):
    """p_i = q_i**k with k chosen so the probabilities sum to 1 (k >= 1 shrinks
    longshots more than favourites)."""
    q = implied(odds)
    if q.sum() <= 1.0:                       # no margin (or an arb): nothing to remove
        return q / q.sum()
    f = lambda k: (q ** k).sum() - 1.0
    hi = 2.0
    while f(hi) > 0 and hi < 512:            # widen until the root is bracketed
        hi *= 2
    if f(hi) > 0:                            # a ~1.00 price pins a prob near 1: fall back
        return q / q.sum()
    return q ** optimize.brentq(f, 1.0, hi)


def devig_shin(odds, tol=1e-12, max_iter=500):
    """Shin (1992/93): z = share of insider trading; solves
    p_i = (sqrt(z^2 + 4(1-z) q_i^2 / S) - z) / (2(1-z)), S = sum q."""
    q = implied(odds)
    S = q.sum()
    if S <= 1.0 + 1e-12:
        return q / S
    n = len(q)

    def probs(z):
        return (np.sqrt(z * z + 4 * (1 - z) * q * q / S) - z) / (2 * (1 - z))

    g = lambda z: probs(z).sum() - 1.0
    lo, hi = 0.0, 0.4999
    if g(lo) * g(hi) > 0:                      # degenerate (very low margin)
        return q / S
    z = optimize.brentq(g, lo, hi, xtol=tol, maxiter=max_iter)
    p = probs(z)
    return p / p.sum()


DEVIG = {"multiplicative": devig_multiplicative, "additive": devig_additive,
         "power": devig_power, "shin": devig_shin}


# ── 2. proper scoring ───────────────────────────────────────────────────────────────
def log_loss(p, y):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def multiclass_log_loss(P, outcome_idx):
    P = np.clip(np.asarray(P, float), EPS, 1.0)
    return float(-np.mean(np.log(P[np.arange(len(P)), np.asarray(outcome_idx, int)])))


def rps(P, outcome_idx):
    """Ranked probability score for ordered outcomes (home/draw/away)."""
    P = np.asarray(P, float)
    n, k = P.shape
    O = np.zeros_like(P)
    O[np.arange(n), np.asarray(outcome_idx, int)] = 1.0
    cp, co = np.cumsum(P, 1)[:, :-1], np.cumsum(O, 1)[:, :-1]
    return float(np.mean(((cp - co) ** 2).sum(1) / (k - 1)))


def clv_pct(odds_taken, odds_close):
    """Closing-line value in % of price: >0 means you beat the close."""
    return float((np.asarray(odds_taken, float) / np.asarray(odds_close, float) - 1.0).mean() * 100)


# ── 3. calibration ──────────────────────────────────────────────────────────────────
class Isotonic:
    """Monotone non-decreasing map p -> E[y|p] via pool-adjacent-violators."""

    def fit(self, p, y):
        p, y = np.asarray(p, float), np.asarray(y, float)
        order = np.argsort(p, kind="mergesort")
        xs, ys = p[order], y[order]
        vals, wts, edges = [], [], []
        for x, v in zip(xs, ys):
            vals.append(v)
            wts.append(1.0)
            edges.append(x)
            while len(vals) > 1 and vals[-2] > vals[-1]:
                w = wts[-2] + wts[-1]
                vals[-2] = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / w
                wts[-2] = w
                edges[-2] = edges[-1]
                vals.pop(); wts.pop(); edges.pop()
        self.x_, self.y_ = np.array(edges), np.array(vals)
        return self

    def predict(self, p):
        return np.interp(np.asarray(p, float), self.x_, self.y_)


class BetaCalibration:
    """Kull et al. 2017: logit(q) = a*ln p - b*ln(1-p) + c, fit by max likelihood.
    a=b=1,c=0 is the identity, so it can only improve on a calibrated input."""

    def fit(self, p, y):
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        y = np.asarray(y, float)
        X = np.column_stack([np.log(p), -np.log(1 - p), np.ones_like(p)])

        def nll(w):
            z = X @ w
            return np.sum(np.logaddexp(0, z) - y * z)

        def grad(w):
            return X.T @ (1 / (1 + np.exp(-(X @ w))) - y)

        r = optimize.minimize(nll, np.array([1.0, 1.0, 0.0]), jac=grad, method="BFGS")
        self.w_ = r.x
        return self

    def predict(self, p):
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        z = np.column_stack([np.log(p), -np.log(1 - p), np.ones_like(p)]) @ self.w_
        return 1 / (1 + np.exp(-z))


class Platt(BetaCalibration):
    """Two-parameter logistic on logit(p): the constrained special case a=b."""

    def fit(self, p, y):
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        lg, y = np.log(p / (1 - p)), np.asarray(y, float)
        f = lambda w: np.sum(np.logaddexp(0, w[0] * lg + w[1]) - y * (w[0] * lg + w[1]))
        self.w_ = optimize.minimize(f, np.array([1.0, 0.0]), method="BFGS").x
        return self

    def predict(self, p):
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        return 1 / (1 + np.exp(-(self.w_[0] * np.log(p / (1 - p)) + self.w_[1])))


# ── 4. intervals ────────────────────────────────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def beta_interval(k: int, n: int, a0: float = 1.0, b0: float = 1.0, level: float = 0.9):
    lo, hi = stats.beta.ppf([(1 - level) / 2, 1 - (1 - level) / 2], a0 + k, b0 + n - k)
    return float(lo), float(hi)


# ── 5. Kelly ────────────────────────────────────────────────────────────────────────
def kelly(p: float, odds: float) -> float:
    b = odds - 1.0
    return max(0.0, (p * b - (1 - p)) / b)


def kelly_uncertain(p_samples, odds: float, grid: int = 400, cap: float = 0.25):
    """Fraction maximising E[ln(1 + f*b)] if win else E[ln(1 - f)] across posterior
    draws of p. Returns (f*, point_kelly, expected_growth_at_f*). With a wide
    posterior f* < point Kelly, and f* = 0 when the edge doesn't survive the spread."""
    p = np.asarray(p_samples, float)
    b = odds - 1.0
    fs = np.linspace(0.0, cap, grid)
    g = (p[:, None] * np.log1p(fs[None, :] * b) + (1 - p[:, None]) * np.log1p(-fs[None, :])).mean(0)
    i = int(np.argmax(g))
    return float(fs[i]), kelly(float(p.mean()), odds), float(g[i])


# ── 6. sampling & self-tests ────────────────────────────────────────────────────────
def lhs_beta(n: int, a: float, b: float, seed: int = 0) -> np.ndarray:
    """Latin-hypercube draws from Beta(a,b): one sample in each of n equal-probability
    strata, so n=200 covers the tails like ~1,000 iid draws."""
    u = stats.qmc.LatinHypercube(d=1, seed=seed).random(n)[:, 0]
    return stats.beta.ppf(u, a, b)


def chi2_rng_test(sampler, p: float, n: int = 200_000, seed: int = 1) -> dict:
    """Is the simulator's success frequency compatible with p? (p-value < .05 => bias)"""
    rng = np.random.default_rng(seed)
    k = int(sampler(rng, n))
    res = stats.chisquare([k, n - k], [n * p, n * (1 - p)])
    return {"k": k, "n": n, "expected": n * p, "chi2": float(res.statistic), "p_value": float(res.pvalue),
            "biased": bool(res.pvalue < 0.05)}
