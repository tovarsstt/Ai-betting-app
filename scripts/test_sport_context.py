"""Tests for tennis_style.py and pace_profile.py — per-sport measured context.

Same discipline as team_style: below the sample floor these return None, never
a softer-sounding number. A 3-match grass record is not a grass preference.
"""
import pytest

import pace_profile as pp
import tennis_style as tsty


# ── Tennis ─────────────────────────────────────────────────────────────────

def _tm(winner, loser, surface="Hard", court="Outdoor", series="ATP250",
        rnd="1st Round", best_of=3, sets=((6, 4), (6, 3))):
    return {"winner": winner, "loser": loser, "surface": surface,
            "court": court, "series": series, "round": rnd,
            "best_of": best_of, "sets": [tuple(s) for s in sets], "year": 2026}


TENNIS = (
    [_tm("Ace", "Foe") for _ in range(12)]
    + [_tm("Foe", "Ace", surface="Clay") for _ in range(8)]
    # Tiebreak sets and a decider, for the nerve read.
    + [_tm("Ace", "Foe", sets=((7, 6), (6, 7), (7, 6))) for _ in range(6)]
    + [_tm("Ace", "Other", court="Indoor") for _ in range(6)]
)


@pytest.fixture(autouse=True)
def stub_tennis(monkeypatch):
    monkeypatch.setattr(tsty, "load_matches", lambda tour="atp", years=None: TENNIS)


def test_player_with_too_few_matches_is_refused():
    assert tsty.profile("Ghost") is None


def test_losses_are_counted_from_the_players_own_side():
    p = tsty.profile("Ace")
    assert p["overall"]["w"] == 24 and p["overall"]["l"] == 8


def test_surface_split_is_measured():
    p = tsty.profile("Ace")
    assert p["by_surface"]["Clay"]["win_pct"] == 0.0      # lost all 8 on clay
    assert p["by_surface"]["Hard"]["win_pct"] > 0.9


def test_thin_split_reports_n_and_no_rate():
    """A 3-match grass record must not read as a grass preference."""
    rows = TENNIS + [_tm("Ace", "Foe", surface="Grass") for _ in range(3)]
    p = tsty.profile("Ace", years=None) if False else None
    out = tsty._split(tsty._player_rows("Ace", rows), "surface")
    assert out["Grass"]["win_pct"] is None
    assert "too few" in out["Grass"]["note"]


def test_indoor_outdoor_is_split():
    p = tsty.profile("Ace")
    assert "Indoor" in p["by_court"] and "Outdoor" in p["by_court"]


def test_tiebreaks_counted_from_set_scores():
    p = tsty.profile("Ace")
    tb = p["nerve"]["tiebreaks"]
    assert tb["played"] == 18          # 6 matches x 3 tiebreak sets
    assert tb["won"] == 12             # won 2 of 3 in each


def test_deciding_sets_are_identified():
    p = tsty.profile("Ace")
    assert p["nerve"]["deciding_sets"]["n"] == 6


def test_shape_reports_straight_sets_and_games():
    p = tsty.profile("Ace")
    assert 0.0 <= p["shape"]["straight_set_win_pct"] <= 1.0
    assert p["shape"]["games_per_bo3_match"] > 0


def test_matchup_names_the_player_it_could_not_measure():
    out = tsty.matchup("Ace", "Ghost")
    assert out["b"] is None and "Ghost" in out["note"]


def test_tennis_context_is_labelled_description():
    assert "not prediction" in tsty.profile("Ace")["source"]


# ── Period sports ──────────────────────────────────────────────────────────

def _pg(home, away, hp, ap, ot=False):
    return {"date": "2026-01-01", "home": home, "away": away,
            "home_periods": [float(x) for x in hp],
            "away_periods": [float(x) for x in ap], "ot": ot}


PACE = {"regulation_periods": 4, "ot_rate": 0.05,
        "games": ([_pg("Fast", "Slow", [30, 30, 30, 20], [25, 25, 25, 25])
                   for _ in range(12)]
                  + [_pg("Slow", "Fast", [20, 20, 20, 20], [28, 28, 28, 18])
                     for _ in range(6)])}


@pytest.fixture(autouse=True)
def stub_pace(monkeypatch):
    monkeypatch.setattr(pp, "load", lambda sport: PACE)


def test_team_with_too_few_games_is_refused():
    assert pp.profile("Nobody", "nba") is None


def test_pace_is_oriented_to_the_team():
    """'Points for' must follow the team into the away column."""
    f = pp.profile("Fast", "nba")
    assert f["games"] == 18
    assert f["pace"]["points_for_pg"] > f["pace"]["points_against_pg"]


def test_period_shares_sum_to_one():
    f = pp.profile("Fast", "nba")
    shares = [p["share_of_own_points"] for p in f["period_shape"]]
    assert sum(shares) == pytest.approx(1.0, abs=0.01)


def test_start_close_split_is_detected():
    """Fast scores 30/30/30 then 20 — it starts better than it closes."""
    f = pp.profile("Fast", "nba")
    assert "starts faster" in f["start_and_close"]["reads"]


def test_variance_is_reported_with_its_reason():
    f = pp.profile("Fast", "nba")
    assert f["variance"]["game_total_sd"] >= 0
    assert "worse bet at the same price" in f["variance"]["note"]


def test_league_shape_gives_the_baseline():
    lg = pp.league_shape("nba")
    assert lg["games"] == 18
    assert len(lg["period_totals"]) == 4
    assert lg["league_total_pg"] > 0


def test_matchup_names_the_side_it_could_not_measure():
    out = pp.matchup("Fast", "Nobody", "nba")
    assert out["away"] is None and "Nobody" in out["note"]


def test_pace_is_labelled_description():
    assert "not prediction" in pp.profile("Fast", "nba")["source"]
