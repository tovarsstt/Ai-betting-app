"""Tests for slip_linter — the pre-bet gate. Uses fixed ROI tables so the
verdicts are deterministic and don't depend on the live slips file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from slip_linter import lint, leg_bucket, roi_by

# Mirrors the user's settled record: longshot wins, lottery/chalk/single bleed.
BAND = {
    "heavy chalk (<1.50)": -33.0,
    "value band (1.50-2.50)": 10.0,
    "longshot (2.50-5.0)": 85.0,
    "lottery (5.0+)": -18.0,
}
SHAPE = {"single": -7.0, "2-3 legs": 83.0, "4-6 legs": 25.0, "7+ legs": -100.0}


def test_clean_two_three_leg_ticket_accepts():
    legs = [{"decimal": 3.2, "selection": "A"}, {"decimal": 2.8, "selection": "B"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "ACCEPT"
    assert v.keep_count == 2


def test_lottery_leg_gets_cut():
    legs = [{"decimal": 3.0, "selection": "A"}, {"decimal": 6.5, "selection": "moon"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "TRIM"
    assert 1 in v.cut_legs  # the 6.5 lottery leg
    assert v.keep_count == 1


def test_chalk_leg_gets_cut_for_losing_band():
    legs = [{"decimal": 1.30, "selection": "chalk"}, {"decimal": 3.0, "selection": "B"}]
    v = lint(legs, BAND, SHAPE)
    assert 0 in v.cut_legs
    assert v.status == "TRIM"


def test_seven_plus_legs_trimmed_to_cap():
    legs = [{"decimal": 2.6 + i * 0.1, "selection": f"L{i}"} for i in range(7)]
    v = lint(legs, BAND, SHAPE)
    assert v.keep_count <= 4  # hard cap enforced


def test_all_losing_bands_rejects():
    legs = [{"decimal": 6.0, "selection": "moon"}, {"decimal": 1.2, "selection": "chalk"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "REJECT"
    assert v.keep_count == 0


def test_single_in_edge_band_warns_not_rejects():
    legs = [{"decimal": 3.0, "selection": "solo"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "ACCEPT"          # leg itself is fine
    assert any("single" in r.lower() for r in v.reasons)  # but nudged to 2-3 lane


def test_leg_bucket_boundaries():
    assert leg_bucket(1) == "single"
    assert leg_bucket(3) == "2-3 legs"
    assert leg_bucket(6) == "4-6 legs"
    assert leg_bucket(9) == "7+ legs"


def test_roi_by_computes_sign():
    items = [{"stake": 10, "payout": 0, "k": "x"}, {"stake": 10, "payout": 30, "k": "x"}]
    assert roi_by(items, lambda i: i["k"])["x"] == 50.0  # staked 20, back 30
