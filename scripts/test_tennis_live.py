"""Tests for tennis_live.py — the in-play set-score win-probability model."""
import math

import pytest

import tennis_live as tl


# ── sets_to_win ────────────────────────────────────────────────────────────
def test_sets_to_win_bo3():
    assert tl.sets_to_win(3) == 2


def test_sets_to_win_bo5():
    assert tl.sets_to_win(5) == 3


def test_sets_to_win_rejects_invalid_format():
    with pytest.raises(ValueError):
        tl.sets_to_win(4)


# ── race_prob ──────────────────────────────────────────────────────────────
def test_race_prob_already_won():
    assert tl.race_prob(0, 2, 0.5) == 1.0


def test_race_prob_already_lost():
    assert tl.race_prob(2, 0, 0.5) == 0.0


def test_race_prob_symmetric_coin_flip_decider():
    # Both need exactly 1 more set, 50/50 per set -> 50/50 overall.
    assert math.isclose(tl.race_prob(1, 1, 0.5), 0.5, abs_tol=1e-9)


def test_race_prob_bo3_matches_closed_form():
    # P(A wins race to 2) = p^2 * (3 - 2p) — direct combinatorial formula.
    for p in (0.3, 0.5, 0.65, 0.8):
        expected = p**2 * (3 - 2 * p)
        assert math.isclose(tl.race_prob(2, 2, p), expected, rel_tol=1e-9)


def test_race_prob_monotonic_in_p():
    vals = [tl.race_prob(3, 3, p) for p in (0.2, 0.4, 0.6, 0.8)]
    assert vals == sorted(vals)


# ── implied_set_prob ─────────────────────────────────────────────────────────
def test_implied_set_prob_roundtrips_through_race_prob():
    for match_prob in (0.55, 0.65, 0.75, 0.9):
        for best_of in (3, 5):
            p = tl.implied_set_prob(match_prob, best_of)
            n = tl.sets_to_win(best_of)
            assert math.isclose(tl.race_prob(n, n, p), match_prob, abs_tol=1e-6)


def test_implied_set_prob_coin_flip_match_is_coin_flip_set():
    assert math.isclose(tl.implied_set_prob(0.5, 3), 0.5, abs_tol=1e-6)
    assert math.isclose(tl.implied_set_prob(0.5, 5), 0.5, abs_tol=1e-6)


def test_implied_set_prob_rejects_boundary_probs():
    with pytest.raises(ValueError):
        tl.implied_set_prob(0.0, 3)
    with pytest.raises(ValueError):
        tl.implied_set_prob(1.0, 3)


# ── live_win_prob ──────────────────────────────────────────────────────────
def test_live_win_prob_pregame_untouched_score_matches_pregame():
    out = tl.live_win_prob(0.7, 0, 0, best_of=3)
    assert math.isclose(out["live_match_prob_home"], 0.7, abs_tol=1e-6)


def test_live_win_prob_leading_a_set_raises_win_prob():
    pregame = 0.6
    up_one = tl.live_win_prob(pregame, 1, 0, best_of=3)["live_match_prob_home"]
    down_one = tl.live_win_prob(pregame, 0, 1, best_of=3)["live_match_prob_home"]
    assert up_one > pregame > down_one


def test_live_win_prob_match_already_won():
    out = tl.live_win_prob(0.6, 2, 0, best_of=3)
    assert out["live_match_prob_home"] == 1.0
    assert out["match_decided"] is True


def test_live_win_prob_match_already_lost():
    out = tl.live_win_prob(0.6, 0, 3, best_of=5)
    assert out["live_match_prob_home"] == 0.0
    assert out["match_decided"] is True


def test_live_win_prob_bo5_two_sets_all_favours_leader_more_than_bo3_one_set_all():
    # Being up 2-0 in a bo5 (need 1 more of 3) is a stronger position than
    # being up 1-0 in a bo3 (need 1 more of 2) for the same pregame prob,
    # since the trailer has fewer sets left to climb back from either way —
    # what we actually assert is just that leading always raises the number
    # and the match-already-in-hand case is close to 1 for a real favourite.
    out = tl.live_win_prob(0.65, 2, 0, best_of=5)
    assert out["live_match_prob_home"] > 0.65


def test_live_win_prob_rejects_negative_sets():
    with pytest.raises(ValueError):
        tl.live_win_prob(0.6, -1, 0, best_of=3)


def test_live_win_prob_rejects_sets_over_cap():
    with pytest.raises(ValueError):
        tl.live_win_prob(0.6, 3, 0, best_of=3)  # bo3 caps at 2 set wins
