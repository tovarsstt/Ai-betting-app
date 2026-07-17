"""Tests for mlb_game_model — fixture data, no network. Distribution math is
checked against known moments; markets against the joint matrix's own axioms."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import mlb_game_model as mm

TEAMS = {
    "New York Mets": {"w": 55, "l": 40, "g": 95, "rs": 470, "ra": 380,
                      "rs_pg": 4.947, "ra_pg": 4.0,
                      "home_w": 30, "home_l": 17, "away_w": 25, "away_l": 23},
    "Philadelphia Phillies": {"w": 48, "l": 47, "g": 95, "rs": 430, "ra": 430,
                              "rs_pg": 4.526, "ra_pg": 4.526,
                              "home_w": 26, "home_l": 21, "away_w": 22, "away_l": 26},
}
GAMES = [{"date": "2026-06-01", "home": "New York Mets",
          "away": "Philadelphia Phillies", "hs": 5, "as": 4}] * 40 + \
        [{"date": "2026-06-02", "home": "Philadelphia Phillies",
          "away": "New York Mets", "hs": 4, "as": 4}] * 40
FIXTURE = {
    "meta": {"league_rpg": 4.5, "pyth_exponent": 1.56, "home_win_pct": 0.522,
             "nb_dispersion": 2.2, "n_games": 80,
             "fetched_at": "2026-07-17T00:00:00"},
    "teams": TEAMS,
    "games": GAMES,
    "probables": [{"date": "2026-07-17", "home": "New York Mets",
                   "away": "Philadelphia Phillies",
                   "home_pitcher": {"name": "Ace", "ra9": 2.5, "ip_per_start": 6.0,
                                    "starts": 19},
                   "away_pitcher": None}],
}


def _patch(monkeypatch):
    monkeypatch.setattr(mm, "load", lambda: FIXTURE)


def test_nb_pmf_matches_target_moments():
    lam, phi = 4.5, 2.2
    pmf = mm.nb_pmf_vector(lam, phi, max_runs=60)
    ks = np.arange(61)
    mean = float((ks * pmf).sum())
    var = float((ks ** 2 * pmf).sum() - mean ** 2)
    assert abs(mean - lam) < 0.01
    assert abs(var - phi * lam) < 0.1          # variance = phi * mean by construction


def test_nb_falls_back_to_poisson_guard():
    pmf = mm.nb_pmf_vector(4.5, 1.0, max_runs=60)
    ks = np.arange(61)
    var = float((ks ** 2 * pmf).sum() - float((ks * pmf).sum()) ** 2)
    assert abs(var - 4.5) < 0.05               # Poisson: var = mean


def test_markets_are_coherent(monkeypatch):
    _patch(monkeypatch)
    out = mm.predict("Mets", "Phillies", total_line=8.5)
    assert out.get("error") is None
    assert abs(sum(out["ml"].values()) - 1.0) < 1e-6
    rl = out["run_line"]
    assert abs(rl["home -1.5"] + rl["away +1.5"] + rl["push"] - 1.0) < 1e-6
    assert rl["push"] == 0.0                   # .5 lines can't push
    t = out["total"]
    assert abs(t["p_over"] + t["p_under"] + t["p_push"] - 1.0) < 1e-6
    # better team at home should be ML favorite
    assert out["ml"]["home"] > 0.5


def test_run_line_is_harder_than_ml(monkeypatch):
    _patch(monkeypatch)
    out = mm.predict("Mets", "Phillies")
    assert out["run_line"]["home -1.5"] < out["ml"]["home"]


def test_ace_starter_suppresses_opponent_runs(monkeypatch):
    _patch(monkeypatch)
    with_ace = mm.predict("Mets", "Phillies")          # probables list the ace
    without = mm.predict("Mets", "Phillies", use_probables=False)
    assert with_ace["expected_runs"]["away"] < without["expected_runs"]["away"]
    assert with_ace["ml"]["home"] > without["ml"]["home"]
    ctx = with_ace["context"]["probable_starters"]
    assert ctx["home"]["factor_on_opp_runs"] < 1.0
    assert ctx["away"] is None                          # no away starter listed


def test_team_total_cdf_monotonic(monkeypatch):
    _patch(monkeypatch)
    out = mm.predict("Mets", "Phillies")
    cdf = [out["team_total_cdf"]["home"][k] for k in ("2.5", "3.5", "4.5", "5.5")]
    assert cdf == sorted(cdf)
    assert all(0.0 < v < 1.0 for v in cdf)


def test_home_scoring_split_measured():
    hf, af = mm.home_scoring_split(GAMES)
    # fixture: home sides scored 5 or 4, away 4 -> home factor above 1
    assert hf > 1.0 > af
    assert abs((hf + af) / 2 - 1.0) < 1e-9


def test_unknown_team_refuses(monkeypatch):
    _patch(monkeypatch)
    out = mm.predict("Mets", "Springfield Isotopes")
    assert out["error"] == "NO_DATA"
    assert "Springfield Isotopes" in out["missing_teams"]


def test_backtest_jackknife_runs_and_reports(monkeypatch):
    _patch(monkeypatch)
    bt = mm.backtest(min_date="2026-01-01")
    assert bt["n_games"] == 80
    assert 0.0 <= bt["ml_accuracy"] <= 1.0
    assert 0.0 <= bt["brier"] <= 1.0
    assert "jackknife" in bt["notes"][0]
