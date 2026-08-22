"""Tests for scripts/win_simulator.py.

The directive under test: WINNING IS KING. Every verdict must be driven by win
probability, and EV must never be able to change one. Seeded throughout so the
Monte Carlo is deterministic.
"""
import pytest

import win_simulator as ws


def leg(prob, decimal=2.0, match=None):
    d = {"prob": prob, "decimal": decimal}
    if match:
        d["match"] = match
    return d


# ── Win probability is the headline ─────────────────────────────────────────

def test_single_leg_win_prob_matches_its_probability():
    out = ws.simulate_ticket([leg(0.70)], n_sims=200_000, seed=1)
    assert out["win_prob"] == pytest.approx(0.70, abs=0.005)


def test_parlay_win_prob_is_the_product():
    out = ws.simulate_ticket([leg(0.80), leg(0.75)], n_sims=200_000, seed=1)
    assert out["win_prob"] == pytest.approx(0.60, abs=0.006)


def test_confidence_interval_brackets_the_estimate():
    out = ws.simulate_ticket([leg(0.6), leg(0.6)], n_sims=50_000, seed=3)
    lo, hi = out["win_prob_ci95"]
    assert lo < out["win_prob"] < hi


def test_more_sims_tighten_the_interval():
    wide = ws.simulate_ticket([leg(0.5)], n_sims=2_000, seed=4)
    tight = ws.simulate_ticket([leg(0.5)], n_sims=200_000, seed=4)
    width = lambda o: o["win_prob_ci95"][1] - o["win_prob_ci95"][0]
    assert width(tight) < width(wide)


# ── Verdicts come from winning, NEVER from EV ───────────────────────────────

def test_verdict_bands_track_win_probability():
    assert ws.simulate_ticket([leg(0.75)], n_sims=50_000, seed=5)["verdict"] == "STRONG"
    assert ws.simulate_ticket([leg(0.54)], n_sims=50_000, seed=5)["verdict"] == "PLAYABLE"
    assert ws.simulate_ticket([leg(0.40)], n_sims=50_000, seed=5)["verdict"] == "THIN"
    assert ws.simulate_ticket([leg(0.15)], n_sims=50_000, seed=5)["verdict"] == "LOTTERY"


def test_fat_ev_longshot_is_still_a_lottery():
    """The core of the directive: a hugely +EV 20% shot must NOT be dressed up
    as a good bet. Winning is the record we're building."""
    out = ws.simulate_ticket([leg(0.20, decimal=10.0)], n_sims=100_000, seed=6)
    assert out["ev_pct"] > 50           # very +EV
    assert out["verdict"] == "LOTTERY"  # and still not a bet


def test_probable_winner_at_negative_ev_outranks_the_longshot():
    """A 70% winner at slightly -EV ranks ABOVE a 20% shot at fat +EV."""
    safe = ws.simulate_single(0.70, 1.40)     # EV -2%
    longshot = ws.simulate_single(0.20, 10.0)  # EV +100%
    assert safe["ev_pct"] < 0 < longshot["ev_pct"]
    assert ws.rank_by_winning([longshot, safe])[0] is safe


def test_ranking_uses_ev_only_to_break_a_win_prob_tie():
    a = ws.simulate_single(0.60, 1.60)
    b = ws.simulate_single(0.60, 1.90)
    assert ws.rank_by_winning([a, b])[0] is b   # same win%, better price wins


# ── The "so close" distribution a bare product hides ───────────────────────

def test_legs_won_distribution_sums_to_one():
    out = ws.simulate_ticket([leg(0.7), leg(0.7), leg(0.7)], n_sims=50_000, seed=8)
    assert sum(out["legs_won_distribution"].values()) == pytest.approx(1.0, abs=0.01)


def test_near_miss_can_be_likelier_than_the_win():
    """A six-leg stack lands 5 of 6 more often than it lands all 6 — the exact
    feeling that makes long parlays seem close when they aren't."""
    legs = [leg(p) for p in (0.645, 0.715, 0.658, 0.839, 0.870, 0.736)]
    out = ws.simulate_ticket(legs, n_sims=200_000, seed=9)
    assert out["legs_won_distribution"][5] > out["win_prob"]


def test_expected_legs_won_is_the_sum_of_probabilities():
    legs = [leg(0.5), leg(0.8), leg(0.9)]
    out = ws.simulate_ticket(legs, n_sims=100_000, seed=10)
    assert out["expected_legs_won"] == pytest.approx(2.2, abs=0.02)


# ── Correlation honesty ─────────────────────────────────────────────────────

def test_same_match_legs_are_flagged_not_silently_multiplied():
    legs = [leg(0.6, match="A vs B"), leg(0.7, match="A vs B")]
    out = ws.simulate_ticket(legs, n_sims=10_000, seed=11)
    assert "NOT independent" in out["correlated_legs_warning"]


def test_different_matches_carry_no_warning():
    legs = [leg(0.6, match="A vs B"), leg(0.7, match="C vs D")]
    out = ws.simulate_ticket(legs, n_sims=10_000, seed=11)
    assert out["correlated_legs_warning"] is None


# ── Input validation ────────────────────────────────────────────────────────

def test_empty_and_invalid_inputs_are_refused():
    assert "error" in ws.simulate_ticket([])
    assert "error" in ws.simulate_ticket([leg(0.0)])
    assert "error" in ws.simulate_ticket([leg(1.5)])


# ── Risk of ruin — the number that matters on a small bankroll ─────────────

def test_lottery_shape_busts_a_small_bankroll():
    out = ws.risk_of_ruin(0.16, 3.81, stake=15, bankroll=200,
                          n_bets=100, n_sims=3_000, seed=12)
    assert out["risk_of_ruin_pct"] > 80


def test_probable_winner_survives_far_better():
    out = ws.risk_of_ruin(0.70, 1.45, stake=15, bankroll=200,
                          n_bets=100, n_sims=3_000, seed=12)
    assert out["risk_of_ruin_pct"] < 40


def test_risk_of_ruin_validates_inputs():
    assert "error" in ws.risk_of_ruin(0.6, 2.0, stake=0, bankroll=100)
    assert "error" in ws.risk_of_ruin(0.6, 2.0, stake=10, bankroll=0)
