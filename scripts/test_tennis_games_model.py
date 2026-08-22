"""Tests for tennis_games_model — exact hold math + simulation properties."""
import sys
from pathlib import Path

import pytest

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


# ── In-play pricing from the live GAME score (added 2026-08-19) ─────────────
# `tennis_live.live_win_prob` only ever used the SET score, so a player 4-3 up
# in the opening set got ZERO adjustment (sets still 0-0) — on a real live
# ticket that understated Keys by ~9 points and Gauff by ~19.

import random


def _holds(a=0.68, b=0.60):
    return a, b


def test_leading_in_the_current_set_raises_match_prob():
    pa, pb = _holds()
    flat = tg.live_state_probs(pa, pb, 0, 0, 0, 0, 0, n_sims=8000)
    ahead = tg.live_state_probs(pa, pb, 0, 0, 4, 1, 0, n_sims=8000)
    assert ahead["match_prob_a"] > flat["match_prob_a"]


def test_zero_zero_sets_still_moves_on_games():
    """The exact bug: sets 0-0 used to mean 'no live information'."""
    behind = tg.live_state_probs(*_holds(), 0, 0, 1, 5, 0, n_sims=8000)
    ahead = tg.live_state_probs(*_holds(), 0, 0, 5, 1, 0, n_sims=8000)
    assert ahead["match_prob_a"] - behind["match_prob_a"] > 0.25


def test_a_set_up_beats_level():
    level = tg.live_state_probs(*_holds(), 0, 0, 0, 0, 0, n_sims=8000)
    set_up = tg.live_state_probs(*_holds(), 1, 0, 0, 0, 0, n_sims=8000)
    assert set_up["match_prob_a"] > level["match_prob_a"]


def test_wins_a_set_is_certain_once_a_set_is_banked():
    out = tg.live_state_probs(*_holds(), 1, 0, 0, 0, 0, n_sims=4000)
    assert out["a_wins_a_set"] == 1.0


def test_trailing_player_can_still_win_a_set():
    # Borges' actual position: lost set 1, leading 4-3 in set 2.
    out = tg.live_state_probs(*_holds(), 0, 1, 4, 3, 0, n_sims=8000)
    assert 0.5 < out["a_wins_a_set"] < 1.0
    assert out["set_in_progress_prob_a"] > 0.5


def test_decided_match_short_circuits():
    out = tg.live_state_probs(*_holds(), 2, 0, 0, 0, 0, n_sims=8000)
    assert out["decided"] is True
    assert out["match_prob_a"] == 1.0


def test_set_from_an_arbitrary_score_can_finish_immediately():
    rng = random.Random(1)
    w, ga, gb, _ = tg._sim_set_from(0.68, 0.6, rng, 0, 6, 3)
    assert (w, ga, gb) == (0, 6, 3)      # already won, reported as-is


def test_set_from_score_respects_the_two_game_margin():
    rng = random.Random(2)
    for _ in range(30):
        w, ga, gb, _ = tg._sim_set_from(0.68, 0.6, rng, 0, 5, 5)
        assert max(ga, gb) >= 6
        assert abs(ga - gb) >= 2 or max(ga, gb) == 7   # 7-6 tiebreak


# ── SET handicap vs GAMES handicap (the market mix-up that cost real money) ──
# A book lists "Handicap de Set -1.5" next to "Handicap de Juego -1.5". They are
# ~24 points apart in win probability. Both must always be emitted and named.

def _sab(monkeypatch):
    _patch(monkeypatch)
    return tg.predict("Alexander Bublik", "Sebastian Baez", games_line=21.5, handicap_a=-4.5,
                      best_of=3, target_match_prob_a=0.80)


def test_set_handicap_is_always_emitted(monkeypatch):
    # Even with no handicap argument at all — silence is what caused the mix-up.
    _patch(monkeypatch)
    out = tg.predict("Alexander Bublik", "Sebastian Baez", best_of=3, target_match_prob_a=0.80)
    assert "set_handicap" in out
    assert out["set_handicap"]["a_minus_1_5_sets"] is not None


def test_minus_1_5_sets_is_strictly_harder_than_winning(monkeypatch):
    out = _sab(monkeypatch)
    sh = out["set_handicap"]
    # Winning the match includes 2-1 wins; the handicap does not.
    assert sh["a_minus_1_5_sets"] < out["match_prob"][out["player_a"]]
    assert sh["a_wins_match_but_loses_handicap"] > 0


def test_set_handicap_carries_the_warning_note(monkeypatch):
    note = _sab(monkeypatch)["set_handicap"]["note"]
    assert "2-1" in note and "GAMES" in note


def test_set_and_games_handicaps_are_materially_different(monkeypatch):
    """The whole point: -1.5 SETS and -1.5 GAMES are not the same bet."""
    out = _sab(monkeypatch)
    sets_15 = out["set_handicap"]["a_minus_1_5_sets"]
    games_15 = out["game_handicap_ladder"]["-1.5"]
    assert games_15 - sets_15 > 0.10


def test_games_handicap_ladder_is_monotonic(monkeypatch):
    # Giving away MORE games can never be more likely to cover.
    lad = _sab(monkeypatch)["game_handicap_ladder"]
    lines = sorted(lad, key=lambda k: float(k))       # -6.5 ... -1.5
    probs = [lad[k] for k in lines]
    assert probs == sorted(probs)                      # rises as the line shrinks


def test_both_players_set_handicaps_are_reported(monkeypatch):
    sh = _sab(monkeypatch)["set_handicap"]
    assert sh["a_minus_1_5_sets"] > sh["b_minus_1_5_sets"]
    assert sh["b_minus_1_5_sets"] >= 0


# ── Games-total calibration (measured 2026-08-21 on 3,172 bo3 matches) ──────
# The raw simulation ran ~1.7-2.2 games LONG, flat across match imbalance. That
# turned a real 52.7% over into a priced 70.2% and cost a settled bet.

def test_offset_is_zero_without_a_calibration_file(monkeypatch, tmp_path):
    monkeypatch.setattr(tg, "CALIB_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(tg, "_CALIB", None)
    assert tg.totals_offset("ATP") == 0.0     # never a guessed correction


def test_offset_is_read_per_tour(monkeypatch):
    monkeypatch.setattr(tg, "_CALIB", {"tours": {
        "atp": {"offset_games": -1.7}, "wta": {"offset_games": -2.15}}})
    assert tg.totals_offset("ATP") == -1.7
    assert tg.totals_offset("wta") == -2.15
    assert tg.totals_offset("ITF") == 0.0     # unknown tour -> no correction
    assert tg.totals_offset(None) == 0.0


def test_calibration_shifts_expected_total(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": 0.0}}})
    raw = tg.predict("Alexander Bublik", "Sebastian Baez", best_of=3)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": -2.0}}})
    cal = tg.predict("Alexander Bublik", "Sebastian Baez", best_of=3)
    assert cal["expected_total_games"] == pytest.approx(
        raw["expected_total_games"] - 2.0, abs=0.01)


def test_calibration_moves_the_over_probability_too(monkeypatch):
    """expected_total and the over/under must move TOGETHER — a shifted mean
    with unshifted probabilities would be worse than no calibration at all."""
    _patch(monkeypatch)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": 0.0}}})
    raw = tg.predict("Alexander Bublik", "Sebastian Baez", games_line=21.5, best_of=3)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": -2.0}}})
    cal = tg.predict("Alexander Bublik", "Sebastian Baez", games_line=21.5, best_of=3)
    assert cal["games_total"]["p_over"] < raw["games_total"]["p_over"]


def test_calibration_is_reported_on_every_prediction(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": -1.7}}})
    out = tg.predict("Alexander Bublik", "Sebastian Baez", best_of=3)
    c = out["totals_calibration"]
    assert c["offset_games"] == -1.7 and c["tour"] == "ATP"


def test_over_and_under_still_sum_to_one(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(tg, "_CALIB", {"tours": {"atp": {"offset_games": -1.7}}})
    gt = tg.predict("Alexander Bublik", "Sebastian Baez",
                    games_line=21.5, best_of=3)["games_total"]
    assert gt["p_over"] + gt["p_under"] + gt["p_push"] == pytest.approx(1.0, abs=0.01)
