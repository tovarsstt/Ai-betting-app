"""Tests for tennis_games_model — exact hold math + simulation properties."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tg

FIXTURE = {
    "built": "2026-07-14",
    "players": {
        "baez|s": {"first_serve_pct": 0.73, "first_serve_win_pct": 0.63,
                   "second_serve_win_pct": 0.51, "tour": "ATP"},
        "bublik|a": {"first_serve_pct": 0.60, "first_serve_win_pct": 0.78,
                     "second_serve_win_pct": 0.55, "tour": "ATP"},
        "davidovich fokina|a": {"first_serve_pct": 0.65, "first_serve_win_pct": 0.70,
                                "second_serve_win_pct": 0.52, "tour": "ATP"},
    },
}


def _patch(monkeypatch):
    monkeypatch.setattr(tg, "load", lambda: FIXTURE)


def test_point_prob_is_pure_arithmetic():
    p = tg.point_prob(FIXTURE["players"]["baez|s"])
    assert abs(p - (0.73 * 0.63 + 0.27 * 0.51)) < 1e-9


def test_hold_prob_known_values():
    assert tg.hold_prob(0.5) == 0.5                    # symmetric game
    # server winning 100% / 0% of points holds always / never
    assert tg.hold_prob(0.999) > 0.999
    assert tg.hold_prob(0.001) < 0.001
    # monotonic in p
    assert tg.hold_prob(0.65) > tg.hold_prob(0.60) > tg.hold_prob(0.55)


def test_symmetric_players_near_coinflip(monkeypatch):
    _patch(monkeypatch)
    sim = tg.simulate_match(0.62, 0.62, n_sims=6000)
    assert abs(sim["match_prob_a"] - 0.5) < 0.03


def test_stronger_server_is_favorite_and_fewer_games(monkeypatch):
    _patch(monkeypatch)
    sim = tg.simulate_match(0.68, 0.58, n_sims=6000)
    assert sim["match_prob_a"] > 0.7
    # big gap -> shorter matches than an even, hold-heavy pairing
    even = tg.simulate_match(0.66, 0.66, n_sims=6000)
    assert (sum(sim["totals"]) / len(sim["totals"])
            < sum(even["totals"]) / len(even["totals"]))


def test_predict_totals_and_handicap_shapes(monkeypatch):
    _patch(monkeypatch)
    out = tg.predict("Alexander Bublik", "Sebastian Baez",
                     games_line=21.5, handicap_a=-3.5)
    assert out.get("error") is None
    gt = out["games_total"]
    assert abs(gt["p_over"] + gt["p_under"] + gt["p_push"] - 1.0) < 1e-6
    assert 0.0 < out["game_handicap"]["Alexander Bublik|a".lower() and
                                      f"bublik|a -3.5"] < 1.0
    assert abs(sum(out["match_prob"].values()) - 1.0) < 1e-6


def test_name_matching_surname_first_and_accents(monkeypatch):
    _patch(monkeypatch)
    out = tg.predict("Báez, Sebastián", "Davidovich Fokina, Alejandro", games_line=22.5)
    assert out.get("error") is None
    assert out["player_a"] == "baez|s"


def test_unknown_player_refuses(monkeypatch):
    _patch(monkeypatch)
    out = tg.predict("Sebastian Baez", "John Nobody")
    assert out["error"] == "NO_DATA"
    assert "John Nobody" in out["missing_players"]


def test_calibration_moves_match_prob_to_target(monkeypatch):
    _patch(monkeypatch)
    out = tg.predict("Sebastian Baez", "Alexander Bublik",
                     target_match_prob_a=0.70)
    assert abs(out["match_prob"]["baez|s"] - 0.70) < 0.05
    assert out["calibration_delta"] != 0.0


def test_deterministic_seed(monkeypatch):
    _patch(monkeypatch)
    a = tg.predict("Sebastian Baez", "Alexander Bublik", games_line=22.5)
    b = tg.predict("Sebastian Baez", "Alexander Bublik", games_line=22.5)
    assert a["games_total"] == b["games_total"]
