"""
Tests for the multivariate Poisson regression national-team fit. Uses small
synthetic match sets (pure math, no network) — real-data sanity checks (does
Morocco actually rank near the top) were run manually against the live
international_results.csv cache, not asserted here since live data drifts.
"""
from datetime import date

import poisson_regression as pr

TODAY = date(2026, 7, 1)


def _match(home, away, hg, ag, days_ago=30, neutral="FALSE"):
    d = date.fromordinal(TODAY.toordinal() - days_ago)
    return {"date": d.strftime("%Y-%m-%d"), "home_team": home, "away_team": away,
            "home_score": str(hg), "away_score": str(ag), "neutral": neutral}


def test_fit_recovers_a_clearly_stronger_team():
    # Strong beats Weak repeatedly and by real margins; Weak never wins.
    rows = []
    for i in range(20):
        rows += [
            _match("Strong", "Weak", 3, 0, days_ago=10 * i),
            _match("Weak", "Strong", 0, 3, days_ago=10 * i + 5),
        ]
    ratings = pr.fit(rows, as_of=TODAY)
    assert ratings.teams["Strong"]["attack"] > ratings.teams["Weak"]["attack"]
    assert ratings.teams["Strong"]["defense"] > ratings.teams["Weak"]["defense"]


def test_predicted_lambdas_favor_the_stronger_team():
    rows = []
    for i in range(15):
        rows += [
            _match("Strong", "Weak", 3, 0, days_ago=10 * i),
            _match("Weak", "Strong", 0, 3, days_ago=10 * i + 5),
        ]
    ratings = pr.fit(rows, as_of=TODAY)
    lh, la = pr.lambdas_for(ratings, "Strong", "Weak", neutral=True)
    assert lh > la


def test_missing_team_falls_back_to_league_average():
    rows = [_match("A", "B", 1, 1, days_ago=5)]
    ratings = pr.fit(rows, as_of=TODAY)
    lh, la = pr.lambdas_for(ratings, "A", "NeverPlayed", neutral=True)
    # A team with no fitted params defaults to attack=defense=0 (league-average
    # rate on the log scale) rather than crashing or inventing a number.
    assert lh > 0 and la > 0


def test_home_advantage_lifts_home_lambda_when_not_neutral():
    rows = []
    for i in range(10):
        rows.append(_match("A", "B", 1, 1, days_ago=10 * i, neutral="FALSE"))
        rows.append(_match("B", "A", 1, 1, days_ago=10 * i + 3, neutral="FALSE"))
    ratings = pr.fit(rows, as_of=TODAY)
    lh_neutral, la_neutral = pr.lambdas_for(ratings, "A", "B", neutral=True)
    lh_home, la_home = pr.lambdas_for(ratings, "A", "B", neutral=False)
    assert lh_home >= lh_neutral  # home advantage should not hurt the home lambda


def test_old_matches_outside_lookback_are_ignored():
    rows = [_match("A", "B", 5, 0, days_ago=3651)]  # >10 years, well past a 6y lookback
    ratings = pr.fit(rows, as_of=TODAY, lookback_years=6)
    assert ratings.n_matches == 0
    assert ratings.teams == {}


def test_future_matches_are_ignored():
    future = date.fromordinal(TODAY.toordinal() + 10)
    rows = [{"date": future.strftime("%Y-%m-%d"), "home_team": "A", "away_team": "B",
             "home_score": "2", "away_score": "1", "neutral": "TRUE"}]
    ratings = pr.fit(rows, as_of=TODAY)
    assert ratings.n_matches == 0


def test_unplayed_fixture_rows_with_na_scores_are_skipped():
    rows = [
        _match("A", "B", 2, 1, days_ago=5),
        {"date": "2026-07-10", "home_team": "A", "away_team": "C",
         "home_score": "NA", "away_score": "NA", "neutral": "TRUE"},
    ]
    ratings = pr.fit(rows, as_of=TODAY)
    assert ratings.n_matches == 1


def test_empty_input_returns_empty_ratings_not_a_crash():
    ratings = pr.fit([], as_of=TODAY)
    assert ratings.teams == {}
    assert ratings.n_matches == 0
