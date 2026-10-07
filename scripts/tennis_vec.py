#!/usr/bin/env python3
"""
tennis_vec.py — vectorised point-by-point tennis simulator with match-level random effects.

Why: tennis_games_model.simulate_match is a Python loop (~20k matches in seconds, minutes
once calibrated per match). This runs N matches at once as numpy arrays — the whole
match is built from Bernoulli points (game hold = exact closed form, tie-breaks are
simulated point by point) — and adds the missing piece the backtest exposed:

  HIERARCHICAL EFFECT. A serve-point rate is not a constant, it is a player's long-run
  rate PLUS a day-specific shock (form, conditions, opponent return). With every match
  given its own p_i = p + sd*z, the margin distribution gets the fat tails the iid
  simulator lacked (measured: P(margin > 4.5 games) understated 4-6 pts) with ONE
  physical parameter instead of a fudge multiplier. Antithetic pairs (z, -z) halve the
  variance of the estimate for free.
"""
from __future__ import annotations

import numpy as np


def hold(p: np.ndarray) -> np.ndarray:
    """P(server holds a game) — exact: p^4(1+4q+10q^2) + 20 p^3 q^3 * p^2/(p^2+q^2)."""
    q = 1.0 - p
    return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * p ** 3 * q ** 3 * (p * p / (p * p + q * q))


def _tiebreak(pa, pb, first, rng):
    """First to 7, win by 2; serve 1 then 2-2. Returns winner (0=A,1=B) for each row."""
    n = pa.shape[0]
    pts = np.zeros((n, 2), dtype=np.int16)
    server = first.copy()
    left = np.ones(n, dtype=np.int8)
    done = np.zeros(n, dtype=bool)
    win = np.zeros(n, dtype=np.int8)
    for _ in range(80):
        if done.all():
            break
        p_srv = np.where(server == 0, pa, pb)
        srv_wins = rng.random(n) < p_srv
        w = np.where(srv_wins, server, 1 - server)
        act = ~done
        pts[act & (w == 0), 0] += 1
        pts[act & (w == 1), 1] += 1
        a, b = pts[:, 0], pts[:, 1]
        fin = act & (((a >= 7) & (a - b >= 2)) | ((b >= 7) & (b - a >= 2)))
        win[fin] = np.where(a[fin] > b[fin], 0, 1)
        done |= fin
        left = np.where(act, left - 1, left)
        flip = act & (left == 0)
        server = np.where(flip, 1 - server, server)
        left = np.where(flip, 2, left)
    return win


def _set(pa, pb, ha, hb, first, rng):
    """One set for every row. Returns (winner, gA, gB, next_first_server)."""
    n = pa.shape[0]
    ga = np.zeros(n, dtype=np.int16)
    gb = np.zeros(n, dtype=np.int16)
    server = first.copy()
    done = np.zeros(n, dtype=bool)
    tb_rows = np.zeros(n, dtype=bool)
    for _ in range(12):
        act = ~done
        if not act.any():
            break
        p_hold = np.where(server == 0, ha, hb)
        srv_wins = rng.random(n) < p_hold
        w = np.where(srv_wins, server, 1 - server)
        ga = ga + (act & (w == 0))
        gb = gb + (act & (w == 1))
        server = np.where(act, 1 - server, server)
        fin = act & (((ga >= 6) & (ga - gb >= 2)) | ((gb >= 6) & (gb - ga >= 2)))
        tb = act & (ga == 6) & (gb == 6)
        done |= fin | tb
        tb_rows |= tb
    win = np.where(ga > gb, 0, 1).astype(np.int8)
    nxt = server.copy()
    if tb_rows.any():
        idx = np.where(tb_rows)[0]
        w = _tiebreak(pa[idx], pb[idx], server[idx], rng)
        ga[idx] += (w == 0)
        gb[idx] += (w == 1)
        win[idx] = w
        nxt[idx] = 1 - server[idx]
    return win, ga, gb, nxt


def simulate(pa, pb, n=20000, sd=0.0, seed=0, best_of=3, antithetic=True):
    """Simulate n matches. pa/pb: serve-point win probs (scalars). sd: day-to-day sd of
    each player's serve-point rate (0 = the old iid model)."""
    rng = np.random.default_rng(seed)
    if antithetic and n % 2:
        n += 1
    half = n // 2 if antithetic else n
    z = rng.standard_normal((half, 2))
    z = np.concatenate([z, -z]) if antithetic else z
    pa_i = np.clip(pa + sd * z[:, 0], 0.30, 0.90)
    pb_i = np.clip(pb + sd * z[:, 1], 0.30, 0.90)
    ha, hb = hold(pa_i), hold(pb_i)
    need = best_of // 2 + 1
    sets = np.zeros((n, 2), dtype=np.int8)
    games = np.zeros((n, 2), dtype=np.int16)
    first = rng.integers(0, 2, n).astype(np.int8)
    s1w = np.zeros(n, dtype=np.int8)
    s1g = np.zeros(n, dtype=np.int16)
    for k in range(best_of):
        act = sets.max(1) < need
        if not act.any():
            break
        w, ga, gb, nxt = _set(pa_i, pb_i, ha, hb, first, rng)
        sets[act & (w == 0), 0] += 1
        sets[act & (w == 1), 1] += 1
        games[act, 0] += ga[act]
        games[act, 1] += gb[act]
        if k == 0:
            s1w, s1g = w.copy(), (ga + gb).astype(np.int16)
        first = np.where(act, nxt, first)
    winner = np.where(sets[:, 0] >= need, 0, 1).astype(np.int8)
    return {"winner": winner, "sets": sets, "games": games, "s1w": s1w, "s1g": s1g,
            "margin": (games[:, 0] - games[:, 1]).astype(np.int16),
            "total": (games[:, 0] + games[:, 1]).astype(np.int16)}


def calibrate(pa, pb, target_a, sd=0.0, n=6000, iters=14, seed=1):
    """Level shift d (pa+d, pb-d) so P(A wins match) == target, with the effect sd in."""
    lo, hi = -0.10, 0.10
    for _ in range(iters):
        d = (lo + hi) / 2
        w = simulate(pa + d, pb - d, n, sd, seed)["winner"]
        lo, hi = (d, hi) if (w == 0).mean() < target_a else (lo, d)
    return (lo + hi) / 2


# ── Numba-compiled kernel (same model, one compiled loop per match, parallel across cores) ──
try:
    from numba import njit, prange

    @njit(cache=True, fastmath=True)
    def _hold_nb(p):
        q = 1.0 - p
        return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * p ** 3 * q ** 3 * (p * p / (p * p + q * q))

    @njit(cache=True, fastmath=True)
    def _tb_nb(pa, pb, first):
        a = 0
        b = 0
        server = first
        left = 1
        while True:
            ps = pa if server == 0 else pb
            w = server if np.random.random() < ps else 1 - server
            if w == 0:
                a += 1
            else:
                b += 1
            if (a >= 7 and a - b >= 2) or (b >= 7 and b - a >= 2):
                return 0 if a > b else 1
            left -= 1
            if left == 0:
                server = 1 - server
                left = 2

    @njit(parallel=True, cache=True, fastmath=True)
    def _sim_nb(pa, pb, z, sda, sdb, best_of, seed):
        n = z.shape[0]
        need = best_of // 2 + 1
        out = np.zeros((n, 7), dtype=np.int16)     # winner, setsA, setsB, s1w, s1g, gA, gB
        np.random.seed(seed)
        for i in prange(n):
            pai = min(0.90, max(0.30, pa + sda * z[i, 0]))
            pbi = min(0.90, max(0.30, pb + sdb * z[i, 1]))
            ha, hb = _hold_nb(pai), _hold_nb(pbi)
            sa = 0
            sb = 0
            gA = 0
            gB = 0
            first = 0 if np.random.random() < 0.5 else 1
            first_set = True
            while sa < need and sb < need:
                ga = 0
                gb = 0
                server = first
                while True:
                    hold = ha if server == 0 else hb
                    w = server if np.random.random() < hold else 1 - server
                    if w == 0:
                        ga += 1
                    else:
                        gb += 1
                    server = 1 - server
                    if (ga >= 6 and ga - gb >= 2) or (gb >= 6 and gb - ga >= 2):
                        break
                    if ga == 6 and gb == 6:
                        t = _tb_nb(pai, pbi, server)
                        if t == 0:
                            ga += 1
                        else:
                            gb += 1
                        server = 1 - server
                        break
                if ga > gb:
                    sa += 1
                else:
                    sb += 1
                gA += ga
                gB += gb
                if first_set:
                    out[i, 3] = 0 if ga > gb else 1
                    out[i, 4] = ga + gb
                    first_set = False
                first = server
            out[i, 0] = 0 if sa >= need else 1
            out[i, 1] = sa
            out[i, 2] = sb
            out[i, 5] = gA
            out[i, 6] = gB
        return out

    def simulate_nb(pa, pb, n=20000, sd=0.0, seed=0, best_of=3):
        """Numba path: identical model to simulate(); antithetic effect draws; returns the same dict."""
        rng = np.random.default_rng(seed)
        half = max(1, n // 2)
        z = rng.standard_normal((half, 2))
        z = np.concatenate([z, -z])
        sda, sdb = (sd if isinstance(sd, (tuple, list)) else (sd, sd))
        o = _sim_nb(float(pa), float(pb), z, float(sda), float(sdb), best_of, int(seed) & 0x7FFFFFFF)
        return {"winner": o[:, 0].astype(np.int8), "sets": o[:, 1:3].astype(np.int8), "s1w": o[:, 3].astype(np.int8),
                "s1g": o[:, 4], "games": o[:, 5:7], "margin": (o[:, 5] - o[:, 6]).astype(np.int16),
                "total": (o[:, 5] + o[:, 6]).astype(np.int16)}

    HAVE_NUMBA = True
except Exception:                                   # pragma: no cover — numpy path stays the reference
    HAVE_NUMBA = False
    simulate_nb = simulate
