"""Tests for scripts/tennis_scanner.py — the standing board scanner.

Anchored on the 2026-08-19 Cincinnati board, where the value was NOT in any
moneyline but in the underdog games handicaps. The scanner must find those
without anyone looking for them.
"""
import pytest

import tennis_games_model as tg
import tennis_scanner as ts

FIXTURE = {
    "built": "2026-07-14",
    "players": {
        "baez|s": {"first_serve_pct": 0.73, "first_serve_win_pct": 0.63,
                   "second_serve_win_pct": 0.51, "tour": "ATP"},
        "bublik|a": {"first_serve_pct": 0.60, "first_serve_win_pct": 0.78,
                     "second_serve_win_pct": 0.55, "tour": "ATP"},
    },
}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(tg, "load", lambda: FIXTURE)


def _match(**over):
    m = {"player_a": "Alexander Bublik", "player_b": "Sebastian Baez",
         "match_prob_a": 0.80}
    m.update(over)
    return m


# ── It prices the whole board, not just the moneyline ───────────────────────

def test_scans_every_posted_market():
    out = ts.scan_board([_match(
        ml={"a": 1.20, "b": 4.50},
        games_handicap={"-3.5": {"a": 1.50, "b": 2.50}},
        games_total={"21.5": {"over": 1.90, "under": 1.90}},
        set_handicap={"-1.5": {"a": 1.60, "b": 2.30}},
        wins_a_set={"a": 1.05, "b": 1.70},
    )])
    markets = {r["market"] for r in out["all_markets"]}
    assert any("ML" in m for m in markets)
    assert any("games" in m and "OVER" not in m for m in markets)
    assert any("OVER" in m for m in markets)
    assert any("SETS" in m for m in markets)
    assert any("wins a set" in m for m in markets)


def test_prices_both_sides_of_a_handicap():
    """The dog side is where the real edge was — it must be priced, not skipped."""
    out = ts.scan_board([_match(games_handicap={"-3.5": {"a": 1.50, "b": 2.50}})])
    markets = [r["market"] for r in out["all_markets"]]
    assert any(m.startswith("Alexander Bublik -3.5") for m in markets)
    assert any("Sebastian Baez +3.5" in m for m in markets)


def test_unpriced_markets_are_skipped_not_invented():
    out = ts.scan_board([_match(ml={"a": 1.20})])       # no 'b' price
    assert not any(r["market"].startswith("Sebastian Baez ML")
                   for r in out["all_markets"])


# ── Gates: winning first, then EV ───────────────────────────────────────────

def test_negative_ev_never_surfaces_as_a_play():
    # Price far below the model's floor.
    out = ts.scan_board([_match(ml={"a": 1.01})])
    assert out["plays"] == []


def test_sub_coinflip_is_gated_out_even_at_fat_ev():
    """Winning is king — a 20% shot at +100% EV is not a play."""
    out = ts.scan_board([_match(ml={"b": 50.0})])       # huge price on the dog
    dog = [r for r in out["all_markets"] if "Baez ML" in r["market"]][0]
    assert dog["ev_pct"] > 50           # very +EV
    assert dog["win_prob"] < 0.5
    assert dog not in out["plays"]      # and still not surfaced


def test_plays_are_ranked_by_win_probability():
    out = ts.scan_board([_match(
        ml={"a": 1.60},
        games_handicap={"-1.5": {"a": 1.70}},
    )])
    probs = [p["win_prob"] for p in out["plays"]]
    assert probs == sorted(probs, reverse=True)


def test_best_is_the_highest_win_probability_play():
    out = ts.scan_board([_match(ml={"a": 1.60}, games_handicap={"-1.5": {"a": 1.70}})])
    if out["plays"]:
        assert out["best"]["win_prob"] == max(p["win_prob"] for p in out["plays"])


def test_gates_are_configurable():
    board = [_match(ml={"a": 1.30})]
    strict = ts.scan_board(board, min_ev=0.99)
    assert strict["plays"] == []


# ── Set handicap stays distinguishable from the games handicap ──────────────

def test_set_handicap_is_labelled_must_win_2_0():
    out = ts.scan_board([_match(set_handicap={"-1.5": {"a": 1.60}})])
    row = [r for r in out["all_markets"] if "SETS" in r["market"]][0]
    assert "must win 2-0" in row["market"]
    assert "2-1 win LOSES" in row["note"]


def test_set_and_games_handicap_get_different_probabilities():
    out = ts.scan_board([_match(
        games_handicap={"-1.5": {"a": 1.60}},
        set_handicap={"-1.5": {"a": 1.60}},
    )])
    games = [r for r in out["all_markets"] if r["market"].endswith("-1.5 games")][0]
    sets = [r for r in out["all_markets"] if "SETS" in r["market"]][0]
    assert games["win_prob"] != sets["win_prob"]


# ── Honesty when there is no data ───────────────────────────────────────────

def test_unknown_player_yields_no_opinion_not_a_guess():
    out = ts.scan_board([{"player_a": "Nobody Atall", "player_b": "Also Nobody",
                          "ml": {"a": 1.5, "b": 2.5}}])
    assert out["plays"] == []
    assert out["no_opinion"]
    assert out["no_opinion"][0]["error"] == "NO_DATA"


def test_a_dead_match_does_not_kill_the_board():
    out = ts.scan_board([
        {"player_a": "Nobody Atall", "player_b": "Also Nobody", "ml": {"a": 1.5}},
        _match(ml={"a": 1.60}),
    ])
    assert out["no_opinion"]                 # one refused
    assert out["scanned_markets"] > 0        # the other still priced


def test_empty_board_is_safe():
    out = ts.scan_board([])
    assert out["plays"] == [] and out["best"] is None


# ── min_odds is the actionable number ───────────────────────────────────────

def test_min_odds_is_the_break_even_price():
    out = ts.scan_board([_match(ml={"a": 1.60})])
    row = [r for r in out["all_markets"] if "Bublik ML" in r["market"]][0]
    assert row["min_odds"] == pytest.approx(1.05 / row["win_prob"], rel=1e-2)


def test_a_play_always_beats_its_own_floor():
    out = ts.scan_board([_match(
        ml={"a": 1.60}, games_handicap={"-1.5": {"a": 1.70, "b": 2.40}})])
    for p in out["plays"]:
        assert p["price"] >= p["min_odds"]
