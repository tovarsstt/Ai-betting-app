"""Test for fit_club_ratings.py's grouping logic — the one new piece of glue
beyond poisson_regression.py/eigen_ratings.py, which already have their own
thorough test suites."""
from fit_club_ratings import _by_league


def test_by_league_groups_rows_by_league_field():
    rows = [
        {"league": "Premier League", "home_team": "Arsenal"},
        {"league": "La Liga", "home_team": "Barcelona"},
        {"league": "Premier League", "home_team": "Chelsea"},
    ]
    grouped = _by_league(rows)
    assert set(grouped) == {"Premier League", "La Liga"}
    assert len(grouped["Premier League"]) == 2
    assert len(grouped["La Liga"]) == 1


def test_by_league_defaults_missing_league_to_unknown_bucket():
    rows = [{"home_team": "Arsenal"}]
    grouped = _by_league(rows)
    assert grouped["?"] == rows
