"""Tests for tennis context nudges (fatigue / home crowd) — pure logic, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edge_api import (_tennis_context_logit, TENNIS_CROWD_LOGIT,
                      TENNIS_FATIGUE_CAP)


def test_no_inputs_means_zero_nudge():
    total, detail = _tennis_context_logit(None, None, None)
    assert total == 0.0 and detail == {}


def test_crowd_direction():
    home, _ = _tennis_context_logit("home", None, None)
    away, _ = _tennis_context_logit("away", None, None)
    assert home == TENNIS_CROWD_LOGIT and away == -TENNIS_CROWD_LOGIT


def test_fatigue_penalizes_heavier_recent_workload():
    # home ground 3 sets, away 2 -> nudge against home
    total, detail = _tennis_context_logit(None, 3, 2)
    assert total < 0 and detail["fatigue_adj"] == total


def test_fatigue_is_capped():
    total, _ = _tennis_context_logit(None, 9, 0)
    assert total == -TENNIS_FATIGUE_CAP


def test_crowd_and_fatigue_combine():
    total, detail = _tennis_context_logit("home", 2, 2)
    assert total == TENNIS_CROWD_LOGIT          # equal workload adds nothing
    assert "fatigue_adj" not in detail
