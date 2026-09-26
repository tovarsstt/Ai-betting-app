"""Tests for soccer_backtest helpers — pure math, fixed fixtures, no refits."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from soccer_backtest import game_probs, month_starts, rps


def test_rps_perfect_and_uniform():
    assert rps((1.0, 0.0, 0.0), 0) == 0.0                      # nailed it
    assert rps((0.0, 0.0, 1.0), 0) == 1.0                      # maximally wrong
    u = rps((1 / 3, 1 / 3, 1 / 3), 0)
    assert 0.2 < u < 0.35                                      # no-skill anchor


def test_rps_rewards_mass_near_truth():
    close = rps((0.6, 0.3, 0.1), 0)
    far = rps((0.1, 0.3, 0.6), 0)
    assert close < far


def test_month_starts_orders_and_filters():
    games = [{"date": "2025-10-30"}, {"date": "2025-11-02"},
             {"date": "2025-11-20"}, {"date": "2026-01-05"}]
    assert month_starts(games, "2025-11-01") == ["2025-11-01", "2026-01-01"]


def test_game_probs_shapes_and_refuses_unknown():
    league = {"mu": 0.1, "home_advantage": 0.2,
              "teams": {"A": {"attack": 0.3, "defense": 0.1},
                        "B": {"attack": -0.1, "defense": -0.2},
                        "C": {"attack": None, "defense": None}}}
    probs = game_probs(league, "A", "B")
    assert probs is not None
    assert abs(sum(probs) - 1.0) < 1e-6
    assert probs[0] > probs[2]                 # stronger home side favored
    assert game_probs(league, "A", "Z") is None
    assert game_probs(league, "A", "C") is None    # unfitted team -> no number
