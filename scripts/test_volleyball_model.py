"""Tests for volleyball_model — pure math on a fixed ratings fixture (no network)."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import volleyball_model as vm
from fetch_volleyball_rankings import fit_logistic_scale, outcome_pairs

FIXTURE = {
    "meta": {"k_match": 0.017, "k_set": 0.010, "n_matches_fit": 3199,
             "favorite_accuracy": 0.762, "source": "test", "fetched_at": "t"},
    "men": {"Poland": {"rank": 1, "points": 380.0, "code": "POL"},
            "Bulgaria": {"rank": 15, "points": 274.0, "code": "BUL"}},
    "women": {"Italy": {"rank": 1, "points": 382.0, "code": "ITA"}},
}


def _patch(monkeypatch):
    monkeypatch.setattr(vm, "load", lambda: FIXTURE)


def test_higher_rated_team_is_favorite(monkeypatch):
    _patch(monkeypatch)
    out = vm.predict("Poland", "Bulgaria", "men")
    assert out["match_win_prob"]["Poland"] > 0.8       # 106-pt gap at k=0.017
    assert abs(sum(out["match_win_prob"].values()) - 1.0) < 1e-6


def test_set_score_probs_sum_to_one(monkeypatch):
    _patch(monkeypatch)
    out = vm.predict("Poland", "Bulgaria", "men")
    assert abs(sum(out["set_score_probs"].values()) - 1.0) < 1e-3


def test_set_handicap_consistent_with_score_dist(monkeypatch):
    _patch(monkeypatch)
    out = vm.predict("Poland", "Bulgaria", "men")
    d = out["set_score_probs"]
    assert abs(out["set_handicap"]["Poland -1.5"] - (d["3-0"] + d["3-1"])) < 1e-6


def test_unknown_team_refuses_no_estimate(monkeypatch):
    _patch(monkeypatch)
    out = vm.predict("Poland", "Narnia", "men")
    assert out["error"] == "NO_DATA"
    assert "Narnia" in out["missing_teams"]
    assert "match_win_prob" not in out


def test_gender_tables_are_separate(monkeypatch):
    _patch(monkeypatch)
    out = vm.predict("Italy", "Poland", "women")       # Poland only in men's table
    assert out["error"] == "NO_DATA"


def test_alias_turkey(monkeypatch):
    _patch(monkeypatch)
    fixture = {**FIXTURE, "women": {"Türkiye": {"rank": 4, "points": 350.0, "code": "TUR"},
                                    "Italy": {"rank": 1, "points": 382.0, "code": "ITA"}}}
    monkeypatch.setattr(vm, "load", lambda: fixture)
    out = vm.predict("Turkey", "Italy", "women")
    assert out.get("error") is None
    assert out["team_a"] == "Türkiye"


def test_missing_file_refuses(monkeypatch):
    monkeypatch.setattr(vm, "load", lambda: None)
    assert vm.predict("A", "B")["error"] == "NO_DATA"


# ── fitter unit tests (synthetic data, known answer) ─────────────────────────
def test_fit_recovers_known_scale():
    import random
    rng = random.Random(7)
    k_true = 0.02
    pairs = []
    for _ in range(4000):
        diff = rng.uniform(-150, 150)
        p = 1 / (1 + math.exp(-k_true * diff))
        pairs.append((diff, 1 if rng.random() < p else 0))
    k_fit = fit_logistic_scale(pairs)
    assert abs(k_fit - k_true) < 0.004


def test_outcome_pairs_parses_result_and_skips_junk():
    matches = [
        {"result": "3 - 1", "homeWRS": 300.0, "awayWRS": 250.0},
        {"result": "0 - 3", "homeWRS": 250.0, "awayWRS": 300.0},
        {"result": "n/a", "homeWRS": 1, "awayWRS": 2},          # skipped
        {"homeWRS": 1, "awayWRS": 2},                            # skipped
    ]
    mp, sp = outcome_pairs(matches)
    assert len(mp) == 2
    assert len(sp) == 4 + 3            # 3-1 gives 4 sets, 0-3 gives 3
    assert mp[0] == (50.0, 1)
