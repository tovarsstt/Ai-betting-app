"""
Soccer markets engine — Caveman Locks.

Pure math, no network. Given two Poisson scoring rates (lambda_home,
lambda_away) it builds the full bivariate score matrix and derives EVERY
soccer market exactly from it:

    1X2 (home / draw / away)
    Double Chance  — 1X (gana o empata), X2, 12
    Draw No Bet    — apuesta sin empate (draw refunded)
    Over/Under totals (any line)
    BTTS (both teams to score)
    Corners (heuristic — flagged, derived from attacking volume)

Why this exists: the old /predict path devigged soccer as a 2-way market
(home vs away) and never modelled the draw. A "team to WIN" pick then died
on any draw (e.g. Canada). With the full score matrix the draw is priced
explicitly, so we can offer draw-insured markets (DC / DNB) with real edge.

Low-score / draw calibration uses the Dixon-Coles (1997) tau correction so
0-0 and 1-1 are not under-counted by independent Poisson.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

MAX_GOALS = 10
DEFAULT_RHO = -0.13  # Dixon-Coles low-score correction (typical fitted value)


# ── Score matrix ────────────────────────────────────────────────────────────
def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _dc_tau(hg: int, ag: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles adjustment for the four low-score cells; 1.0 elsewhere."""
    if hg == 0 and ag == 0:
        return 1.0 - lh * la * rho
    if hg == 0 and ag == 1:
        return 1.0 + lh * rho
    if hg == 1 and ag == 0:
        return 1.0 + la * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def _poisson_vector(lam: float, n: int) -> list[float]:
    return [_poisson_pmf(k, lam) for k in range(n + 1)]


def _wld_from_vectors(ph: list[float], pa: list[float]) -> tuple[float, float, float]:
    """Win/draw/loss from two independent Poisson goal vectors (no DC — fast)."""
    home = draw = away = 0.0
    for i, pi in enumerate(ph):
        for j, pj in enumerate(pa):
            p = pi * pj
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def solve_lambdas_from_1x2(
    p_home: float,
    p_draw: float,
    p_away: float,
    max_goals: int = MAX_GOALS,
) -> tuple[float, float, float]:
    """
    Fit (lambda_home, lambda_away) whose Poisson score matrix reproduces the
    devigged 1X2 probabilities. This calibrates the goal model to the SHARP
    MARKET, so every derived market (totals, BTTS, correct score, team totals)
    is consistent with the price the market set — instead of relying on the
    unreliable national-team ratings. Returns (lh, la, residual).

    Coarse grid → local refine. Objective fits home & away win (draw falls out).
    Plain independent Poisson is used for the fit (the Dixon-Coles draw nudge is
    applied later when the final board is built; it barely moves home/away win).
    """
    coarse = [round(0.10 + 0.05 * k, 3) for k in range(69)]  # 0.10 … 3.50
    vecs = {lam: _poisson_vector(lam, max_goals) for lam in coarse}

    def err(lh_vec: list[float], la_vec: list[float]) -> float:
        h, _, a = _wld_from_vectors(lh_vec, la_vec)
        return (h - p_home) ** 2 + (a - p_away) ** 2

    best = (1e9, 1.3, 1.0)
    for lh in coarse:
        ph = vecs[lh]
        for la in coarse:
            e = err(ph, vecs[la])
            if e < best[0]:
                best = (e, lh, la)

    _, lh0, la0 = best
    fine_h = [round(max(0.05, lh0 - 0.05) + 0.01 * k, 3) for k in range(11)]
    fine_a = [round(max(0.05, la0 - 0.05) + 0.01 * k, 3) for k in range(11)]
    for lh in fine_h:
        ph = _poisson_vector(lh, max_goals)
        for la in fine_a:
            e = err(ph, _poisson_vector(la, max_goals))
            if e < best[0]:
                best = (e, lh, la)

    return best[1], best[2], best[0] ** 0.5


def score_matrix(
    lh: float, la: float, max_goals: int = MAX_GOALS, rho: float = DEFAULT_RHO
) -> list[list[float]]:
    """P(home=i, away=j) for i,j in [0, max_goals], renormalized to sum to 1."""
    matrix = [
        [
            _poisson_pmf(i, lh) * _poisson_pmf(j, la) * _dc_tau(i, j, lh, la, rho)
            for j in range(max_goals + 1)
        ]
        for i in range(max_goals + 1)
    ]
    total = sum(cell for row in matrix for cell in row)
    if total <= 0:
        return matrix
    return [[cell / total for cell in row] for row in matrix]


# ── Market probabilities (all derived from the matrix) ────────────────────────
@dataclass(frozen=True)
class MarketBook:
    """Model probabilities for every supported market. Home perspective."""
    home_win: float
    draw: float
    away_win: float
    dc_home_draw: float   # 1X — home win or draw (gana o empata, home)
    dc_away_draw: float   # X2 — away win or draw (gana o empata, away)
    dc_home_away: float   # 12 — no draw
    dnb_home: float       # home, draw refunded (apuesta sin empate)
    dnb_away: float       # away, draw refunded
    btts_yes: float
    btts_no: float
    over_under: dict[float, dict[str, float]]  # line -> {"over","under"}
    expected_total_goals: float


def derive_markets(
    matrix: list[list[float]],
    total_lines: tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5),
) -> MarketBook:
    home_win = draw = away_win = btts_yes = 0.0
    exp_goals = 0.0
    n = len(matrix)
    over = {ln: 0.0 for ln in total_lines}

    for i in range(n):
        for j in range(n):
            p = matrix[i][j]
            if p <= 0:
                continue
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            if i >= 1 and j >= 1:
                btts_yes += p
            exp_goals += p * (i + j)
            for ln in total_lines:
                if (i + j) > ln:
                    over[ln] += p

    no_draw = home_win + away_win
    return MarketBook(
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        dc_home_draw=home_win + draw,
        dc_away_draw=away_win + draw,
        dc_home_away=no_draw,
        dnb_home=home_win / no_draw if no_draw > 0 else 0.0,
        dnb_away=away_win / no_draw if no_draw > 0 else 0.0,
        btts_yes=btts_yes,
        btts_no=1.0 - btts_yes,
        over_under={
            ln: {"over": over[ln], "under": 1.0 - over[ln]} for ln in total_lines
        },
        expected_total_goals=exp_goals,
    )


# ── Odds helpers ──────────────────────────────────────────────────────────────
def american_to_decimal(odds: float) -> float:
    if odds >= 0:
        return odds / 100.0 + 1.0
    return 100.0 / abs(odds) + 1.0


def decimal_to_american(dec: float) -> int:
    if dec <= 1.0:
        return 0
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def fair_odds(prob: float) -> dict:
    """Fair (vig-free) price for a model probability."""
    if prob <= 0:
        return {"decimal": None, "american": None}
    dec = 1.0 / prob
    return {"decimal": round(dec, 3), "american": decimal_to_american(dec)}


def devig_3way(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    """Proportional devig of a 3-way market into fair probabilities."""
    raw = [
        1.0 / american_to_decimal(home_odds),
        1.0 / american_to_decimal(draw_odds),
        1.0 / american_to_decimal(away_odds),
    ]
    overround = sum(raw)
    if overround <= 0:
        return {"home": 0.0, "draw": 0.0, "away": 0.0, "vig_pct": 0.0}
    return {
        "home": raw[0] / overround,
        "draw": raw[1] / overround,
        "away": raw[2] / overround,
        "vig_pct": round((overround - 1.0) * 100, 2),
    }


def ev_pct(model_prob: float, american_odds: float) -> float:
    """Expected value as a fraction of stake for a 1-unit bet."""
    dec = american_to_decimal(american_odds)
    return round(model_prob * (dec - 1.0) - (1.0 - model_prob), 4)


# ── Corners (heuristic — NOT from goal matrix; flagged honestly) ──────────────
def estimate_corners(lh: float, la: float) -> dict:
    """
    Heuristic team-corner expectation from attacking volume. We have no corner
    data in ratings, so this is a documented proxy (corners track attacking
    lambda), NOT a calibrated stat. League-average team corners ~5.0 at an
    attacking lambda of ~1.4 goals.
    """
    CORNERS_PER_GOAL_LAMBDA = 5.0 / 1.4
    ch = lh * CORNERS_PER_GOAL_LAMBDA
    ca = la * CORNERS_PER_GOAL_LAMBDA
    total_lambda = ch + ca

    def over_line(line: float) -> float:
        # Total corners ~ Poisson(total_lambda); P(total > line)
        floor = math.floor(line)
        cdf = sum(_poisson_pmf(k, total_lambda) for k in range(floor + 1))
        return round(1.0 - cdf, 4)

    return {
        "method": "heuristic_from_attack",
        "expected_total_corners": round(total_lambda, 1),
        "lines": {
            "8.5": {"over": over_line(8.5), "under": round(1 - over_line(8.5), 4)},
            "9.5": {"over": over_line(9.5), "under": round(1 - over_line(9.5), 4)},
            "10.5": {"over": over_line(10.5), "under": round(1 - over_line(10.5), 4)},
        },
        "note": "no corner data in ratings — proxy only, do not present as a hard stat",
    }


# ── Recommendation: draw-insurance over straight win ──────────────────────────
# The Canada lesson: a "better" team that doesn't WIN still loses a straight
# Win/ML ticket on a draw. When the favorite is better but not dominant and the
# draw is live, the draw-insured markets (Double Chance, Draw No Bet) keep the
# read alive. Ranking obeys CLAUDE.md: win-probability first, edge second.
STRONG_FAV_WIN = 0.60   # at/above this, straight Win/ML is the play
MATERIAL_DRAW = 0.26    # draw this likely = live risk, prefer Double Chance
TIGHT_MARGIN = 0.12     # |p_win - p_lose| below this + high draw = Draw No Bet
MIN_VALUE_EV = 0.02     # EV floor to call a straight-win ticket "value"


@dataclass(frozen=True)
class MarketOdds:
    """Optional book prices (American). None = unknown, edge not computed."""
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None
    dc_home_draw: Optional[float] = None
    dc_away_draw: Optional[float] = None
    dnb_home: Optional[float] = None
    dnb_away: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None


def _pick(label: str, side: str, prob: float, odds: Optional[float], why: str) -> dict:
    out = {
        "market": label,
        "side": side,
        "model_prob": round(prob, 4),
        "fair_odds": fair_odds(prob),
        "rationale": why,
    }
    if odds is not None:
        out["book_odds_american"] = odds
        out["ev_pct"] = round(ev_pct(prob, odds) * 100, 2)
        out["value"] = out["ev_pct"] > 0
    return out


def recommend(
    book: MarketBook,
    home_team: str,
    away_team: str,
    odds: Optional[MarketOdds] = None,
) -> dict:
    """
    Pick the best market for the favourite, preferring draw-insured plays when
    the draw is live. Returns a primary pick, a higher-payout value alternative
    (straight win, only if it has real EV), plus totals and BTTS leans.
    """
    odds = odds or MarketOdds()
    home_is_fav = book.home_win >= book.away_win
    fav = home_team if home_is_fav else away_team
    dog = away_team if home_is_fav else home_team

    p_win = book.home_win if home_is_fav else book.away_win
    p_lose = book.away_win if home_is_fav else book.home_win
    p_draw = book.draw
    p_dc = book.dc_home_draw if home_is_fav else book.dc_away_draw   # 1X / X2
    p_dnb = book.dnb_home if home_is_fav else book.dnb_away
    o_win = odds.home if home_is_fav else odds.away
    o_dc = odds.dc_home_draw if home_is_fav else odds.dc_away_draw
    o_dnb = odds.dnb_home if home_is_fav else odds.dnb_away

    win_ev = ev_pct(p_win, o_win) if o_win is not None else None

    # ── Decision tree ────────────────────────────────────────────────────────
    if p_win >= STRONG_FAV_WIN:
        primary = _pick(
            "Win (ML)", fav, p_win, o_win,
            f"{fav} wins {p_win:.0%} of sims — dominant enough to back straight.",
        )
    elif abs(p_win - p_lose) < TIGHT_MARGIN and p_draw >= MATERIAL_DRAW:
        primary = _pick(
            "Draw No Bet (apuesta sin empate)", fav, p_dnb, o_dnb,
            f"Tight match ({p_win:.0%} vs {p_lose:.0%}) with a {p_draw:.0%} draw. "
            f"DNB refunds the draw — only loses if {dog} actually wins.",
        )
    elif p_draw >= MATERIAL_DRAW:
        primary = _pick(
            "Double Chance (gana o empata)", f"{fav} or Draw", p_dc, o_dc,
            f"{fav} is better but only wins {p_win:.0%}; draw is live at {p_draw:.0%}. "
            f"Double Chance cashes on win OR draw ({p_dc:.0%}) — the Canada-draw insurance.",
        )
    else:
        primary = _pick(
            "Win (ML)", fav, p_win, o_win,
            f"{fav} wins {p_win:.0%} with a low {p_draw:.0%} draw — straight win is clean.",
        )

    # ── Higher-payout value alternative: straight win, only if real EV ────────
    value_alt = None
    if primary["market"] != "Win (ML)":
        if win_ev is not None and win_ev >= MIN_VALUE_EV:
            value_alt = _pick(
                "Win (ML) — higher payout", fav, p_win, o_win,
                f"Straight win carries +{win_ev*100:.1f}% EV — take it for the bigger "
                f"return if you can stomach the {p_draw:.0%} draw risk.",
            )
        elif win_ev is None:
            value_alt = _pick(
                "Win (ML) — higher payout", fav, p_win, o_win,
                f"Bigger return than the insured play; needs win odds to confirm value.",
            )

    # ── Totals lean: most confident O/U 2.5 side ──────────────────────────────
    ou25 = book.over_under.get(2.5, {"over": 0.0, "under": 0.0})
    over_side = ou25["over"] >= ou25["under"]
    tot_prob = ou25["over"] if over_side else ou25["under"]
    tot_odds = odds.over_2_5 if over_side else odds.under_2_5
    totals_lean = _pick(
        "Total Goals 2.5", "Over 2.5" if over_side else "Under 2.5", tot_prob, tot_odds,
        f"Model expects {book.expected_total_goals:.2f} goals → "
        f"{'Over' if over_side else 'Under'} 2.5 at {tot_prob:.0%}.",
    )

    # ── BTTS lean ──────────────────────────────────────────────────────────────
    btts_yes_side = book.btts_yes >= book.btts_no
    btts_prob = book.btts_yes if btts_yes_side else book.btts_no
    btts_odds = odds.btts_yes if btts_yes_side else odds.btts_no
    btts_lean = _pick(
        "Both Teams To Score", "Yes" if btts_yes_side else "No", btts_prob, btts_odds,
        f"BTTS {'Yes' if btts_yes_side else 'No'} at {btts_prob:.0%}.",
    )

    return {
        "favorite": fav,
        "underdog": dog,
        "win_draw_lose": {
            "win": round(p_win, 4),
            "draw": round(p_draw, 4),
            "lose": round(p_lose, 4),
        },
        "primary_pick": primary,
        "value_alternative": value_alt,
        "totals_lean": totals_lean,
        "btts_lean": btts_lean,
    }


def recommend_1x2(
    p_home: float,
    p_draw: float,
    p_away: float,
    home_team: str,
    away_team: str,
    odds_home: Optional[float] = None,
    odds_draw: Optional[float] = None,
    odds_away: Optional[float] = None,
) -> dict:
    """
    Draw-insurance recommendation from explicit 1X2 probabilities (e.g. the
    devigged market) rather than the goal model. Use this when the rating model
    is unreliable for the teams (World Cup national sides) — the sharp market is
    the better probability estimate, and the value-add is the DC/DNB/ML choice.
    Same thresholds and win-prob-first ranking as recommend().
    """
    home_is_fav = p_home >= p_away
    fav = home_team if home_is_fav else away_team
    dog = away_team if home_is_fav else home_team
    p_win = p_home if home_is_fav else p_away
    p_lose = p_away if home_is_fav else p_home
    p_dc = p_win + p_draw
    p_dnb = p_win / (p_win + p_lose) if (p_win + p_lose) > 0 else 0.0
    o_win = odds_home if home_is_fav else odds_away

    if p_win >= STRONG_FAV_WIN:
        primary = _pick("Win (ML)", fav, p_win, o_win,
                        f"{fav} {p_win:.0%} per market — strong enough to back straight.")
    elif abs(p_win - p_lose) < TIGHT_MARGIN and p_draw >= MATERIAL_DRAW:
        primary = _pick("Draw No Bet (apuesta sin empate)", fav, p_dnb, None,
                        f"Tight ({p_win:.0%} vs {p_lose:.0%}) + {p_draw:.0%} draw — DNB refunds the draw.")
    elif p_draw >= MATERIAL_DRAW:
        primary = _pick("Double Chance (gana o empata)", f"{fav} or Draw", p_dc, None,
                        f"{fav} better but only {p_win:.0%}; draw live at {p_draw:.0%} → win-or-draw {p_dc:.0%}.")
    else:
        primary = _pick("Win (ML)", fav, p_win, o_win,
                        f"{fav} {p_win:.0%}, draw only {p_draw:.0%} — straight win is clean.")

    return {
        "source": "market_devig",
        "favorite": fav, "underdog": dog,
        "win_draw_lose": {"win": round(p_win, 4), "draw": round(p_draw, 4),
                          "lose": round(p_lose, 4)},
        "double_chance": {"fav_or_draw": round(p_dc, 4)},
        "draw_no_bet": {"fav": round(p_dnb, 4)},
        "primary_pick": primary,
    }

