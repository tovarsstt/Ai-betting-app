#!/usr/bin/env python3
"""
soccer_totals_backtest.py — is the soccer goals model biased?

The tennis games-total model turned out to run 1.7-2.2 games long, which cost a
settled bet before anyone measured it (global rule 21). Over/under 2.5 goals is
the same shape of market in the user's number-one sport, priced by the same
family of model, and had never been checked.

WALK-FORWARD, so this is point-in-time honest where the tennis win-prob backtest
was not (rule 22): ratings are refit monthly with `fit_club_ratings.build(as_of=)`,
which sees only matches played BEFORE that month. A game in April is priced by an
April-1 fit, never by a fit that has already watched it.

Reports:
  * mean bias in expected goals (model minus actual) — the level error
  * calibration of P(over) at each line — buckets predicted vs actually landed
  * per-league breakdown, because the 1X2 model already proved league-dependent
    (Premier League has no demonstrated skill; La Liga and Serie A do)

Run: python3 scripts/soccer_totals_backtest.py [--from 2025-11-01]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fit_club_ratings as fcr  # noqa: E402
import soccer_markets as sm  # noqa: E402
from poisson_model import score_matrix  # noqa: E402
from soccer_backtest import load_games, month_starts  # noqa: E402

DEFAULT_FROM = "2025-11-01"
LINES = (1.5, 2.5, 3.5)
CALIB_FILE = Path(__file__).parent.parent / "data" / "soccer" / "totals_calibration.json"


def _lambdas(league: dict, home: str, away: str) -> tuple | None:
    import math
    th, ta = league["teams"].get(home), league["teams"].get(away)
    if not th or not ta or th.get("attack") is None or ta.get("attack") is None:
        return None
    lh = math.exp(league["mu"] + league["home_advantage"] + th["attack"] - ta["defense"])
    la = math.exp(league["mu"] + ta["attack"] - th["defense"])
    return lh, la


def _p_over(lh: float, la: float, line: float) -> float:
    """P(total goals > line) from the same Dixon-Coles matrix the engine prices on."""
    m = score_matrix(lh, la, rho=sm.DEFAULT_RHO)
    p = 0.0
    for i, row in enumerate(m):
        for j, cell in enumerate(row):
            if i + j > line:
                p += cell
    return p


def backtest(start_from: str = DEFAULT_FROM) -> dict:
    games = load_games()
    diffs: list[float] = []
    per_league: dict[str, list] = {}
    # line -> list of (predicted_p_over, actually_over)
    calib: dict[float, list] = {ln: [] for ln in LINES}

    for mstart in month_starts(games, start_from):
        ratings = fcr.build(as_of=date.fromisoformat(mstart))["leagues"]
        month = mstart[:7]
        for g in games:
            if g["date"][:7] != month or g["date"] < start_from:
                continue
            league = ratings.get(g["league"])
            if not league:
                continue
            lam = _lambdas(league, g["home_team"], g["away_team"])
            if lam is None:
                continue
            lh, la = lam
            actual = int(g["home_score"]) + int(g["away_score"])
            expected = lh + la
            diffs.append(expected - actual)
            per_league.setdefault(g["league"], []).append(expected - actual)
            for ln in LINES:
                calib[ln].append((_p_over(lh, la, ln), 1 if actual > ln else 0))

    if not diffs:
        return {"error": "NO_GAMES", "note": f"nothing priced after {start_from}"}

    bias = statistics.fmean(diffs)
    lines_out = {}
    for ln, pairs in calib.items():
        if not pairs:
            continue
        pred = statistics.fmean(p for p, _ in pairs)
        act = statistics.fmean(o for _, o in pairs)
        n = len(pairs)
        se = (pred * (1 - pred) / n) ** 0.5
        z = (pred - act) / se if se else 0.0
        lines_out[str(ln)] = {
            "n": n,
            "predicted_over": round(pred, 4),
            "actual_over": round(act, 4),
            "gap": round(pred - act, 4),
            "z": round(z, 2),
            "significant": abs(z) > 1.96,
        }

    return {
        "window_from": start_from,
        "n_games": len(diffs),
        # Positive bias = the model expects MORE goals than are scored.
        "mean_bias_goals": round(bias, 4),
        "median_bias_goals": round(statistics.median(diffs), 4),
        "mae_goals": round(statistics.fmean(abs(d) for d in diffs), 3),
        # Per-league bias WITH significance. Five leagues means five more tests
        # on top of the three lines, so the bar is Bonferroni-corrected across
        # all eight — otherwise the largest of five noisy means always "looks"
        # like a finding. (Ligue 1 reads +0.24 goals, z=2.2: nominally
        # interesting, nowhere near enough to move a price.)
        "per_league_bias": {
            lg: (lambda v, sd, se: {
                "n": len(v),
                "bias": round(statistics.fmean(v), 4),
                "z": round(statistics.fmean(v) / se, 2) if se else 0.0,
                "significant_corrected": (abs(statistics.fmean(v) / se) > 2.73
                                          if se else False),
            })(v, statistics.pstdev(v), statistics.pstdev(v) / (len(v) ** 0.5))
            for lg, v in sorted(per_league.items()) if len(v) > 1},
        "multiple_comparisons": {
            "tests": 8,
            "bonferroni_z": 2.73,
            "note": "3 total lines + 5 leagues; a per-test z is not enough to "
                    "justify moving prices",
        },
        "over_lines": lines_out,
        "verdict": ("model expects MORE goals than are scored — overs will lose"
                    if bias > 0.15 else
                    "model expects FEWER goals than are scored — unders will lose"
                    if bias < -0.15 else
                    "no material goals bias"),
        "method": "walk-forward monthly refits (as_of) — no lookahead",
    }


def fit_calibration(start_from: str = DEFAULT_FROM,
                    path: Path = CALIB_FILE) -> dict:
    """Persist the goals offset ONLY when it is both material and significant."""
    r = backtest(start_from)
    if "error" in r:
        return r
    bias = r["mean_bias_goals"]
    # Significance on the 2.5 line, the one actually bet.
    main = r["over_lines"].get("2.5", {})
    justified = abs(bias) > 0.15 and main.get("significant", False)
    out = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "window_from": start_from,
        "n_games": r["n_games"],
        "measured_bias_goals": bias,
        "offset_goals": round(-bias, 4) if justified else 0.0,
        "applied": justified,
        "why": ("bias is material (>0.15 goals) and the 2.5 line is significant"
                if justified else
                "bias is immaterial or not statistically significant — no "
                "correction applied, deliberately"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_FROM)
    ap.add_argument("--fit", action="store_true",
                    help="fit + persist the goals offset (only if justified)")
    a = ap.parse_args()
    print(json.dumps(fit_calibration(a.start) if a.fit else backtest(a.start), indent=1))
