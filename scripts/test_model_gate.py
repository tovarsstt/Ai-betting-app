"""Tests for model_gate.py — rule 30 enforced in code, not asserted in prose.

Rule 30 was written into a markdown file, labelled BLOCKING, and enforced
nowhere; the engine kept emitting standalone model picks. These tests exist so
that cannot silently happen again.
"""
import argparse

import pytest

import bank_builder as bb
import edge_api as e
import kill_test as kt
import model_gate as mg
from edge_api import predict_soccer, SoccerMarketReq

FAILING = {
    "results": {
        "soccer_close": {"vs_market": {"model_brier": 0.6018, "market_brier": 0.5850},
                         "betting": {"roi": -0.096}},
        "tennis_atp": {"vs_market": {"model_brier": 0.2272, "market_brier": 0.2140},
                       "betting": {"roi": -0.052}},
        "tennis_wta": {"vs_market": {"model_brier": 0.2169, "market_brier": 0.2009},
                       "betting": {"roi": -0.170}},
    }
}
PASSING = {
    "results": {
        "soccer_close": {"vs_market": {"model_brier": 0.500, "market_brier": 0.585},
                         "betting": {"roi": 0.04}},
    }
}


@pytest.fixture
def failing(monkeypatch):
    monkeypatch.setattr(mg, "_load", lambda: FAILING)
    mg._CACHE = FAILING


@pytest.fixture
def passing(monkeypatch):
    monkeypatch.setattr(mg, "_load", lambda: PASSING)


# ── The block itself ───────────────────────────────────────────────────────

def test_measured_loser_is_blocked(failing):
    assert mg.allows_standalone("SOCCER") is False
    assert mg.allows_standalone("TENNIS") is False


def test_unmeasured_sport_is_NOT_blocked(failing):
    """Absence of evidence is not evidence of failure — blocking everything
    would make the gate useless and invite someone to switch it off."""
    assert mg.allows_standalone("NBA") is True
    assert mg.status("NBA")["measured"] is False


def test_a_model_that_beats_the_price_is_allowed(passing):
    """The gate must be able to OPEN, or it is just a hardcoded refusal."""
    assert mg.allows_standalone("SOCCER") is True


def test_losing_roi_blocks_even_if_brier_is_better(monkeypatch):
    """Better calibration does not license a negative-ROI bet."""
    monkeypatch.setattr(mg, "_load", lambda: {"results": {"soccer_close": {
        "vs_market": {"model_brier": 0.50, "market_brier": 0.58},
        "betting": {"roi": -0.03}}}})
    assert mg.allows_standalone("SOCCER") is False


def test_tennis_blocked_if_EITHER_tour_fails(monkeypatch):
    monkeypatch.setattr(mg, "_load", lambda: {"results": {
        "tennis_atp": {"vs_market": {"model_brier": 0.20, "market_brier": 0.21},
                       "betting": {"roi": 0.02}},
        "tennis_wta": {"vs_market": {"model_brier": 0.2169, "market_brier": 0.2009},
                       "betting": {"roi": -0.17}}}})
    assert mg.allows_standalone("TENNIS") is False


# ── What the gate does to a payload ────────────────────────────────────────

def test_gate_removes_the_call_to_action(failing):
    out = mg.gate("SOCCER", {"bet_signal": "HOME_WIN", "edge_strength": "STRONG",
                             "home_true_prob": 0.61})
    assert out["bet_signal"] == "NO_BET_MODEL_UNVALIDATED"
    assert out["edge_strength"] == "BLOCKED"


def test_gate_keeps_the_numbers_for_comparison(failing):
    """Description is still allowed — it is staking money that is not."""
    out = mg.gate("SOCCER", {"bet_signal": "HOME_WIN", "home_true_prob": 0.61})
    assert out["home_true_prob"] == 0.61
    assert out["bet_signal_model"] == "HOME_WIN"      # what the model said, kept


def test_gate_leaves_an_allowed_sport_untouched(failing):
    out = mg.gate("NBA", {"bet_signal": "HOME_WIN", "edge_strength": "STRONG"})
    assert out["bet_signal"] == "HOME_WIN"
    assert out["edge_strength"] == "STRONG"


def test_gate_does_not_invent_a_signal_where_there_was_none(failing):
    out = mg.gate("SOCCER", {"bet_signal": "NO_DATA"})
    assert out["bet_signal"] == "NO_DATA"


# ── The staking paths ──────────────────────────────────────────────────────

def _cand(sport, prob=0.62, dec=1.90):
    return {"sport": sport, "match": f"{sport} match", "selection": f"{sport} pick",
            "pick": f"{sport} pick", "prob": prob, "decimal": dec}


def test_blocked_sport_cannot_become_a_parlay_leg(failing):
    assert bb._leg_ok(_cand("SOCCER")) is False
    assert bb._leg_ok(_cand("NBA")) is True


def test_blocked_sport_cannot_become_a_kelly_single(failing):
    out = bb.strong_singles([_cand("SOCCER", 0.65, 1.95), _cand("NBA", 0.65, 1.95)], 200)
    assert [s["selection"] for s in out] == ["NBA pick"]


def test_filter_candidates_reports_what_it_dropped(failing):
    kept, dropped = mg.filter_candidates([_cand("SOCCER"), _cand("NBA")])
    assert len(kept) == 1 and len(dropped) == 1


# ── day_card — the LIVE day card the UI actually calls ────────────────────────
# candidates_from_slate/candidates_from_2way used to build candidate dicts with
# NO "sport" key at all, so _leg_ok's gate.allows_standalone(c.get("sport") or
# "") always saw "" (unmeasured -> allowed) no matter what the live slate's
# sport actually was. The gate code above was correct and fully tested, but
# the real caller never fed it a sport — soccer's day card kept shipping
# tickets and singles from a model measured losing to the market.

SOCCER_GAME = {"name": "Brasil v Chile", "h2h": [1.45, 4.60, 8.00],
               "totals": [[2.5, 1.85, 1.95]], "btts": [1.90, 1.85]}
# best price 1.75 vs ~64.3% pinnacle-devigged fair clears +5% EV — a real
# single when the gate is open, so an empty result under `failing` is the
# gate's doing, not just a thin board.
TENNIS_GAME = {"name": "A v B", "home": "A", "away": "B",
               "pinnacle": [1.50, 2.70], "best": [1.75, 2.70]}


def test_soccer_day_card_candidates_are_tagged_for_the_gate():
    cands = bb.candidates_from_slate([SOCCER_GAME])
    assert cands and all(c["sport"] == "SOCCER" for c in cands)


def test_tennis_day_card_candidates_are_tagged_for_the_gate():
    cands = bb.candidates_from_2way([TENNIS_GAME], sport_key="tennis")
    assert cands and all(c["sport"] == "TENNIS" for c in cands)


def test_live_soccer_day_card_produces_nothing_when_blocked(failing):
    card = bb.day_card([SOCCER_GAME], bankroll=200.0)      # mode="soccer" default
    assert card["tickets"] == []
    assert card["singles"] == []
    assert all(r["verdict"] == "NO_BET" for r in card["per_match"])
    assert all("rule 30" in r["model_gate"] for r in card["per_match"])


def test_live_tennis_day_card_produces_nothing_when_blocked(failing):
    card = bb.day_card([TENNIS_GAME], bankroll=200.0, mode="2way", sport_key="tennis")
    assert card["tickets"] == []
    assert card["singles"] == []
    assert all(r["verdict"] == "NO_BET" for r in card["per_match"])


def test_live_soccer_day_card_untouched_when_soccer_passes(passing):
    card = bb.day_card([SOCCER_GAME], bankroll=200.0)
    assert any(r["verdict"] != "NO_BET" or "model_gate" not in r
               for r in card["per_match"])


def test_live_tennis_day_card_ships_the_single_when_tennis_passes(monkeypatch):
    monkeypatch.setattr(mg, "_load", lambda: {"results": {}})   # tennis unmeasured
    card = bb.day_card([TENNIS_GAME], bankroll=200.0, mode="2way", sport_key="tennis")
    assert card["singles"]


def test_nba_day_card_unaffected_by_soccer_tennis_failing(failing):
    """An unmeasured sport must not get caught by a neighboring sport's block."""
    # pinnacle fair ~64.3% on the favourite; best price 1.75 clears +5% EV —
    # a real single, so an empty result here could only be the gate's doing.
    nba_game = {"name": "Lakers v Celtics", "home": "Lakers", "away": "Celtics",
                "pinnacle": [1.50, 2.70], "best": [1.75, 2.70]}
    card = bb.day_card([nba_game], bankroll=200.0, mode="2way", sport_key="basketball_nba")
    assert card["singles"]


# ── /predict-soccer — the main soccer engine, gated same as /predict ──────────

def _soccer_req():
    return SoccerMarketReq(home_team="Madeupland", away_team="Nowhereia",
                            home_odds=-110, draw_odds=240, away_odds=300)


def test_predict_soccer_blocks_the_recommendation(failing):
    r = predict_soccer(_soccer_req())
    assert r["model_gate"]["standalone_allowed"] is False
    assert r["recommendation"] is None
    assert r["recommendation_model"]["primary_pick"]["market"]
    assert r["market_recommendation"] is None
    assert r["market_recommendation_model"]["primary_pick"]["market"]
    assert r["most_likely_pick"] is None
    assert r["most_likely_pick_model"]["market"]
    assert "gate_note" in r


def test_predict_soccer_keeps_the_markets_for_comparison(failing):
    """Description survives the gate — only the call to action is removed."""
    r = predict_soccer(_soccer_req())
    assert r["markets"]["1x2"]["home"] > 0
    assert r["simulated_ladder"]


def test_predict_soccer_untouched_when_soccer_passes(passing):
    r = predict_soccer(_soccer_req())
    assert r["model_gate"]["standalone_allowed"] is True
    assert r["recommendation"] is not None
    assert "recommendation_model" not in r


# ── kill_test.py — the every-engine CLI report, checked separately from the ──
# ── /predict-soccer endpoint because it builds its OWN BET/thin/PASS ladder ──
# from the raw priced markets rather than reading bet_signal/recommendation.
# A gate that only edits the JSON response is invisible here unless kill_test
# is taught to read model_gate itself — this is that wiring, verified.

def _kt_ns(**kw):
    base = dict(home="Spain", away="Argentina", home_venue=False,
                price_home=2.27, price_draw=3.00, price_away=3.55, json=False)
    return argparse.Namespace(**{**base, **kw})


def test_kill_test_soccer_shows_rule_30_and_blocks_verdicts(failing, capsys):
    kt.soccer(_kt_ns())
    out = capsys.readouterr().out
    assert "RULE 30" in out
    assert "BLOCKED(r30)" in out
    assert " BET" not in out           # no live call-to-action leaks through


def test_kill_test_soccer_untouched_when_soccer_passes(passing, capsys):
    kt.soccer(_kt_ns())
    out = capsys.readouterr().out
    assert "RULE 30" not in out
    assert "BLOCKED(r30)" not in out
