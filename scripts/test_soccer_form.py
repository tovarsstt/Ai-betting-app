"""Tests for the soccer/WC comparative profile + the market-calibrated data gate."""
import edge_api as e
from edge_api import predict_soccer, SoccerMarketReq

_TEAM = {"form_ppg": 1.9, "win_rate": 0.5, "gf": 1.8, "ga": 0.8, "over25": 0.5,
         "btts": 0.45, "clean_sheet": 0.4, "failed_to_score": 0.2,
         "streak": "W3", "last5": "WWWDL", "n": 30.0}


def _set_soccer(teams=None, h2h=None):
    e.SOCCER_FORM.clear()
    e.SOCCER_FORM.update({"teams": teams or {}, "h2h": h2h or {}})


def test_alias_resolves_usa_to_united_states():
    # Arrange: data is keyed by the source's name.
    _set_soccer(teams={"United States": _TEAM})
    # Act / Assert: odds-feed shorthand still resolves.
    assert e._soccer_team_key("USA", e.SOCCER_FORM["teams"]) == "United States"


def test_profile_attaches_home_away_and_h2h():
    # Arrange
    _set_soccer(
        teams={"Brazil": _TEAM, "Chile": _TEAM},
        h2h={"Brazil": {"Chile": {"n": 5, "w": 4, "d": 1, "l": 0,
                                  "gf": 2.1, "ga": 0.4, "last": "2025-06-01 3-0"}}},
    )
    # Act
    p = e._soccer_profile("Brazil", "Chile")
    # Assert
    assert p["home"]["team"] == "Brazil"
    assert p["away"]["team"] == "Chile"
    assert p["h2h"]["w"] == 4


def test_profile_none_when_both_unknown():
    # Arrange
    _set_soccer(teams={"Brazil": _TEAM})
    # Act / Assert: unknown names → no fabricated profile.
    assert e._soccer_profile("Madeupland", "Nowhereia") is None


def test_unknown_team_with_full_odds_still_prices():
    # Arrange: names absent from ratings, but full 1X2 odds present.
    _set_soccer()
    # Act
    r = predict_soccer(SoccerMarketReq(
        home_team="Madeupland", away_team="Nowhereia",
        home_odds=-110, draw_odds=240, away_odds=300))
    # Assert: market-calibrated board, NOT a NO_DATA refusal (WC name-mismatch fix).
    assert r["status"] == "OK"
    assert r["lambda_source"] == "market_calibrated"


def test_no_odds_and_unknown_team_refuses():
    # Arrange / Act: no odds AND no ratings → nothing to model from.
    r = predict_soccer(SoccerMarketReq(home_team="Madeupland", away_team="Nowhereia"))
    # Assert
    assert r["status"] == "NO_DATA"
