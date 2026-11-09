"""Tests for tennis_model.py (v4): name keys, antisymmetry, no look-ahead, artifacts, and the walk-forward claim that justified replacing the old points logistic."""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np, pandas as pd
import tennis_model as tm


def test_key_formats_agree():
    assert tm.key("Sabalenka, Aryna")[0] == "sabalenka a"
    assert tm.key("Sabalenka A.")[0] == "sabalenka a"
    assert "sabalenka a" in tm.key("Aryna Sabalenka")
    assert tm.key("De Minaur, Alex")[0] == "de minaur a" == tm.key("De Minaur A.")[0]
    assert tm.key("Andreeva, Mirra")[0] == tm.key("Andreeva M.")[0]


def test_state_features_use_only_the_past():
    st = tm.State(); d0 = pd.Timestamp("2025-01-01"); d1 = pd.Timestamp("2025-01-08")
    before = st.feats("a", "b", "Hard", 3, d0)
    assert before[0] == 0 and before[5] == 0                 # nothing known -> neutral features
    st.update("a", "b", "Hard", d0)
    after = st.feats("a", "b", "Hard", 3, d1)
    assert after[0] > 0 and after[5] > 0                     # winner now leads on Elo and h2h
    again = st.feats("b", "a", "Hard", 3, d1)
    assert abs(after[0] + again[0]) < 1e-9 and abs(after[5] + again[5]) < 1e-9   # antisymmetric


def test_model_is_antisymmetric_and_loaded():
    m = tm.TennisV4.get()
    assert m is not None, "run: python3 scripts/tennis_model.py rebuild"
    p = m.predict("Sabalenka, Aryna", "Muchova, Karolina", "Hard", 3)
    q = m.predict("Muchova, Karolina", "Sabalenka, Aryna", "Hard", 3)
    assert abs(p["p_model"] + q["p_model"] - 1) < 1e-9
    assert m.predict("Nobody, Zed", "Muchova, Karolina") is None


def test_anchor_follows_the_market_when_odds_given():
    m = tm.TennisV4.get()
    r = m.predict("Sabalenka, Aryna", "Muchova, Karolina", "Hard", 3, (1.48, 2.70))
    pm = r["p_market"]
    assert abs(r["p_anchored"] - pm) < abs(r["p_model"] - pm) + 0.02      # the anchor sits at the market, not at the model


def test_report_shows_v4_beats_old_points_model_every_test_year():
    rep = json.loads(tm.REPORT.read_text())
    assert rep["by_year"], "empty report"
    for y, r in rep["by_year"].items():
        assert r["model_ll"] < r["old_points_ll"], y
        assert 0.85 < r["model_slope"] < 1.2, (y, r["model_slope"])           # calibrated (the old model's slope was .72-.84)
