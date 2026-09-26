#!/usr/bin/env python3
"""
cfb_model.py — college football (FBS) margin/total model from free ESPN schedules
(sportsdataverse-data release `espn_cfb_schedules`, via GitHub — no API key).

  python3 scripts/cfb_model.py "Clemson Tigers" "California Golden Bears" [--spread -1.5 --total 50.5]
  python3 scripts/cfb_model.py --backtest

Ratings: ridge offense/defense on scores (same solver as the NFL feed), last
season as a prior worth PRIOR_GAMES games, walk-forward safe. Backtest
(2022-2025, weeks 2-14, 3,138 games, walk-forward, --backtest reproduces):
  margin MAE 13.68 · residual σ 17.15 · home bias -2.21 · total σ 16.19 ·
  winner accuracy 71.4% · Brier 0.183.
Market lines beat ratings in every sport we backtested, so when a line is known
it gets MARKET_WEIGHT; ratings alone are used only when no line is given.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent))
import nflverse_feed as nf  # noqa: E402  (shared ridge solver)

DATA = Path(__file__).resolve().parent.parent / "data" / "cfb"
URL = ("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
       "espn_cfb_schedules/cfb_schedule_{y}.csv")
FIRST_SEASON = 2019
MAX_AGE_H = 6.0
PRIOR_GAMES = 4.0          # backtest: 2 → MAE 13.80, 4 → 13.68, 6 → 13.70
MIN_CURRENT_GAMES = 30     # league-wide games before the current season is solved at all
UNKNOWN_TEAM = -10.0       # off/def for a team with no FBS history (FCS visitors)
SIGMA_MARGIN = 17.15       # walk-forward residual σ (ratings); kept for blends too (conservative)
SIGMA_TOTAL = 16.19
HOME_BIAS = -2.21          # ratings over-rate home teams by this much (backtest mean residual).
# Out-of-sample check: fit on 2022-23 (-2.18) -> tested 2024-25: mean error -2.24 -> -0.09,
# MAE 13.72 -> 13.56, Brier 0.1819 -> 0.1777. It generalises.
MARKET_WEIGHT = 0.65       # same market share the Judge uses
FAV_TOTAL_RHO = 0.123      # backtest: favourite's margin residual vs total residual (dog cover ~ under)
BACKTEST_GAMES = 3138      # walk-forward games behind the σ, bias and ρ above


def refresh(season: int, max_age_h: float = MAX_AGE_H) -> dict:
    """Download missing seasons; re-pull the current one when older than max_age_h."""
    DATA.mkdir(parents=True, exist_ok=True)
    out = {}
    for y in range(FIRST_SEASON, season + 1):
        p = DATA / f"cfb_schedule_{y}.csv"
        stale = not p.exists() or (y == season and time.time() - p.stat().st_mtime > max_age_h * 3600)
        if stale:
            try:
                urllib.request.urlretrieve(URL.format(y=y), p)
                out[y] = "downloaded"
            except OSError as e:
                out[y] = f"failed: {e}"
    load.cache_clear()
    return out


@lru_cache(maxsize=1)
def load() -> pd.DataFrame:
    frames = [pd.read_csv(p, low_memory=False) for p in sorted(DATA.glob("cfb_schedule_*.csv"))]
    if not frames:
        return pd.DataFrame(columns=["season", "week", "home_team", "away_team", "home_score", "away_score"])
    g = pd.concat(frames, ignore_index=True)
    g = g[(g.status == "STATUS_FINAL") & g.home_score.notna() & (g.season_type == 2)].copy()
    g["location"] = np.where(g.neutral_site.astype(bool), "Neutral", "Home")
    return g


def ratings(season: int, week: int, games: Optional[pd.DataFrame] = None,
            prior_games: float = PRIOR_GAMES) -> dict:
    """Walk-forward: only games before `week` of `season`, last season as the prior."""
    g = load() if games is None else games
    prev = g[g.season == season - 1]
    cur = g[(g.season == season) & (g.week < week)]
    teams = sorted(set(g[g.season >= season - 1].home_team) | set(g[g.season >= season - 1].away_team))
    op, dp, mp, hp = nf._solve(prev, teams)
    use_cur = len(cur) >= MIN_CURRENT_GAMES
    oc, dc, mc, hc = nf._solve(cur, teams) if use_cur else (op, dp, mp, hp)
    n = {t: int(((cur.home_team == t) | (cur.away_team == t)).sum()) if use_cur else 0 for t in teams}
    k = prior_games
    off = {t: (k * op[t] + n[t] * oc[t]) / (k + n[t]) for t in teams}
    dfn = {t: (k * dp[t] + n[t] * dc[t]) / (k + n[t]) for t in teams}
    avg = float(np.mean(list(n.values()))) if n else 0.0
    return {"off": off, "def": dfn, "games": n, "season": season, "through_week": week - 1,
            "mu": (k * mp + avg * mc) / (k + avg), "hfa": (k * hp + avg * hc) / (k + avg)}


def predict(r: dict, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
    """(expected home margin, expected total), home-bias corrected."""
    hfa = 0.0 if neutral else r["hfa"]
    o, d = r["off"], r["def"]
    hp = r["mu"] + hfa / 2 + o.get(home, UNKNOWN_TEAM) - d.get(away, UNKNOWN_TEAM)
    ap = r["mu"] - hfa / 2 + o.get(away, UNKNOWN_TEAM) - d.get(home, UNKNOWN_TEAM)
    return hp - ap + (0.0 if neutral else HOME_BIAS), hp + ap


def current_week(season: int) -> int:
    g = load()
    cur = g[g.season == season]
    return int(cur.week.max()) + 1 if len(cur) else 1


def game_view(home: str, away: str, season: Optional[int] = None, neutral: bool = False,
              market_spread: Optional[float] = None, market_total: Optional[float] = None) -> Optional[dict]:
    """Expected margin/total for one game. market_spread is the HOME line (e.g. -1.5)."""
    g = load()
    if g.empty:
        return None
    season = season or int(g.season.max())
    r = ratings(season, current_week(season), g)
    if home not in r["off"] and away not in r["off"]:
        return None
    rm, rt = predict(r, home, away, neutral)
    mm = -market_spread if market_spread is not None else None
    mu = MARKET_WEIGHT * mm + (1 - MARKET_WEIGHT) * rm if mm is not None else rm
    tot = MARKET_WEIGHT * market_total + (1 - MARKET_WEIGHT) * rt if market_total is not None else rt
    return {"home": home, "away": away, "mu": float(mu), "total": float(tot),
            "ratings_margin": float(rm), "ratings_total": float(rt),
            "market_margin": mm, "market_total": market_total,
            "games_this_season": {home: r["games"].get(home, 0), away: r["games"].get(away, 0)},
            "source": "ratings+market" if mm is not None else "ratings only"}


def p_side(mu: float, line: float, home_side: bool) -> float:
    """P(side covers `line`), line from that side's view (ML = 0). No ties in college (OT)."""
    m = mu if home_side else -mu
    return float(1 - norm.cdf(-line, m, SIGMA_MARGIN))


def p_total(total: float, line: float, over: bool) -> float:
    p = float(1 - norm.cdf(line, total, SIGMA_TOTAL))
    return p if over else 1 - p


def joint_prob(view: dict, legs: list, n_sims: int = 2_000_000, seed: int = 5) -> float:
    """All legs of one game hit together. legs: ("side", home_side, line) | ("total", line, over).
    Margin and total drawn jointly (bivariate normal, measured correlation)."""
    rho = FAV_TOTAL_RHO * (1 if view["mu"] >= 0 else -1)      # home margin vs total
    cov = [[SIGMA_MARGIN ** 2, rho * SIGMA_MARGIN * SIGMA_TOTAL],
           [rho * SIGMA_MARGIN * SIGMA_TOTAL, SIGMA_TOTAL ** 2]]
    m, t = np.random.default_rng(seed).multivariate_normal([view["mu"], view["total"]], cov, n_sims).T
    ok = np.ones(n_sims, bool)
    for leg in legs:
        if leg[0] == "side":
            ok &= ((m if leg[1] else -m) + leg[2]) > 0
        else:
            ok &= (t > leg[1]) if leg[2] else (t < leg[1])
    return float(ok.mean())


def teams() -> set:
    g = load()
    return set(g.home_team) | set(g.away_team)


@lru_cache(maxsize=1)
def market_lines() -> dict:
    """Optional sourced lines: data/cfb/lines.json {"Away @ Home": {"home_spread": -1.5, "total": 50.5}}."""
    p = DATA / "lines.json"
    return json.loads(p.read_text()) if p.exists() else {}


def backtest(seasons=(2022, 2023, 2024, 2025), prior_games: float = PRIOR_GAMES) -> dict:
    g = load()
    rows = []
    for s in seasons:
        for w in range(2, 15):
            test = g[(g.season == s) & (g.week == w)]
            if test.empty:
                continue
            r = ratings(s, w, g, prior_games)
            for x in test.itertuples():
                hm, t = predict(r, x.home_team, x.away_team, bool(x.neutral_site))
                rows.append((hm - (0 if x.neutral_site else HOME_BIAS), t,
                             x.home_score - x.away_score, x.home_score + x.away_score))
    R = pd.DataFrame(rows, columns=["pm", "pt", "m", "t"])
    e, et = R.m - R.pm, R.t - R.pt
    p = norm.cdf(R.pm / e.std())
    return {"games": len(R), "margin_mae": round(float(e.abs().mean()), 2), "sigma": round(float(e.std()), 2),
            "home_bias": round(float(e.mean()), 2), "total_sigma": round(float(et.std()), 2),
            "winner_acc": round(float(((R.pm > 0) == (R.m > 0)).mean()), 3),
            "brier": round(float(((p - (R.m > 0)) ** 2).mean()), 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("home", nargs="?")
    ap.add_argument("away", nargs="?")
    ap.add_argument("--spread", type=float, help="market HOME spread, e.g. -1.5")
    ap.add_argument("--total", type=float)
    ap.add_argument("--neutral", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--backtest", action="store_true")
    a = ap.parse_args()
    if a.refresh:
        print(refresh(int(load().season.max()) if not load().empty else time.gmtime().tm_year), file=sys.stderr)
    if a.backtest:
        print(json.dumps(backtest(), indent=2))
        return 0
    v = game_view(a.home, a.away, neutral=a.neutral, market_spread=a.spread, market_total=a.total)
    if v is None:
        print("unknown teams")
        return 1
    print(json.dumps(v, indent=2))
    print(f"{a.home} wins {p_side(v['mu'], 0, True):.1%} · {a.away} wins {p_side(v['mu'], 0, False):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
