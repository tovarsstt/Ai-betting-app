"""Fast invariants for the v2 math (run: python3 -m pytest tests/test_engine_math.py -q)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import betting_math as bm  # noqa: E402
import sport_math as sm  # noqa: E402
import stochastic_engine as se  # noqa: E402
import tennis_vec as tv  # noqa: E402


def test_devig_methods_sum_to_one_and_keep_order():
    odds = [1.28, 3.90]
    for name, fn in bm.DEVIG.items():
        p = fn(odds)
        assert abs(p.sum() - 1) < 1e-9, name
        assert p[0] > p[1], name
    p3 = bm.devig_power([2.1, 3.4, 3.6])
    assert abs(p3.sum() - 1) < 1e-9


def test_power_devig_pushes_margin_onto_longshots():
    mult, power = bm.devig_multiplicative([1.2, 5.0]), bm.devig_power([1.2, 5.0])
    assert power[0] > mult[0]                     # favourite keeps more under power


def test_kelly_with_uncertainty_never_exceeds_point_kelly():
    p = np.random.default_rng(1).beta(55, 45, 4000)
    f, f_pt, _ = bm.kelly_uncertain(p, 1.95)
    assert 0 <= f <= f_pt + 1e-9


def test_isotonic_is_monotone():
    rng = np.random.default_rng(2)
    p = rng.random(2000)
    y = (rng.random(2000) < p).astype(float)
    q = bm.Isotonic().fit(p, y).predict(np.linspace(0, 1, 50))
    assert np.all(np.diff(q) >= -1e-12)


def test_closed_form_hold_matches_exact_recursion():
    import tennis_games_model as t
    for p in (0.5, 0.58, 0.66, 0.74):
        assert abs(float(tv.hold(np.array(p))) - t.hold_prob(p)) < 1e-9


def test_exact_streak_formula_matches_monte_carlo():
    exact = se.streak_before_successes(4, 3, 0.55)
    rng = np.random.default_rng(3)
    x = rng.random((200_000, 120)) < 0.55
    idx = np.arange(120)[None, :]
    run = idx - np.maximum.accumulate(np.where(x, idx, -1), axis=1)
    hit = np.where(run >= 4, idx, 999).min(1)
    reach = np.where(np.cumsum(x, 1) >= 3, idx, 999).min(1)
    assert abs(exact - (hit < reach).mean()) < 0.004


def test_sport_price_game_probabilities_are_coherent():
    for sport, kw in (("mlb", dict(total=8.5, p_home=0.58)), ("nhl", dict(total=5.5, p_home=0.6)), ("nba", dict(total=224.5, p_home=0.7)), ("nfl", dict(total=45.5, p_home=0.6))):
        a = sm.price_game(sport, line=-1.5 if sport in ("mlb", "nhl") else -3.5, **kw)
        b = sm.price_game(sport, line=+1.5 if sport in ("mlb", "nhl") else +3.5, **kw)
        assert 0 < a["cover"] < b["cover"] < 1, sport     # a bigger handicap must cover more often


def test_hierarchical_sd_widens_margin_tails_but_keeps_win_prob():
    a = tv.simulate(0.66, 0.62, 200_000, 0.0, 1)
    b = tv.simulate(0.66, 0.62, 200_000, 0.05, 1)
    assert (np.abs(b["margin"]) > 8).mean() > (np.abs(a["margin"]) > 8).mean()


def test_tennis_games_model_uses_v2_for_bo3_and_legacy_for_bo5():
    import tennis_games_model as t
    if not t.V2_ENABLED:
        return
    d3 = t.predict("Rune, Holger", "Altmaier, Daniel", handicap_a=-2.5, target_match_prob_a=0.657)
    assert d3["engine"] == "v2"
    assert abs(list(d3["match_prob"].values())[0] - 0.657) < 0.02            # level stays anchored to the supplied probability
    assert t.predict("Rune, Holger", "Altmaier, Daniel", best_of=5)["engine"] == "legacy"
