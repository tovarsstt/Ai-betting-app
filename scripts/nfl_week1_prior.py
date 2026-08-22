#!/usr/bin/env python3
"""
nfl_week1_prior.py — usable NFL ratings for Week 1, when no current-season games exist.

The problem this solves is a genuine catch-22, not a data gap. The freshness gate
(rule 16) caps every NFL pick at LEAN while the ratings predate the season start.
On Week 1 there ARE no current-season games, so that condition can never clear —
the engine would be least useful in exactly the week it is most wanted.

Carrying last season's ratings forward untouched is the wrong answer: teams
revert, and last year's edge over-predicts this year's margin. So MEASURE by how
much, and shrink.

MEASURED, not assumed. Regressing early-2025 game margins on the 2024 end-of-
season net-rating gap (n=70 games, the first ~4 weeks):

    margin = +4.53 + 0.664 x (prior-season net rating gap)     residual sd 12.2

So a prior-season edge is worth about **two thirds** of face value in September,
and the spread around it is a little wider than mid-season (12.2 vs ~11.5). Both
numbers are applied below.

⚠️ HONEST LIMIT: that coefficient rests on ONE season transition, 70 games. It is
a far better estimate than 1.0 (carry forward whole) or 0.0 (ignore the past),
and it is not precise. Re-run `--fit` after each season to accumulate transitions;
until then treat the shrinkage as directionally right, not exact.

ROSTER CHURN widens the uncertainty on top: a team that turned over a lot of its
roster, or changed its QB room, is less well described by last year than a team
that returned intact. Churn does not move the rating's DIRECTION — we have no
measurement saying churn is good or bad — it only shrinks confidence toward the
league mean, which is the honest response to knowing less.

Run:  python3 scripts/nfl_week1_prior.py --fit       (measure + write the prior)
      python3 scripts/nfl_week1_prior.py             (show it)
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent.parent / "data"
PERIOD = DATA / "period_scores.json"
CHURN = DATA / "nfl_roster_changes.json"
OUT = DATA / "nfl_week1_prior.json"

MIN_GAMES = 8          # below this a team's prior-season rating is too thin
# Extra shrink for a roster that turned over. Capped: churn tells us we know
# less, never that a team got worse.
CHURN_MAX_EXTRA_SHRINK = 0.15
QB_CHANGE_EXTRA_SHRINK = 0.08


def _season(date_str: str) -> int:
    y, m = int(date_str[:4]), int(date_str[5:7])
    return y if m >= 8 else y - 1


def load_games() -> dict[int, list]:
    try:
        games = json.loads(PERIOD.read_text())["nfl"]["games"]
    except (FileNotFoundError, OSError, KeyError, json.JSONDecodeError):
        return {}
    by: dict[int, list] = defaultdict(list)
    for g in games:
        by[_season(g["date"])].append(g)
    return by


def net_ratings(games: list) -> dict[str, float]:
    """Points-per-game differential per team — the prior-season strength."""
    pf, pa, n = defaultdict(float), defaultdict(float), defaultdict(int)
    for g in games:
        h, a = sum(g["home_periods"]), sum(g["away_periods"])
        pf[g["home"]] += h; pa[g["home"]] += a; n[g["home"]] += 1
        pf[g["away"]] += a; pa[g["away"]] += h; n[g["away"]] += 1
    return {t: round((pf[t] - pa[t]) / n[t], 3) for t in n if n[t] >= MIN_GAMES}


def measure_shrinkage(by_season: dict[int, list]) -> Optional[dict]:
    """Fit `margin ~ a + b * prior_gap` on each season's opening weeks.

    b IS the shrinkage: how much of last season's edge actually shows up.
    """
    seasons = sorted(by_season)
    xs, ys, used = [], [], []
    for prev, cur in zip(seasons, seasons[1:]):
        prior = net_ratings(by_season[prev])
        early = sorted(by_season[cur], key=lambda g: g["date"])[:70]
        pairs = [(prior[g["home"]] - prior[g["away"]],
                  sum(g["home_periods"]) - sum(g["away_periods"]))
                 for g in early
                 if g["home"] in prior and g["away"] in prior]
        if len(pairs) < 30:
            continue
        xs += [p[0] for p in pairs]
        ys += [p[1] for p in pairs]
        used.append(f"{prev}->{cur}")
    if len(xs) < 30:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 0:
        return None
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    alpha = my - beta * mx
    resid = statistics.pstdev([y - (alpha + beta * x) for x, y in zip(xs, ys)])
    return {"shrinkage": round(beta, 4), "home_advantage": round(alpha, 2),
            "sigma": round(resid, 2), "n_games": len(xs), "transitions": used}


def _churn_by_team() -> dict[str, dict]:
    """Total roster churn and QB movement since the last snapshot chain."""
    try:
        diffs = json.loads(CHURN.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    agg: dict[str, dict] = defaultdict(lambda: {"churn": 0.0, "qb_changed": False})
    for d in diffs if isinstance(diffs, list) else [diffs]:
        for team, rec in (d.get("teams") or {}).items():
            agg[team]["churn"] += float(rec.get("churn_share") or 0.0)
            if rec.get("qb_changes"):
                agg[team]["qb_changed"] = True
    return dict(agg)


def build(season: Optional[int] = None) -> dict:
    by = load_games()
    if not by:
        return {"error": "NO_DATA", "note": "run fetch_period_scores.py --sport nfl"}
    prev = max(by) if season is None else season
    prior = net_ratings(by[prev])
    if not prior:
        return {"error": "NO_PRIOR_SEASON", "season": prev}

    fit = measure_shrinkage(by)
    if fit is None:
        # Refuse to invent a coefficient — two seasons of games are needed to
        # measure one transition, and a guessed shrinkage is the whole problem.
        return {"error": "CANNOT_MEASURE_SHRINKAGE",
                "note": "need two consecutive seasons of results; fetch another "
                        "season with fetch_period_scores.py --seasons"}

    churn = _churn_by_team()
    league_mean = statistics.fmean(prior.values())
    teams = {}
    for t, r in prior.items():
        c = churn.get(t, {})
        extra = min(float(c.get("churn", 0.0)), 1.0) * CHURN_MAX_EXTRA_SHRINK
        if c.get("qb_changed"):
            extra += QB_CHANGE_EXTRA_SHRINK
        k = max(0.25, fit["shrinkage"] - extra)   # never shrink past a floor
        teams[t] = {
            "prior_net": r,
            "shrink_applied": round(k, 4),
            # Shrunk toward the league mean, which is what "we know less" means.
            "week1_net": round(league_mean + k * (r - league_mean), 3),
            "roster_churn": round(float(c.get("churn", 0.0)), 3),
            "qb_room_changed": bool(c.get("qb_changed")),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prior_season": prev,
        "league_mean_net": round(league_mean, 3),
        "measured": fit,
        "sigma_week1": fit["sigma"],
        "teams": teams,
        "caveat": (f"shrinkage {fit['shrinkage']} measured on {fit['n_games']} "
                   f"games across {len(fit['transitions'])} season transition(s) "
                   f"({', '.join(fit['transitions'])}) — directionally right, not "
                   f"precise. Churn only widens uncertainty; it never says a team "
                   f"got better or worse."),
        "method": "prior-season net rating shrunk toward the league mean by a "
                  "MEASURED early-season regression, plus extra shrink for "
                  "roster churn and QB-room change",
    }


def load_prior() -> Optional[dict]:
    try:
        return json.loads(OUT.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def week1_net(team: str, prior: Optional[dict] = None) -> Optional[float]:
    """Week-1 net rating for a team, or None when it has no prior."""
    prior = prior or load_prior()
    rec = ((prior or {}).get("teams") or {}).get(team)
    return rec["week1_net"] if rec else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true", help="rebuild and persist")
    a = ap.parse_args()
    if a.fit:
        out = build()
        if "error" not in out:
            OUT.write_text(json.dumps(out, indent=1))
        print(json.dumps({k: v for k, v in out.items() if k != "teams"}, indent=1))
    else:
        p = load_prior() or {}
        print(json.dumps({k: v for k, v in p.items() if k != "teams"}, indent=1))
