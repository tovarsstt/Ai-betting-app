"""
usage_vacuum.py — vacated-usage model: when a player leaves / is out, his minutes and shots go to teammates; when stars join a team,
everyone's share shrinks. Team totals (points, assists, rebounds, threes) are conserved:

  minutes   : m0 = last-season minutes per game (starters >= STARTER_MIN, bench <= BENCH_MAX), rescaled so the available
              rotation sums to 240 with a cap of MAX_MIN per player;
  share_i   = rate_i * m_i / sum_j rate_j * m_j       (rate = per-minute pts / ast / reb / 3PM from the player's own 2025-26 logs);
  role_i    = share_i(today) / share_i(last season, when he played)  -> multiplier applied to his bootstrapped box-score line.

validate_usage_vacuum.py checks the same formula out-of-sample on real 2025-26 absences before it is trusted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TEAM_MIN = 240.0
STARTER_MIN, BENCH_MAX, MAX_MIN = 28.0, 24.0, 38.0
DEFAULT_MIN = 8.0              # no logs (rookie / new): deep-bench minutes
ROTATION = 9                   # only the top-9 by projected minutes play (starters always); the rest of a 17-man roster gets 0
STATS = {"pts": "pts", "ast": "ast", "reb": "reb", "fg3m": "fg3m"}


def build_rates(logs: pd.DataFrame, team_tot: pd.DataFrame) -> pd.DataFrame:
    """Per athlete: games, mpg, per-minute rates, and mean share of his team's total when he played."""
    d = logs.merge(team_tot, on=["game_id", "team_id"], suffixes=("", "_t"))
    out = pd.DataFrame({"name": d.groupby("athlete_id").name.first(), "n": d.groupby("athlete_id").size(), "mpg": d.groupby("athlete_id")["min"].mean()})
    for s in STATS:
        out[f"rate_{s}"] = d.groupby("athlete_id").apply(lambda g, s=s: g[s].sum() / g["min"].sum(), include_groups=False)
        out[f"share_{s}"] = (d[s] / d[f"{s}_t"].replace(0, np.nan)).groupby(d.athlete_id).mean()
    return out


def project_minutes(avail: list, starters: set, rates: pd.DataFrame) -> dict:
    m0 = {}
    for a in avail:
        base = float(rates.mpg.get(a, DEFAULT_MIN)) if a in rates.index else DEFAULT_MIN
        m0[a] = max(base, STARTER_MIN) if a in starters else min(base, BENCH_MAX)
    keep = sorted(m0, key=lambda a: (a not in starters, -m0[a]))[:ROTATION]
    m0 = {a: (m0[a] if a in keep else 0.0) for a in m0}
    m = dict(m0)
    for _ in range(20):                                                      # rescale to 240 with a per-player cap
        free = [a for a in m if m[a] < MAX_MIN - 1e-9]
        capped = sum(m[a] for a in m if a not in free)
        s = sum(m0[a] for a in free)
        if s <= 0:
            break
        k = (TEAM_MIN - capped) / s
        m = {a: (m0[a] * k if a in free else m[a]) for a in m0}
        over = [a for a in m if m[a] > MAX_MIN]
        if not over:
            break
        for a in over:
            m[a] = MAX_MIN
            m0[a] = MAX_MIN
    return m


def shares(avail: list, minutes: dict, rates: pd.DataFrame, stat: str) -> dict:
    w = {}
    for a in avail:
        r = float(rates[f"rate_{stat}"].get(a, np.nan)) if a in rates.index else np.nan
        w[a] = (r if np.isfinite(r) else float(rates[f"rate_{stat}"].median())) * minutes[a]
    tot = sum(w.values())
    return {a: v / tot for a, v in w.items()}


def roles(avail: list, starters: set, rates: pd.DataFrame) -> dict:
    """{athlete_id: {'min', 'pts', 'ast', 'reb', 'fg3m'}}  — role multipliers vs last season's share when playing."""
    m = project_minutes(avail, starters, rates)
    out = {a: {"min": m[a]} for a in avail}
    for s in STATS:
        sh = shares(avail, m, rates, s)
        for a in avail:
            base = float(rates[f"share_{s}"].get(a, np.nan)) if a in rates.index else np.nan
            out[a][s] = sh[a] / base if np.isfinite(base) and base > 0 else 1.0
            out[a][f"{s}_share"] = sh[a]
    return out
