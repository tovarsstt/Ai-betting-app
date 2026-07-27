"""Tests for failure_modes.py — the 'how it could go wrong' layer.
Pure functions on synthetic inputs, no network."""
import failure_modes as fm
from poisson_model import score_matrix

MATRIX = score_matrix(1.1, 0.9, rho=-0.13)


# ── match_kill_paths: probabilities come from the matrix, not vibes ──────────
def test_ml_home_kill_paths_sum_to_lose_prob():
    out = fm.match_kill_paths(MATRIX, "ml_home")
    events = {k["event"]: k["prob"] for k in out["kill_paths"]}
    assert "draw" in events and "opponent wins" in events
    total_kill = sum(events.values())
    assert abs(total_kill - (1 - out["pick_prob"])) < 1e-9


def test_under_25_kill_paths_name_the_exact_goal_counts():
    out = fm.match_kill_paths(MATRIX, "under_2_5")
    events = {k["event"] for k in out["kill_paths"]}
    assert "exactly 3 goals" in events
    assert "4+ goals" in events


def test_btts_no_kill_path_is_both_score():
    out = fm.match_kill_paths(MATRIX, "btts_no")
    assert out["kill_paths"][0]["event"] == "both teams score"
    assert 0 < out["kill_paths"][0]["prob"] < 1


def test_kill_paths_sorted_desc_and_rounded():
    out = fm.match_kill_paths(MATRIX, "under_2_5")
    probs = [k["prob"] for k in out["kill_paths"]]
    assert probs == sorted(probs, reverse=True)
    assert all(round(p, 4) == p for p in probs)


def test_unknown_market_returns_empty_not_invented():
    out = fm.match_kill_paths(MATRIX, "corner_race_to_5")
    assert out["kill_paths"] == []
    assert "not modelled" in out["note"]


# ── availability: appearance rate from real cache counts ────────────────────
def test_availability_full_appearance_is_low_risk():
    out = fm.availability(6, 6)
    assert out["appearance_rate"] == 1.0
    assert out["risk"] == "LOW"


def test_availability_partial_flags_rotation():
    out = fm.availability(3, 6)
    assert out["appearance_rate"] == 0.5
    assert out["risk"] == "HIGH"
    assert out["missed"] == 3


def test_availability_zero_team_games_is_no_data():
    out = fm.availability(0, 0)
    assert out["risk"] == "NO_DATA"


# ── unmodelled taxonomy: fixed lists, never probabilities ────────────────────
def test_unmodelled_ufc_names_late_withdrawal():
    flags = fm.unmodelled("ufc")
    assert any("withdraw" in f["risk"].lower() for f in flags)
    assert all("prob" not in f for f in flags)  # never invented numbers


def test_unmodelled_soccer_names_benching_and_settlement():
    flags = fm.unmodelled("soccer")
    joined = " ".join(f["risk"].lower() for f in flags)
    assert "bench" in joined or "lineup" in joined
    assert "extra time" in joined  # 90' vs incl-ET settlement trap


def test_unmodelled_every_flag_has_mitigation():
    for sport in ("soccer", "ufc", "tennis", "nba", "nfl"):
        for f in fm.unmodelled(sport):
            assert f["mitigation"], f"{sport} flag missing mitigation"


def test_unmodelled_unknown_sport_falls_back_to_generic():
    flags = fm.unmodelled("curling")
    assert len(flags) >= 1


# ── edge_kill_path: parses day-card selection names ──────────────────────────
def test_edge_kill_path_home_ml_top_kill_is_biggest_threat():
    out = fm.edge_kill_path(MATRIX, "Home ML")
    assert out["event"] in ("draw", "opponent wins")
    assert 0 < out["prob"] < 1


def test_edge_kill_path_under_any_line_names_first_killing_count():
    out = fm.edge_kill_path(MATRIX, "Under 2.25")
    # first whole-goal count above 2.25 is 3
    assert out["event"] == "exactly 3 goals"


def test_edge_kill_path_over_names_the_short_side():
    out = fm.edge_kill_path(MATRIX, "Over 2.5")
    assert "goals" in out["event"]


def test_edge_kill_path_btts_no():
    out = fm.edge_kill_path(MATRIX, "BTTS No")
    assert out["event"] == "both teams score"


def test_edge_kill_path_unknown_selection_is_none():
    assert fm.edge_kill_path(MATRIX, "Corners Over 9.5") is None
