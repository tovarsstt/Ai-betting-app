"""Tests for the generic Poisson scoring engine. Pure math — no network, no API."""
import math

import poisson_model as pm


# ── Score matrix ──────────────────────────────────────────────────────────────
def test_matrix_sums_to_one():
    matrix = pm.score_matrix(1.6, 1.1)
    total = sum(c for row in matrix for c in row)
    assert math.isclose(total, 1.0, abs_tol=1e-9)


def test_rho_zero_matches_independent_poisson():
    matrix = pm.score_matrix(1.4, 1.4, rho=0.0)
    p00 = matrix[0][0]
    expected = pm.poisson_pmf(0, 1.4) * pm.poisson_pmf(0, 1.4)
    assert math.isclose(p00, expected, rel_tol=1e-6)


def test_win_draw_loss_sums_to_one():
    matrix = pm.score_matrix(1.7, 1.2)
    h, d, a = pm.win_draw_loss(matrix)
    assert math.isclose(h + d + a, 1.0, abs_tol=1e-9)


# ── Correct score ───────────────────────────────────────────────────────────
def test_correct_score_sorted_descending():
    matrix = pm.score_matrix(1.6, 1.1)
    cs = pm.correct_score_probs(matrix, top_n=10)
    probs = [c["prob"] for c in cs]
    assert probs == sorted(probs, reverse=True)
    assert len(cs) == 10


def test_correct_score_most_likely_is_low_scoring_for_low_lambdas():
    matrix = pm.score_matrix(1.1, 0.9)
    cs = pm.correct_score_probs(matrix, top_n=1)
    top = cs[0]
    assert top["home"] <= 2 and top["away"] <= 2


def test_correct_score_has_fair_odds():
    matrix = pm.score_matrix(1.6, 1.1)
    cs = pm.correct_score_probs(matrix, top_n=3)
    for c in cs:
        assert c["fair_decimal_odds"] > 1.0
        assert math.isclose(1.0 / c["fair_decimal_odds"], c["prob"], abs_tol=0.01)


# ── Monte Carlo simulator ──────────────────────────────────────────────────
def test_simulation_matches_closed_form_within_tolerance():
    matrix = pm.score_matrix(1.6, 1.1, rho=-0.13)
    h, d, a = pm.win_draw_loss(matrix)
    sim = pm.simulate_matches(matrix, n_sims=40000, seed=42)
    sim_home = pm.hit_rate(sim, pm.home_win)["prob"]
    sim_draw = pm.hit_rate(sim, pm.draw)["prob"]
    sim_away = pm.hit_rate(sim, pm.away_win)["prob"]
    assert abs(sim_home - h) < 0.02
    assert abs(sim_draw - d) < 0.02
    assert abs(sim_away - a) < 0.02


def test_simulation_is_reproducible_with_seed():
    matrix = pm.score_matrix(1.4, 1.2)
    sim1 = pm.simulate_matches(matrix, n_sims=5000, seed=7)
    sim2 = pm.simulate_matches(matrix, n_sims=5000, seed=7)
    assert list(sim1.home_goals) == list(sim2.home_goals)
    assert list(sim1.away_goals) == list(sim2.away_goals)


def test_hit_rate_ci_contains_the_point_estimate():
    matrix = pm.score_matrix(1.5, 1.3)
    sim = pm.simulate_matches(matrix, n_sims=10000, seed=1)
    r = pm.hit_rate(sim, pm.home_win)
    lo, hi = r["ci_95"]
    assert lo <= r["prob"] <= hi


def test_combo_hit_rate_is_never_above_either_marginal():
    matrix = pm.score_matrix(1.6, 1.1)
    sim = pm.simulate_matches(matrix, n_sims=20000, seed=3)
    home = pm.hit_rate(sim, pm.home_win)["prob"]
    btts = pm.hit_rate(sim, pm.btts_yes)["prob"]
    combo = pm.combo_hit_rate(sim, [pm.home_win, pm.btts_yes])["prob"]
    assert combo <= home + 1e-6
    assert combo <= btts + 1e-6


def test_over_under_predicates_are_complementary_around_the_line():
    matrix = pm.score_matrix(1.6, 1.4)
    sim = pm.simulate_matches(matrix, n_sims=20000, seed=5)
    over = pm.hit_rate(sim, pm.over(2.5))["prob"]
    under = pm.hit_rate(sim, pm.under(2.5))["prob"]
    # no push at a .5 line — every simulated total is on one side or the other
    assert math.isclose(over + under, 1.0, abs_tol=1e-9)


def test_exact_score_predicate_matches_correct_score_prob():
    matrix = pm.score_matrix(1.3, 1.0)
    sim = pm.simulate_matches(matrix, n_sims=40000, seed=9)
    closed_form = matrix[1][0]
    simulated = pm.hit_rate(sim, pm.exact_score(1, 0))["prob"]
    assert abs(simulated - closed_form) < 0.02

def test_default_is_120k_real_simulations():
    # Guard the contract: default sample size is 120,000 REAL random draws.
    matrix = pm.score_matrix(1.88, 0.65, rho=-0.13)
    sim = pm.simulate_matches(matrix)           # no n_sims arg -> default
    assert sim.n_sims == 120_000
    assert len(sim.home_goals) == 120_000       # actual draw arrays, not a label
    # real sampling: two seeds must NOT produce identical outcomes
    a = pm.simulate_matches(matrix, seed=1)
    b = pm.simulate_matches(matrix, seed=2)
    assert (a.home_goals != b.home_goals).any()
    # converged: simulated home-win within 1pt of the analytic matrix
    analytic = sum(matrix[h][x] for h in range(len(matrix))
                   for x in range(len(matrix[0])) if h > x)
    simulated = pm.hit_rate(a, pm.home_win)["prob"]
    assert abs(simulated - analytic) < 0.01
