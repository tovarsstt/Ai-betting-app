"""Live in-play soccer pricing: time-decayed Poisson offset by the current score.

Implements the LIVE / IN-PLAY DISCIPLINE from skills/betting/soccer_skill.md:
the pre-match model expires at kickoff; the only honest live fair price is
remaining-lambda = pre-match lambda x (minutes left / total), rebuild the score
matrix and offset by the current score. Analytic (no Monte Carlo needed).

Usage:
    from soccer_live import lambdas_from_ratings, live_probs
    lam_h, lam_a = lambdas_from_ratings("Serie A", "Lecce", "Roma")
    live_probs(lam_h, lam_a, minute=21, score_home=0, score_away=1)
"""
from __future__ import annotations

import json
import math
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CLUB_RATINGS = os.path.join(DATA_DIR, "soccer", "club_ratings.json")

REGULATION_MIN = 90
STOPPAGE_MIN = 5  # FIFA-era average added time, both halves combined effect
MAX_GOALS = 12


def lambdas_from_ratings(league: str, home: str, away: str) -> tuple[float, float]:
    """Pre-match lambdas from the fitted per-league Poisson ratings.

    Raises KeyError on any name miss — an alias miss must never fall through
    to a silent heuristic price (reference_club_name_aliases lesson).
    """
    with open(CLUB_RATINGS) as f:
        leagues = json.load(f)["leagues"]
    pool_name = RATINGS_POOL.get(league, league)
    if pool_name not in leagues:
        raise KeyError(f"league not fitted: {pool_name!r} (have {sorted(leagues)})")
    lg = leagues[pool_name]
    teams = lg["teams"]
    missing = [t for t in (home, away) if t not in teams]
    if missing:
        raise KeyError(f"team(s) not in {league} ratings: {missing}")
    lam_h = math.exp(lg["mu"] + lg["home_advantage"] + teams[home]["attack"] - teams[away]["defense"])
    lam_a = math.exp(lg["mu"] + teams[away]["attack"] - teams[home]["defense"])
    return lam_h, lam_a


def _poisson_pmf(lam: float, kmax: int) -> list[float]:
    pmf = [math.exp(-lam)]
    for k in range(1, kmax + 1):
        pmf.append(pmf[-1] * lam / k)
    return pmf


def live_probs(
    lam_home_full: float,
    lam_away_full: float,
    minute: int,
    score_home: int,
    score_away: int,
    stoppage_min: int = STOPPAGE_MIN,
) -> dict[str, float]:
    """Full-time market probabilities conditioned on the live state."""
    if minute < 0 or score_home < 0 or score_away < 0:
        raise ValueError("minute and scores must be non-negative")
    total = REGULATION_MIN + stoppage_min
    frac_left = max(0.0, (total - minute) / total)
    lam_h = lam_home_full * frac_left
    lam_a = lam_away_full * frac_left

    pmf_h = _poisson_pmf(lam_h, MAX_GOALS)
    pmf_a = _poisson_pmf(lam_a, MAX_GOALS)

    p_home = p_draw = p_away = 0.0
    p_away_m15 = 0.0  # away -1.5 handicap
    p_home_m15 = 0.0
    over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    p_btts = 0.0
    for i, ph in enumerate(pmf_h):
        for j, pa in enumerate(pmf_a):
            p = ph * pa
            gh, ga = score_home + i, score_away + j
            if gh > ga:
                p_home += p
                if gh - ga >= 2:
                    p_home_m15 += p
            elif gh == ga:
                p_draw += p
            else:
                p_away += p
                if ga - gh >= 2:
                    p_away_m15 += p
            tot_goals = gh + ga
            for line in over:
                if tot_goals > line:
                    over[line] += p
            if gh >= 1 and ga >= 1:
                p_btts += p

    # renormalize the truncated matrix
    mass = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / mass, p_draw / mass, p_away / mass

    no_push = 1.0 - p_draw
    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "home_dnb": p_home / no_push if no_push > 0 else 0.0,
        "away_dnb": p_away / no_push if no_push > 0 else 0.0,
        "home_dc": p_home + p_draw,   # 1X
        "away_dc": p_away + p_draw,   # X2
        "home_minus_1_5": p_home_m15 / mass,
        "away_minus_1_5": p_away_m15 / mass,
        "over_1_5": min(1.0, over[1.5] / mass),
        "over_2_5": min(1.0, over[2.5] / mass),
        "over_3_5": min(1.0, over[3.5] / mass),
        "under_2_5": max(0.0, 1.0 - over[2.5] / mass),
        "under_3_5": max(0.0, 1.0 - over[3.5] / mass),
        "btts": min(1.0, p_btts / mass),
        "exp_goals_remaining": lam_h + lam_a,
        "minute": float(minute),
        "frac_left": frac_left,
    }


BASELINE_SOT_PER_MIN = 0.09   # ~8.5 combined shots-on-target per 95 min
TEMPO_PRIOR_MIN = 90          # shrinkage: prior worth 90 min of baseline
TEMPO_FLOOR, TEMPO_CEIL = 0.7, 1.5


def tempo_multiplier(total_sot: int, minute: int) -> float:
    """Bounded run-of-play multiplier for remaining lambdas.

    Shrinks the observed combined shots-on-target rate toward the league
    baseline (prior worth TEMPO_PRIOR_MIN minutes) so early-game noise can't
    explode the estimate; clamped to [0.7, 1.5].
    """
    if minute <= 0:
        return 1.0
    expected = BASELINE_SOT_PER_MIN * (minute + TEMPO_PRIOR_MIN)
    observed = total_sot + BASELINE_SOT_PER_MIN * TEMPO_PRIOR_MIN
    return min(TEMPO_CEIL, max(TEMPO_FLOOR, observed / expected))


def asian_ev(pmf: dict[int, float], line: float, price: float, side: str) -> float:
    """EV per unit staked for an asian total/handicap line vs an integer pmf.

    pmf maps final integer outcome (total goals, or signed margin) -> prob.
    Quarter lines (x.25 / x.75) split into the two adjacent half-lines, so
    over X.25 half-LOSES on exactly X and over X.75 half-WINS on exactly X+1.
    """
    if side not in ("over", "under"):
        raise ValueError(f"side must be 'over' or 'under', got {side!r}")

    def half_ev(sub_line: float) -> float:
        if side == "over":
            p_win = sum(p for k, p in pmf.items() if k > sub_line)
        else:
            p_win = sum(p for k, p in pmf.items() if k < sub_line)
        p_push = sum(p for k, p in pmf.items() if k == sub_line)
        p_lose = 1.0 - p_win - p_push
        return p_win * (price - 1.0) - p_lose

    if round(line * 4) % 2 == 1:  # quarter line
        return 0.5 * half_ev(line - 0.25) + 0.5 * half_ev(line + 0.25)
    return half_ev(line)


def asian_handicap_ev(margin_pmf: dict[int, float], handicap: float, price: float) -> float:
    """EV for backing a team at an asian handicap (e.g. -3.25) at `price`.

    margin_pmf maps final (team goals - opponent goals) -> prob. The bet wins
    when margin + handicap > 0, so it is `asian_ev` with line = -handicap.
    """
    return asian_ev(margin_pmf, -handicap, price, "over")


def total_pmf(
    lam_home_full: float,
    lam_away_full: float,
    minute: int,
    score_home: int,
    score_away: int,
    tempo_mult: float = 1.0,
    stoppage_min: int = STOPPAGE_MIN,
) -> tuple[dict[int, float], dict[int, float]]:
    """(total-goals pmf, home-minus-away margin pmf) conditioned on live state."""
    frac_left = max(0.0, (REGULATION_MIN + stoppage_min - minute) / (REGULATION_MIN + stoppage_min))
    pmf_h = _poisson_pmf(lam_home_full * frac_left * tempo_mult, MAX_GOALS)
    pmf_a = _poisson_pmf(lam_away_full * frac_left * tempo_mult, MAX_GOALS)
    totals: dict[int, float] = {}
    margins: dict[int, float] = {}
    for i, ph in enumerate(pmf_h):
        for j, pa in enumerate(pmf_a):
            p = ph * pa
            gh, ga = score_home + i, score_away + j
            totals[gh + ga] = totals.get(gh + ga, 0.0) + p
            margins[gh - ga] = margins.get(gh - ga, 0.0) + p
    return totals, margins


def ever_leads_prob(
    lam_home_full: float,
    lam_away_full: float,
    by: int = 1,
    minute: int = 0,
    score_home: int = 0,
    score_away: int = 0,
    n_sims: int = 60_000,
    seed: int = 0,
    stoppage_min: int = STOPPAGE_MIN,
) -> float:
    """P(home team's lead reaches `by` at ANY point) — the 1UP / 2UP markets.

    Stake's "1x2 (1UP)" pays the moment your side goes a goal ahead, even if
    the match is later drawn or lost, so it CANNOT be read off the final-score
    matrix. Simulated as two independent Poisson processes over the remaining
    clock, tracking the running lead.
    """
    if by < 1:
        raise ValueError("by must be at least 1")
    if score_home - score_away >= by:
        return 1.0
    total = REGULATION_MIN + stoppage_min
    frac_left = max(0.0, (total - minute) / total)
    if frac_left <= 0.0:
        return 0.0

    import random

    rng = random.Random(seed)
    lam_h = lam_home_full * frac_left
    lam_a = lam_away_full * frac_left
    hits = 0
    for _ in range(n_sims):
        # goal counts then uniform arrival times: equivalent to the process,
        # far cheaper than stepping minute by minute
        n_h = _poisson_draw(rng, lam_h)
        n_a = _poisson_draw(rng, lam_a)
        if n_h == 0:
            continue  # cannot extend a lead without scoring
        events = [(rng.random(), 1) for _ in range(n_h)] + [(rng.random(), -1) for _ in range(n_a)]
        events.sort()
        lead = score_home - score_away
        for _, delta in events:
            lead += delta
            if lead >= by:
                hits += 1
                break
    return hits / n_sims


def _poisson_draw(rng, lam: float) -> int:
    """Knuth sampler — small lambdas here, so the loop is short."""
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def lambdas_from_market(p_home: float, p_draw: float, p_away: float) -> tuple[float, float]:
    """Back out (lambda_home, lambda_away) that reproduce devigged 1X2 probs.

    For a match where one side is missing from the fitted ratings, the market
    is the only honest source — this converts its 1X2 into the goal rates the
    rest of the engine needs, instead of inventing a rating.
    """
    total = p_home + p_draw + p_away
    if abs(total - 1.0) > 0.02:
        raise ValueError(f"probs must be devigged and sum to 1 (got {total:.3f})")

    def probs(lh: float, la: float) -> tuple[float, float, float]:
        p = live_probs(lh, la, 0, 0, 0)
        return p["home"], p["draw"], p["away"]

    # 2-D bisection on (total goals, goal difference): both are monotone in
    # the pair, so a coarse grid + refinement converges quickly and reliably.
    best, best_err = (1.3, 1.3), 9.9
    for tot in [x / 10 for x in range(15, 45)]:          # 1.5 – 4.4 expected goals
        for share in [x / 100 for x in range(20, 81)]:   # home's share of them
            lh, la = tot * share, tot * (1 - share)
            ph, pd, pa = probs(lh, la)
            err = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
            if err < best_err:
                best, best_err = (lh, la), err
    return best


ESPN_LEAGUE_CODES = {
    "Serie A": "ita.1",
    "Premier League": "eng.1",
    "La Liga": "esp.1",
    "Bundesliga": "ger.1",
    "Ligue 1": "fra.1",
    "Champions League": "uefa.champions",
    "Europa League": "uefa.europa",
}
# UEFA cup matches cross leagues, so they price off the pooled "Europe" fit
# (anchored by real cross-league results — see fit_club_ratings.py).
RATINGS_POOL = {
    "Champions League": "Europe",
    "Europa League": "Europe",
}


def fetch_live_state(league: str, team_hint: str) -> dict[str, object]:
    """Live minute / score / shots-on-target for the match containing team_hint.

    Free ESPN endpoints only (default urllib UA — ESPN 403s Mozilla UAs).
    Raises KeyError when the league has no ESPN code, LookupError when no
    match on today's board contains team_hint.
    """
    import urllib.request

    code = ESPN_LEAGUE_CODES.get(league)
    if code is None:
        raise KeyError(f"no ESPN code for league {league!r}")
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}"
    with urllib.request.urlopen(urllib.request.Request(f"{base}/scoreboard"), timeout=10) as r:
        board = json.load(r)
    events = [e for e in board.get("events", []) if team_hint.lower() in e["name"].lower()]
    if not events:
        raise LookupError(f"no live/scheduled match for {team_hint!r} in {league}")
    ev = events[0]
    comp = ev["competitions"][0]
    clock = str(ev["status"].get("displayClock", "0'")).replace("'", "")
    try:
        minute = int(clock.split("+")[0])
    except ValueError:
        minute = 0
    scores = {c["homeAway"]: int(c.get("score", 0) or 0) for c in comp["competitors"]}
    total_sot = None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{base}/summary?event={ev['id']}"), timeout=10
        ) as r:
            summary = json.load(r)
        sot = 0
        for team in summary.get("boxscore", {}).get("teams", []):
            for stat in team.get("statistics", []):
                if stat.get("name") == "shotsOnTarget":
                    sot += int(float(stat.get("displayValue", 0)))
        total_sot = sot
    except Exception:
        pass  # stats feed is best-effort; pricing works without it
    return {
        "minute": minute,
        "score_home": scores.get("home", 0),
        "score_away": scores.get("away", 0),
        "total_sot": total_sot,
        "status": ev["status"]["type"]["description"],
        "event_name": ev["name"],
    }


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Live soccer fair probs (time-decayed Poisson)")
    ap.add_argument("league")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--minute", type=int, required=True)
    ap.add_argument("--score", required=True, help="home-away, e.g. 0-1")
    args = ap.parse_args()
    sh, sa = (int(x) for x in args.score.split("-"))
    lam_h, lam_a = lambdas_from_ratings(args.league, args.home, args.away)
    probs = live_probs(lam_h, lam_a, args.minute, sh, sa)
    print(json.dumps(probs, indent=2))


if __name__ == "__main__":
    _main()
