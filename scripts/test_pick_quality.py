"""Tests for pick_quality — the win-probability-first grade on every pick.
Calibrated from the 2026-06-25 tennis slips: <1.50 locks 6/6, soft favs 6/8, and
both misses (Kecmanovic ~56%, Navarro ~60%) were sub-62% soft favourites the engine
had wrongly called safe. The grade must refuse to call a sub-62% pick a LOCK/PICK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edge_api import pick_quality, LOCK_PROB, PICK_PROB


def test_high_prob_with_value_is_lock():
    grade, _ = pick_quality(0.78, best_ev=0.06, has_edge=True)  # a 1.30 lock
    assert grade == "LOCK"


def test_solid_favourite_with_edge_is_pick():
    grade, _ = pick_quality(0.65, best_ev=0.03, has_edge=True)
    assert grade == "PICK"


def test_soft_favourite_is_only_a_lean():
    # Navarro ~60% / Kecmanovic ~56% — favourites, but NOT locks. Must demote to LEAN.
    for prob in (0.60, 0.56):
        grade, note = pick_quality(prob, best_ev=0.03, has_edge=True)
        assert grade == "LEAN"
        assert "not a lock" in note.lower()


def test_no_edge_is_pass():
    grade, _ = pick_quality(0.80, best_ev=0.10, has_edge=False)
    assert grade == "PASS"


def test_high_prob_but_no_value_is_not_a_lock():
    # 75% to win but EV<=0 (no value chalk) — can't be LOCK/PICK; falls to LEAN.
    grade, _ = pick_quality(0.75, best_ev=-0.01, has_edge=True)
    assert grade == "LEAN"


def test_thresholds_are_win_prob_ordered():
    assert LOCK_PROB > PICK_PROB >= 0.60


# ── tennis stale-rank guard (Jul 18 2026 — Badosa comeback vs rank-141 read) ─
def test_stale_guard_caps_grade_on_big_gap():
    from edge_api import stale_rank_guard
    q, note, flag = stale_rank_guard(0.51, 0.21, "PICK", "base")
    assert q == "LEAN"
    assert "capped" in note
    assert "market" in flag


def test_stale_guard_quiet_when_model_and_market_agree():
    from edge_api import stale_rank_guard
    q, note, flag = stale_rank_guard(0.62, 0.58, "PICK", "base")
    assert (q, note, flag) == ("PICK", "base", None)


def test_stale_guard_fires_both_directions_and_lock_drops_to_pick():
    from edge_api import stale_rank_guard
    q, _, flag = stale_rank_guard(0.72, 0.49, "LOCK", "n")
    assert q == "PICK" and flag is not None
    q2, _, flag2 = stale_rank_guard(0.40, 0.79, "LEAN", "n")   # model fading a market lock
    assert flag2 is not None and q2 == "LEAN"                   # LEAN stays, flag shown
