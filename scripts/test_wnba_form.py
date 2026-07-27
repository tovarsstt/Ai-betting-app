"""Tests for the WNBA comparative profile (form / rest / B2B / H2H)."""
import edge_api as e

_TEAM = {"gp": 18, "win_rate": 0.667, "last10": "7-3", "avg_margin": 5.2,
         "recent_margin": 4.2, "streak": "W2", "rest_days": 2, "b2b": False,
         "home": "7-2", "road": "5-4"}


def _set_wnba(teams=None, h2h=None):
    e.WNBA_FORM.clear()
    e.WNBA_FORM.update({"teams": teams or {}, "h2h": h2h or {}})


def test_nickname_resolves_to_full_name():
    # Arrange: data keyed by full ESPN displayName.
    _set_wnba(teams={"Las Vegas Aces": _TEAM})
    # Act / Assert: an odds-feed nickname still resolves.
    assert e._wnba_team_key("Aces", e.WNBA_FORM["teams"]) == "Las Vegas Aces"
    assert e._wnba_team_key("Las Vegas Aces", e.WNBA_FORM["teams"]) == "Las Vegas Aces"


def test_profile_attaches_form_and_h2h():
    # Arrange
    _set_wnba(
        teams={"Dallas Wings": _TEAM, "Chicago Sky": _TEAM},
        h2h={"Dallas Wings": {"Chicago Sky": {"n": 2, "w": 2, "l": 0,
                                              "margin": 5.5, "last": "2026-06-20 93-92"}}},
    )
    # Act
    p = e._wnba_profile("Dallas Wings", "Chicago Sky")
    # Assert
    assert p["home"]["team"] == "Dallas Wings"
    assert p["away"]["team"] == "Chicago Sky"
    assert p["h2h"]["w"] == 2


def test_profile_none_when_unknown():
    # Arrange / Act / Assert: no fabricated profile for unknown teams.
    _set_wnba(teams={"Dallas Wings": _TEAM})
    assert e._wnba_profile("Madeup City", "Nowhere State") is None
