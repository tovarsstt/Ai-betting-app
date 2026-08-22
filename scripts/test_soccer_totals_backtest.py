"""Tests for scripts/soccer_totals_backtest.py.

The value here is a NEGATIVE result — the soccer goals model turned out NOT to
carry the level bias the tennis games-total model did. These tests pin the
machinery that produced that verdict, so a future refit cannot quietly start
applying a correction that was never justified.
"""
import json

import pytest

import soccer_totals_backtest as stb


# ── P(over) from the score matrix ───────────────────────────────────────────

def test_p_over_falls_as_the_line_rises():
    lh, la = 1.5, 1.2
    assert stb._p_over(lh, la, 1.5) > stb._p_over(lh, la, 2.5) > stb._p_over(lh, la, 3.5)


def test_p_over_rises_with_expected_goals():
    low = stb._p_over(0.8, 0.7, 2.5)
    high = stb._p_over(2.2, 1.9, 2.5)
    assert high > low


def test_p_over_is_a_probability():
    for line in (0.5, 2.5, 6.5):
        p = stb._p_over(1.4, 1.1, line)
        assert 0.0 <= p <= 1.0


def test_p_over_half_lines_cannot_push():
    """Every line is a .5, so P(over) + P(under) must exhaust the space."""
    p = stb._p_over(1.4, 1.1, 2.5)
    assert 0.0 < p < 1.0


# ── Lambda construction mirrors the engine ──────────────────────────────────

LEAGUE = {"mu": 0.15, "home_advantage": 0.20,
          "teams": {"Home": {"attack": 0.30, "defense": 0.10},
                    "Away": {"attack": 0.05, "defense": 0.25},
                    "NoData": {"attack": None, "defense": None}}}


def test_home_advantage_raises_the_home_lambda():
    lh, la = stb._lambdas(LEAGUE, "Home", "Away")
    no_adv = dict(LEAGUE, home_advantage=0.0)
    lh2, _ = stb._lambdas(no_adv, "Home", "Away")
    assert lh > lh2


def test_unknown_team_yields_no_lambdas():
    assert stb._lambdas(LEAGUE, "Home", "Nobody") is None


def test_team_with_null_ratings_yields_no_lambdas():
    # A team in the pool but never fitted must not be priced off defaults.
    assert stb._lambdas(LEAGUE, "Home", "NoData") is None


# ── Calibration gate: a correction must be earned ───────────────────────────

def _result(bias, sig_25):
    return {"n_games": 1311, "mean_bias_goals": bias,
            "over_lines": {"2.5": {"significant": sig_25}}}


def test_no_correction_when_bias_is_immaterial(tmp_path, monkeypatch):
    monkeypatch.setattr(stb, "backtest", lambda s: _result(-0.0123, False))
    out = stb.fit_calibration(path=tmp_path / "c.json")
    assert out["offset_goals"] == 0.0
    assert out["applied"] is False


def test_no_correction_when_bias_is_large_but_not_significant(tmp_path, monkeypatch):
    """Size alone is not evidence — this is the guard that stopped the tennis
    bucket corrections from shipping."""
    monkeypatch.setattr(stb, "backtest", lambda s: _result(0.40, False))
    out = stb.fit_calibration(path=tmp_path / "c.json")
    assert out["applied"] is False
    assert out["offset_goals"] == 0.0


def test_no_correction_when_significant_but_immaterial(tmp_path, monkeypatch):
    monkeypatch.setattr(stb, "backtest", lambda s: _result(0.02, True))
    out = stb.fit_calibration(path=tmp_path / "c.json")
    assert out["applied"] is False


def test_correction_applies_only_when_material_AND_significant(tmp_path, monkeypatch):
    monkeypatch.setattr(stb, "backtest", lambda s: _result(0.40, True))
    out = stb.fit_calibration(path=tmp_path / "c.json")
    assert out["applied"] is True
    assert out["offset_goals"] == pytest.approx(-0.40)


def test_correction_opposes_the_bias(tmp_path, monkeypatch):
    # Model expects too FEW goals -> offset must ADD goals.
    monkeypatch.setattr(stb, "backtest", lambda s: _result(-0.40, True))
    out = stb.fit_calibration(path=tmp_path / "c.json")
    assert out["offset_goals"] == pytest.approx(0.40)


def test_calibration_file_records_its_reasoning(tmp_path, monkeypatch):
    monkeypatch.setattr(stb, "backtest", lambda s: _result(-0.0123, False))
    path = tmp_path / "c.json"
    stb.fit_calibration(path=path)
    saved = json.loads(path.read_text())
    assert "deliberately" in saved["why"]
    assert saved["measured_bias_goals"] == -0.0123     # the measurement is kept


def test_backtest_error_passes_through(tmp_path, monkeypatch):
    monkeypatch.setattr(stb, "backtest", lambda s: {"error": "NO_GAMES"})
    assert stb.fit_calibration(path=tmp_path / "c.json")["error"] == "NO_GAMES"
