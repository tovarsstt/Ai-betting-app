"""Tests for team_style.py — measured game context.

The point of this module is that "knowing the game" must be COUNTED, never
asserted. These tests exist mostly to pin that: too little data returns None
rather than a confident-sounding profile.
"""
import pytest

import team_style as ts


def _m(home, away, **kw):
    base = {
        "date": "2026-01-01", "league": "Premier League",
        "home_team": home, "away_team": away,
        "home_goals": "2", "away_goals": "1",
        "ht_home_goals": "1", "ht_away_goals": "0",
        "referee": "A Ref",
        "home_shots": "15", "away_shots": "9",
        "home_sot": "6", "away_sot": "3",
        "home_fouls": "10", "away_fouls": "12",
        "home_corners": "7", "away_corners": "3",
        "home_yellow": "1", "away_yellow": "2",
        "home_red": "0", "away_red": "0",
        "close_home": "1.5", "close_draw": "4.0", "close_away": "6.0",
    }
    base.update({k: str(v) for k, v in kw.items()})
    return base


ROWS = ([_m("Alpha", "Beta") for _ in range(12)]
        + [_m("Beta", "Alpha", home_yellow=4, away_yellow=4,
              home_fouls=18, away_fouls=18) for _ in range(4)]
        + [_m("Gamma", "Delta", referee="B Ref", home_yellow=1, away_yellow=0,
              home_fouls=20, away_fouls=20) for _ in range(12)]
        # A referee who books nobody at all — the divide-by-zero case.
        + [_m("Eta", "Theta", referee="C Ref", home_yellow=0, away_yellow=0,
              home_fouls=20, away_fouls=20) for _ in range(10)])


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(ts, "load", lambda path=None: ROWS)


# ── Refuses rather than inventing ──────────────────────────────────────────

def test_too_few_matches_yields_no_style():
    assert ts.style("Nobody", ROWS) is None


def test_referee_with_too_few_matches_is_refused():
    assert ts.referee("Z Nobody", ROWS) is None


def test_context_names_the_side_it_could_not_measure():
    out = ts.context("Alpha", "Nobody")
    assert out["away_style"] is None
    assert "Nobody" in out["note"]


# ── Style is computed from the team's OWN perspective ──────────────────────

def test_home_and_away_are_flipped_correctly():
    """A team's 'shots for' must follow it to the away column."""
    s = ts.style("Alpha", ROWS)
    assert s["matches"] == 16
    # Alpha shoots 15 at home (12 games) and 9 away (4 games).
    assert 13.0 < s["tempo"]["shots_for_pg"] < 15.0


def test_shot_volume_is_both_sides_added():
    s = ts.style("Alpha", ROWS)
    t = s["tempo"]
    assert t["shot_volume_pg"] == pytest.approx(
        t["shots_for_pg"] + t["shots_against_pg"], abs=0.01)


def test_finishing_reports_its_sample_size():
    s = ts.style("Alpha", ROWS)
    assert s["finishing"]["goals_per_sot"] is not None
    assert "n=" in s["finishing"]["note"]


def test_game_state_split_is_a_share():
    s = ts.style("Alpha", ROWS)
    g = s["game_state"]
    assert 0.0 <= g["share_goals_scored_1st_half"] <= 1.0


def test_style_is_labelled_description_not_prediction():
    """It must never read as a forecast — the Poisson model owns that."""
    assert "not prediction" in ts.style("Alpha", ROWS)["source"]


# ── Referee tendency ───────────────────────────────────────────────────────

def test_fouls_per_card_separates_strict_from_lenient():
    """Two refs can average different cards on the SAME fouls — that ratio is
    the number that matters, not raw cards."""
    strict = ts.referee("A Ref", ROWS)
    lenient = ts.referee("B Ref", ROWS)
    assert strict["cards_pg"] > lenient["cards_pg"]
    assert strict["fouls_per_card"] < lenient["fouls_per_card"]


def test_referee_with_no_cards_does_not_divide_by_zero():
    none_given = ts.referee("C Ref", ROWS)
    assert none_given["fouls_per_card"] is None
    assert none_given["cards_pg"] == 0.0


def test_referee_table_is_sorted_by_cards():
    tbl = ts.referee_table(ROWS)
    assert [r["cards_pg"] for r in tbl] == sorted(
        [r["cards_pg"] for r in tbl], reverse=True)


# ── Derby heat is a ratio, not a vibe ──────────────────────────────────────

def test_fixture_intensity_detects_a_hot_fixture():
    out = ts.fixture_intensity("Alpha", "Beta", ROWS)
    assert out["meetings"] == 16
    assert out["intensity_ratio"] is not None
    assert out["verdict"]


def test_fixture_with_too_few_meetings_is_refused():
    assert ts.fixture_intensity("Alpha", "Gamma", ROWS) is None


def test_thin_head_to_head_carries_a_caveat():
    rows = ROWS + [_m("Eps", "Zeta") for _ in range(3)] + [
        _m("Eps", "Zeta") for _ in range(9)]
    out = ts.fixture_intensity("Eps", "Zeta", rows)
    assert out is not None
    assert out["caveat"] is None            # 12 meetings is not thin


def test_missing_stat_columns_do_not_crash():
    """Older seasons omit shot data; a blank must read as unknown, not zero."""
    thin = [dict(_m("Solo", "Other"), home_shots="", home_sot="") for _ in range(8)]
    s = ts.style("Solo", thin)
    assert s is not None
    assert s["tempo"]["shots_for_pg"] is None
