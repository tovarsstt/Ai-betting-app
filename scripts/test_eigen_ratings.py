"""
Tests for the Keener eigenvector rating engine. Small synthetic match sets
(pure math, no network) verify the eigenvector-centrality properties the
method is supposed to have — self-consistent strength-of-schedule, not just
raw win count.
"""
from datetime import date

import eigen_ratings as er

TODAY = date(2026, 7, 1)


def _match(home, away, hg, ag, days_ago=30):
    d = date.fromordinal(TODAY.toordinal() - days_ago)
    return {"date": d.strftime("%Y-%m-%d"), "home_team": home, "away_team": away,
            "home_score": str(hg), "away_score": str(ag)}


def test_ratings_sum_to_one():
    rows = [_match("A", "B", 2, 1, 5), _match("B", "C", 1, 0, 10), _match("C", "A", 0, 3, 15)]
    r = er.fit(rows, as_of=TODAY)
    assert abs(sum(r.ratings.values()) - 1.0) < 1e-6


def test_dominant_team_over_multiple_weak_opponents_rates_highest():
    rows = []
    for i in range(10):
        rows.append(_match("Champion", "Also-Ran", 4, 0, days_ago=10 * i))
        rows.append(_match("Also-Ran", "Champion", 0, 4, days_ago=10 * i + 3))
    r = er.fit(rows, as_of=TODAY)
    assert r.ratings["Champion"] > r.ratings["Also-Ran"]


def test_beating_a_strong_team_outweighs_beating_a_weak_one():
    # Team X beats a genuinely strong team (Elite) once; Team Y racks up wins
    # only against a proven-weak team (Scrub). Eigenvector centrality should
    # reward X for who it beat, not just how many times.
    rows = []
    # Elite dominates the field except for one loss to X.
    for i in range(8):
        rows.append(_match("Elite", "Scrub", 3, 0, days_ago=10 * i))
        rows.append(_match("Scrub", "Elite", 0, 3, days_ago=10 * i + 3))
    rows.append(_match("X", "Elite", 1, 0, days_ago=5))
    rows.append(_match("Elite", "X", 0, 1, days_ago=8))
    # Y beats Scrub repeatedly (nothing else).
    for i in range(8):
        rows.append(_match("Y", "Scrub", 2, 0, days_ago=10 * i + 100))
        rows.append(_match("Scrub", "Y", 0, 2, days_ago=10 * i + 103))
    r = er.fit(rows, as_of=TODAY)
    assert r.ratings["X"] > r.ratings["Y"]


def test_keener_transform_is_concave_above_parity():
    # Marginal reward for a bigger goal-share should SHRINK as the game gets
    # more lopsided (sqrt concavity) — a 0.5->0.6 swing should count for more
    # than an equally-sized 0.8->0.9 swing. This is what stops one blowout
    # from dominating the rating the way raw goal difference would.
    step_near_parity = er._keener_transform(0.6) - er._keener_transform(0.5)
    step_deep_in_blowout = er._keener_transform(0.9) - er._keener_transform(0.8)
    assert step_near_parity > step_deep_in_blowout


def test_empty_input_returns_empty_ratings():
    r = er.fit([], as_of=TODAY)
    assert r.ratings == {}
    assert r.n_matches == 0


def test_old_matches_outside_lookback_are_ignored():
    rows = [_match("A", "B", 3, 0, days_ago=3651)]
    r = er.fit(rows, as_of=TODAY, lookback_years=6)
    assert r.n_matches == 0
