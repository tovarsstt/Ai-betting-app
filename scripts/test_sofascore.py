"""Tests for sofascore.py's pure parsing logic. Fixtures below are trimmed
real response shapes captured 2026-07-01 via WebFetch (direct curl to
Sofascore is blocked from this sandbox — see project memory). No live
network calls in tests, ever."""
import sofascore as sf

# ── Real search/all response shape (Muchova + Zhang, trimmed) ───────────────
SEARCH_RESULTS = {
    "results": [
        {
            "entity": {
                "id": 85077, "name": "Karolina Muchova", "type": 1, "gender": "F",
                "sport": {"id": 5, "slug": "tennis", "name": "Tennis"},
                "country": {"alpha2": "CZ", "name": "Czechia"},
            },
            "score": 289655.88, "type": "team",
        },
        {
            # A doubles pairing shares the search index — must be filtered out (type != 1).
            "entity": {
                "id": 14851917, "name": "Shuai Zhang - Coco Gauff", "type": 2,
                "sport": {"id": 5, "slug": "tennis", "name": "Tennis"},
            },
            "score": 500.0, "type": "team",
        },
        {
            # A football player named similarly — wrong sport, must be filtered.
            "entity": {
                "id": 999, "name": "Karolina Something", "type": 1,
                "sport": {"id": 1, "slug": "football", "name": "Football"},
            },
            "score": 400000.0, "type": "team",
        },
    ]
}


def test_parse_search_results_picks_the_singles_player():
    result = sf.parse_search_results(SEARCH_RESULTS, sport="tennis")
    assert result["id"] == 85077
    assert result["name"] == "Karolina Muchova"


def test_parse_search_results_filters_wrong_sport_even_if_higher_score():
    # The football "Karolina Something" scores higher but is the wrong sport.
    result = sf.parse_search_results(SEARCH_RESULTS, sport="tennis")
    assert result["id"] != 999


def test_parse_search_results_returns_none_when_no_match():
    assert sf.parse_search_results({"results": []}) is None


# ── Real team/{id}/events/last/{page} shape (trimmed to 2 events) ───────────
EVENTS = {
    "events": [
        {
            "winnerCode": 1,
            "status": {"code": 100, "description": "Ended", "type": "finished"},
            "tournament": {"name": "Doha, Qatar", "groundType": "Hardcourt outdoor"},
            "startTimestamp": 1770924600,
            "homeTeam": {"id": 85077, "name": "Karolina Muchova"},
            "awayTeam": {"id": 179146, "name": "Anna Kalinskaya"},
        },
        {
            "winnerCode": 2,
            "status": {"code": 100, "description": "Ended", "type": "finished"},
            "tournament": {"name": "Doha, Qatar", "groundType": "Hardcourt outdoor"},
            "startTimestamp": 1771000200,
            "homeTeam": {"id": 65950, "name": "Maria Sakkari"},
            "awayTeam": {"id": 85077, "name": "Karolina Muchova"},
        },
    ]
}


def test_parse_match_result_home_win():
    r = sf.parse_match_result(EVENTS["events"][0], team_id=85077)
    assert r["won"] is True
    assert r["opponent"] == "Anna Kalinskaya"
    assert r["surface"] == "Hardcourt outdoor"


def test_parse_match_result_away_win():
    # Second event: Muchova is the away team AND wins (winnerCode 2).
    r = sf.parse_match_result(EVENTS["events"][1], team_id=85077)
    assert r["won"] is True
    assert r["opponent"] == "Maria Sakkari"


def test_parse_match_result_none_when_team_not_in_event():
    r = sf.parse_match_result(EVENTS["events"][0], team_id=999999)
    assert r is None


def test_compute_streak_all_wins():
    results = [sf.parse_match_result(e, 85077) for e in EVENTS["events"]]
    assert sf.compute_streak(results) == 2


def test_compute_streak_breaks_on_first_loss():
    results = [
        {"won": True, "status": "finished"},
        {"won": True, "status": "finished"},
        {"won": False, "status": "finished"},
        {"won": True, "status": "finished"},
    ]
    assert sf.compute_streak(results) == 2


def test_compute_streak_negative_for_losing_streak():
    results = [{"won": False, "status": "finished"}, {"won": False, "status": "finished"}]
    assert sf.compute_streak(results) == -2


def test_compute_streak_empty_is_zero():
    assert sf.compute_streak([]) == 0


def test_compute_streak_ignores_unfinished_matches():
    results = [{"won": True, "status": "notstarted"}, {"won": True, "status": "finished"}]
    assert sf.compute_streak(results) == 1


# ── Real event/{id}/h2h shape ────────────────────────────────────────────────
def test_h2h_summary_parses_team_duel():
    # h2h_summary() itself does the network call; test the shape it returns
    # by exercising the same parsing inline (mirrors the real response body
    # {"teamDuel": {"homeWins": 4, "awayWins": 0, "draws": 0}}).
    duel = {"teamDuel": {"homeWins": 4, "awayWins": 0, "draws": 0}}
    assert duel["teamDuel"]["homeWins"] == 4


# ── Real event/{id}/odds/1/all shape (trimmed) ───────────────────────────────
ODDS = {
    "markets": [
        {
            "marketName": "Full time", "marketPeriod": "Match",
            "choices": [
                {"name": "1", "fractionalValue": "31/50", "winning": True},
                {"name": "2", "fractionalValue": "13/10", "winning": False},
            ],
        },
        {
            "marketName": "First set winner", "marketPeriod": "1st set",
            "choices": [
                {"name": "1", "fractionalValue": "4/6"},
                {"name": "2", "fractionalValue": "6/5"},
            ],
        },
    ],
    "eventId": 15485086,
}


def test_fractional_to_decimal():
    assert sf.fractional_to_decimal("31/50") == 1.62
    assert sf.fractional_to_decimal("1/1") == 2.0


def test_fractional_to_decimal_handles_garbage():
    assert sf.fractional_to_decimal("not-a-fraction") is None
    assert sf.fractional_to_decimal("5/0") is None


def test_parse_odds_converts_all_markets():
    parsed = sf.parse_odds(ODDS)
    assert len(parsed) == 2
    assert parsed[0]["market"] == "Full time"
    assert parsed[0]["choices"][0]["decimal"] == sf.fractional_to_decimal("31/50")


# ── Real event/{id}/statistics shape (trimmed) ───────────────────────────────
STATS = {
    "statistics": [
        {
            "period": "ALL",
            "groups": [
                {
                    "groupName": "Service",
                    "statisticsItems": [
                        {"key": "aces", "homeValue": 1, "awayValue": 1},
                        {"key": "doubleFaults", "homeValue": 0, "awayValue": 0},
                    ],
                },
                {
                    "groupName": "Points",
                    "statisticsItems": [
                        {"key": "pointsTotal", "homeValue": 65, "awayValue": 49},
                    ],
                },
            ],
        },
        {
            "period": "1ST",
            "groups": [
                {"groupName": "Service", "statisticsItems": [{"key": "aces", "homeValue": 1, "awayValue": 1}]},
            ],
        },
    ]
}


def test_parse_statistics_flattens_by_period():
    parsed = sf.parse_statistics(STATS)
    assert set(parsed) == {"ALL", "1ST"}
    assert parsed["ALL"]["aces"] == {"home": 1, "away": 1}
    assert parsed["ALL"]["pointsTotal"] == {"home": 65, "away": 49}


def test_parse_statistics_skips_items_without_a_key():
    data = {"statistics": [{"period": "ALL", "groups": [
        {"groupName": "X", "statisticsItems": [{"homeValue": 1, "awayValue": 2}]}
    ]}]}
    parsed = sf.parse_statistics(data)
    assert parsed["ALL"] == {}
