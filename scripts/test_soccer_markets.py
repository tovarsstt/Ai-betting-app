"""Tests for the soccer markets engine. Pure math — no network, no API."""
import math

import soccer_markets as sm


# ── Score matrix ──────────────────────────────────────────────────────────────
def test_matrix_sums_to_one():
    matrix = sm.score_matrix(1.6, 1.1)
    total = sum(c for row in matrix for c in row)
    assert math.isclose(total, 1.0, abs_tol=1e-9)


def test_dixon_coles_lifts_draws_vs_independent_poisson():
    # rho < 0 should raise the combined draw probability vs plain Poisson (rho=0)
    plain = sm.derive_markets(sm.score_matrix(1.4, 1.4, rho=0.0))
    dc = sm.derive_markets(sm.score_matrix(1.4, 1.4, rho=-0.13))
    assert dc.draw > plain.draw


# ── Market identities (must hold exactly by construction) ─────────────────────
def test_1x2_probabilities_sum_to_one():
    b = sm.derive_markets(sm.score_matrix(2.0, 0.8))
    assert math.isclose(b.home_win + b.draw + b.away_win, 1.0, abs_tol=1e-9)


def test_double_chance_equals_sum_of_outcomes():
    b = sm.derive_markets(sm.score_matrix(1.7, 1.2))
    assert math.isclose(b.dc_home_draw, b.home_win + b.draw, abs_tol=1e-9)
    assert math.isclose(b.dc_away_draw, b.away_win + b.draw, abs_tol=1e-9)
    assert math.isclose(b.dc_home_away, b.home_win + b.away_win, abs_tol=1e-9)


def test_double_chance_never_below_straight_win():
    b = sm.derive_markets(sm.score_matrix(1.5, 1.3))
    assert b.dc_home_draw >= b.home_win
    assert b.dc_away_draw >= b.away_win


def test_draw_no_bet_excludes_the_draw():
    b = sm.derive_markets(sm.score_matrix(1.8, 1.0))
    # DNB renormalizes over non-draw outcomes only → home+away DNB = 1
    assert math.isclose(b.dnb_home + b.dnb_away, 1.0, abs_tol=1e-9)
    # and the favourite's DNB prob exceeds its raw win prob (draw mass removed)
    assert b.dnb_home > b.home_win


def test_totals_are_monotone_decreasing_overs():
    b = sm.derive_markets(sm.score_matrix(1.6, 1.4))
    overs = [b.over_under[ln]["over"] for ln in (0.5, 1.5, 2.5, 3.5, 4.5)]
    assert overs == sorted(overs, reverse=True)


def test_over_under_complementary():
    b = sm.derive_markets(sm.score_matrix(1.6, 1.4))
    for ln, v in b.over_under.items():
        assert math.isclose(v["over"] + v["under"], 1.0, abs_tol=1e-9)


# ── Odds helpers ──────────────────────────────────────────────────────────────
def test_devig_3way_sums_to_one_and_reports_vig():
    dv = sm.devig_3way(-110, 250, 280)
    assert math.isclose(dv["home"] + dv["draw"] + dv["away"], 1.0, abs_tol=1e-9)
    assert dv["vig_pct"] > 0


def test_american_decimal_roundtrip():
    assert math.isclose(sm.american_to_decimal(-200), 1.5, abs_tol=1e-9)
    assert math.isclose(sm.american_to_decimal(150), 2.5, abs_tol=1e-9)
    assert sm.decimal_to_american(1.5) == -200
    assert sm.decimal_to_american(2.5) == 150


# ── Market calibration (fit lambdas to devigged 1X2) ──────────────────────────
def test_solver_recovers_known_lambdas():
    # Build 1X2 from known lambdas, then recover them
    b = sm.derive_markets(sm.score_matrix(1.8, 1.0, rho=0.0))
    lh, la, resid = sm.solve_lambdas_from_1x2(b.home_win, b.draw, b.away_win)
    assert abs(lh - 1.8) < 0.12
    assert abs(la - 1.0) < 0.12
    assert resid < 0.02


def test_calibrated_board_reproduces_market_1x2():
    # Devigged market → calibrated lambdas → board should match the market 1X2
    dv = sm.devig_3way(168, 360, 540)  # Brazil/Morocco style decimals→american
    lh, la, _ = sm.solve_lambdas_from_1x2(dv["home"], dv["draw"], dv["away"])
    b = sm.derive_markets(sm.score_matrix(lh, la))
    assert abs(b.home_win - dv["home"]) < 0.04
    assert abs(b.away_win - dv["away"]) < 0.04


def test_calibration_favorite_has_higher_lambda():
    lh, la, _ = sm.solve_lambdas_from_1x2(0.60, 0.25, 0.15)  # strong home fav
    assert lh > la


# ── Recommendation: the Canada draw-insurance lesson ──────────────────────────
def test_strong_favorite_gets_straight_win():
    b = sm.derive_markets(sm.score_matrix(2.6, 0.6))  # lopsided
    rec = sm.recommend(b, "Brazil", "Minnow")
    assert b.home_win >= sm.STRONG_FAV_WIN
    assert rec["primary_pick"]["market"] == "Win (ML)"


def test_better_but_drawish_favorite_gets_double_chance():
    # Canada-style: better team, moderate win prob, live draw → insure it
    b = sm.derive_markets(sm.score_matrix(1.35, 1.05))
    rec = sm.recommend(b, "Canada", "Opponent")
    assert b.draw >= sm.MATERIAL_DRAW
    assert b.home_win < sm.STRONG_FAV_WIN
    assert "Double Chance" in rec["primary_pick"]["market"] or \
           "Draw No Bet" in rec["primary_pick"]["market"]


def test_tight_match_high_draw_gets_draw_no_bet():
    b = sm.derive_markets(sm.score_matrix(1.15, 1.1))  # near-even, low scoring
    rec = sm.recommend(b, "TeamA", "TeamB")
    assert rec["primary_pick"]["market"].startswith("Draw No Bet")


def test_value_alternative_surfaces_when_win_odds_have_edge():
    b = sm.derive_markets(sm.score_matrix(1.4, 1.05))
    # Generous +180 win price on a ~45% favourite = clear +EV straight win
    odds = sm.MarketOdds(home=180)
    rec = sm.recommend(b, "Canada", "Opponent", odds)
    if rec["primary_pick"]["market"] != "Win (ML)":
        assert rec["value_alternative"] is not None
        assert rec["value_alternative"]["ev_pct"] > 0


# ── Upset / public-trap detector ──────────────────────────────────────────────
def test_upset_high_for_canada_pattern():
    # Modest favourite, live draw, dog with real equity → should flag
    u = sm.upset_risk(0.50, 0.27, 0.23, fav_decimal_odds=1.55)
    assert u["level"] in ("ELEVATED", "HIGH")
    assert u["reasons"]
    assert "0.5u" in u["protective_action"] or "Double Chance" in u["protective_action"]


def test_upset_low_for_genuine_lock():
    # Switzerland-style heavy favourite → no upset flag
    u = sm.upset_risk(0.78, 0.15, 0.07, fav_decimal_odds=1.19)
    assert u["level"] == "LOW"


def test_upset_public_pct_escalates():
    base = sm.upset_risk(0.58, 0.25, 0.17, fav_decimal_odds=1.7)
    trap = sm.upset_risk(0.58, 0.25, 0.17, fav_decimal_odds=1.7, public_pct_on_fav=0.82)
    assert trap["score"] > base["score"]


def test_upset_non_win_prob_is_one_minus_fav():
    u = sm.upset_risk(0.55, 0.26, 0.19)
    assert abs(u["non_win_prob"] - (1 - 0.55)) < 1e-9


def test_ev_pct_positive_when_model_beats_price():
    # Model 60% vs +100 (implied 50%) → strong +EV
    assert sm.ev_pct(0.60, 100) > 0
    # Model 40% vs -200 (implied 66.7%) → negative EV
    assert sm.ev_pct(0.40, -200) < 0
