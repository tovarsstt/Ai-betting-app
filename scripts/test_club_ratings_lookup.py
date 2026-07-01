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
