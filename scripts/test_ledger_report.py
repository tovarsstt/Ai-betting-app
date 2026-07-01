"""Tests for ledger_report — CLV grading + calibration. Uses inline ledgers so
verdicts are deterministic and don't depend on the live pick_ledger.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ledger_report import to_decimal, clv_pct, clv_report, calibration_report, _clv_flag


def test_american_to_decimal():
    assert round(to_decimal(-110), 4) == 1.9091
    assert to_decimal(150) == 2.5


def test_clv_positive_when_bet_price_beats_close():
    # bet +150 (dec 2.5), closed +120 (dec 2.2) -> you got the better price
    assert clv_pct(150, 120) > 0


def test_clv_negative_when_line_moved_against():
    assert clv_pct(120, 150) < 0


def test_flag_lost_but_beat_close_is_good_process():
    assert "GOOD PROCESS" in _clv_flag(8.0, "L")


def test_flag_won_but_missed_close_is_lucky():
    assert "LUCKY" in _clv_flag(-8.0, "W")


def test_clv_report_skips_picks_without_close():
    ledger = [
        {"sport": "NBA", "selection": "A", "odds": 150, "closing_odds": 120, "result": "W"},
        {"sport": "NBA", "selection": "B", "odds": -110, "closing_odds": None, "result": "PENDING"},
    ]
    rep = clv_report(ledger)
    assert rep["graded"] == 1
    assert rep["pending_awaiting_close"] == 1
    assert rep["beat_rate_pct"] == 100.0


def test_calibration_buckets_and_overconfidence():
    # model says ~80% on 4 picks but only 1 wins (25%) -> overconfident
    ledger = [{"sport": "T", "result": r, "predicted_prob": 0.80}
              for r in ("W", "L", "L", "L")]
    rep = calibration_report(ledger)
    b = rep["buckets"][0]
    assert b["bucket"] == "80-90%"
    assert b["verdict"] == "overconfident"
    assert b["gap"] > 0


def test_binomial_test_flags_significant_on_large_sample_gap():
    # 30 picks at model 80%, only 15 win (50%) -> same-direction gap as the
    # n=4 case above, but at real volume this is a statistically real miss.
    ledger = [{"sport": "T", "result": "W" if i < 15 else "L", "predicted_prob": 0.80}
              for i in range(30)]
    rep = calibration_report(ledger)
    b = rep["buckets"][0]
    assert b["binomial_test"]["significant"] is True
    assert b["binomial_test"]["p_value"] < 0.05


def test_binomial_test_not_significant_on_tiny_sample():
    # n=5, model 60%, 2 win (40%) -> a real-looking gap, but n=5 is too little
    # data for a two-sided binomial test to call it significant.
    ledger = [{"sport": "T", "result": r, "predicted_prob": 0.60}
              for r in ("W", "W", "L", "L", "L")]
    rep = calibration_report(ledger)
    b = rep["buckets"][0]
    assert b["binomial_test"]["significant"] is False


def test_binomial_test_not_significant_when_actual_matches_predicted():
    ledger = [{"sport": "T", "result": r, "predicted_prob": 0.70}
              for r in ["W"] * 7 + ["L"] * 3]
    rep = calibration_report(ledger)
    b = rep["buckets"][0]
    assert b["binomial_test"]["significant"] is False
    assert b["binomial_test"]["p_value"] > 0.5


def test_calibration_counts_missing_prob():
    ledger = [{"result": "W", "predicted_prob": 0.6},
              {"result": "L"},  # no predicted_prob
              {"result": "PENDING", "predicted_prob": 0.7}]  # not settled
    rep = calibration_report(ledger)
    assert rep["settled_with_prob"] == 1
    assert rep["settled_missing_prob"] == 1
    assert rep["enough_volume"] is False
