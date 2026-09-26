"""Tests for lmb_model + fetch_lmb_standings fitters — fixed fixture, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lmb_model as lm
from fetch_lmb_standings import fit_pyth_exponent, league_home_win_pct

FIXTURE = {
    "meta": {"pyth_exponent": 1.8, "league_rpg": 5.0, "home_win_pct": 0.54,
             "source": "test", "fetched_at": "t"},
    "teams": {
        "Toros de Tijuana": {"w": 50, "l": 22, "g": 72, "rs": 400, "ra": 300,
                             "rs_pg": 5.556, "ra_pg": 4.167,
                             "home_w": 28, "home_l": 8, "away_w": 22, "away_l": 14},
        "Dorados de Chihuahua": {"w": 30, "l": 42, "g": 72, "rs": 320, "ra": 380,
                                 "rs_pg": 4.444, "ra_pg": 5.278,
                                 "home_w": 18, "home_l": 18, "away_w": 12, "away_l": 24},
    },
}


def _patch(monkeypatch):
    monkeypatch.setattr(lm, "load", lambda: FIXTURE)


def test_better_team_is_favorite_and_probs_sum(monkeypatch):
    _patch(monkeypatch)
    out = lm.predict("Toros de Tijuana", "Dorados de Chihuahua")
    assert out["ml_prob"]["Toros de Tijuana"] > 0.6
    assert abs(sum(out["ml_prob"].values()) - 1.0) < 1e-6


def test_home_field_moves_the_line(monkeypatch):
    _patch(monkeypatch)
    at_home = lm.predict("Dorados de Chihuahua", "Toros de Tijuana")
    on_road = lm.predict("Toros de Tijuana", "Dorados de Chihuahua")
    # Dorados prob when hosting > Dorados prob when visiting
    assert at_home["ml_prob"]["Dorados de Chihuahua"] > on_road["ml_prob"]["Dorados de Chihuahua"]


def test_partial_name_matches(monkeypatch):
    _patch(monkeypatch)
    out = lm.predict("Dorados", "Toros")
    assert out.get("error") is None
    assert out["home"] == "Dorados de Chihuahua"


def test_unknown_team_refuses(monkeypatch):
    _patch(monkeypatch)
    out = lm.predict("Dorados", "Gotham Knights")
    assert out["error"] == "NO_DATA"
    assert "Gotham Knights" in out["missing_teams"]


def test_expected_runs_track_matchup(monkeypatch):
    _patch(monkeypatch)
    out = lm.predict("Toros de Tijuana", "Dorados de Chihuahua")
    er = out["expected_runs"]
    # strong offense vs weak defense should beat league average 5.0
    assert er["Toros de Tijuana"] > 5.0
    # parts are rounded independently of the total — allow a cent of rounding drift
    assert abs(er["total"] - (er["Toros de Tijuana"] + er["Dorados de Chihuahua"])) < 0.02


def test_pyth_fit_recovers_consistent_exponent():
    # build teams whose W% exactly follows pyth with x=2.0; fitter should find ~2.0
    teams = {}
    for i, (rs, ra) in enumerate([(400, 300), (350, 350), (300, 400), (380, 320)]):
        x = 2.0
        wpct = rs ** x / (rs ** x + ra ** x)
        g = 100
        teams[f"T{i}"] = {"w": round(wpct * g), "l": g - round(wpct * g), "g": g,
                          "rs": rs, "ra": ra}
    assert abs(fit_pyth_exponent(teams) - 2.0) < 0.15


def test_home_win_pct_aggregates():
    teams = {"A": {"home_w": 30, "home_l": 10, "away_w": 0, "away_l": 0},
             "B": {"home_w": 10, "home_l": 30, "away_w": 0, "away_l": 0}}
    assert league_home_win_pct(teams) == 0.5
