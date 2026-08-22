"""Tests for edge_api._club_lambdas — the per-league club-ratings fallback
used by /predict-soccer when there's no market odds and neither team is a
national team in the international fit."""
import edge_api as e


def _set_club_ratings(leagues=None):
    e.CLUB_SOCCER_RATINGS.clear()
    e.CLUB_SOCCER_RATINGS.update({"leagues": leagues or {}})


PREM = {
    "mu": 0.2, "home_advantage": 0.15,
    "teams": {
        "Arsenal": {"attack": 0.3, "defense": 0.5},
        "Chelsea": {"attack": 0.2, "defense": 0.3},
    },
}
LIGA = {
    "mu": 0.1, "home_advantage": 0.1,
    "teams": {
        "Barcelona": {"attack": 0.7, "defense": 0.3},
    },
}


def test_returns_none_when_no_league_has_both_teams():
    _set_club_ratings({"Premier League": PREM, "La Liga": LIGA})
    lambdas, league = e._club_lambdas("Arsenal", "Barcelona", neutral=False)
    assert lambdas is None and league is None


def test_finds_lambdas_when_both_teams_share_a_league():
    _set_club_ratings({"Premier League": PREM, "La Liga": LIGA})
    lambdas, league = e._club_lambdas("Arsenal", "Chelsea", neutral=False)
    assert league == "Premier League"
    assert lambdas is not None
    lh, la = lambdas
    assert lh > 0 and la > 0


def test_neutral_venue_drops_home_advantage():
    _set_club_ratings({"Premier League": PREM})
    (lh_neutral, _), _ = e._club_lambdas("Arsenal", "Chelsea", neutral=True)
    (lh_home, _), _ = e._club_lambdas("Arsenal", "Chelsea", neutral=False)
    assert lh_neutral < lh_home  # home_advantage term dropped when neutral


def test_returns_none_with_empty_ratings_store():
    _set_club_ratings()
    lambdas, league = e._club_lambdas("Arsenal", "Chelsea", neutral=False)
    assert lambdas is None and league is None


def test_missing_team_in_the_only_league_returns_none():
    _set_club_ratings({"Premier League": PREM})
    lambdas, league = e._club_lambdas("Arsenal", "Real Madrid", neutral=False)
    assert lambdas is None and league is None


# ── Club name resolution (found 2026-08-21 mispricing Espanyol v Real Madrid) ─
# Fitted ratings key off football-data.co.uk's abbreviated names. A miss did not
# error — it fell through to the hand-tuned heuristic and produced a confident
# garbage price (Real Madrid 83.7% away at Espanyol).

import pytest


@pytest.fixture
def laliga():
    e.load_all()
    return e.CLUB_SOCCER_RATINGS["leagues"]["La Liga"]["teams"]


@pytest.fixture
def epl():
    e.load_all()
    return e.CLUB_SOCCER_RATINGS["leagues"]["Premier League"]["teams"]


@pytest.mark.parametrize("written,expected", [
    ("Espanyol", "Espanol"),
    ("Atletico Madrid", "Ath Madrid"),
    ("Atlético Madrid", "Ath Madrid"),      # accents stripped
    ("Real Sociedad", "Sociedad"),
    ("Rayo Vallecano", "Vallecano"),
    ("Athletic Bilbao", "Ath Bilbao"),
    ("Real Madrid", "Real Madrid"),          # exact still works
])
def test_spanish_club_names_resolve(written, expected, laliga):
    assert e.resolve_club(written, laliga) == expected


@pytest.mark.parametrize("written,expected", [
    ("Manchester United", "Man United"),
    ("Tottenham Hotspur", "Tottenham"),
    ("Nottingham Forest", "Nott'm Forest"),
])
def test_english_club_names_resolve(written, expected, epl):
    assert e.resolve_club(written, epl) == expected


def test_unknown_club_refuses(laliga):
    assert e.resolve_club("Nonexistent FC", laliga) is None
    assert e.resolve_club("", laliga) is None


def test_resolution_reaches_the_fitted_ratings_not_the_heuristic(laliga):
    """The actual bug: a name miss silently downgraded to a hand-tuned default."""
    lam, league = e._club_lambdas("Espanyol", "Real Madrid", neutral=False)
    assert league == "La Liga"
    assert lam is not None


def test_real_madrid_away_is_a_sane_favourite():
    """The heuristic priced Madrid at 83.7% away. The fitted model must not."""
    lam, _ = e._club_lambdas("Espanyol", "Real Madrid", neutral=False)
    lh, la = lam
    assert la > lh                 # Madrid the stronger side
    assert la / lh < 3.0           # but not absurdly so
