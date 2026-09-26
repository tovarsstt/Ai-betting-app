"""cfb_model — ratings, pricing and joint sims on synthetic schedules (no network)."""
import numpy as np
import pandas as pd
import pytest

import cfb_model as cm
import slip_pricer as sp


@pytest.fixture
def cfb(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "DATA", tmp_path)
    monkeypatch.setattr(cm, "MIN_CURRENT_GAMES", 4)
    rows, gid = [], 0
    for season, weeks in ((2025, range(1, 11)), (2026, range(1, 4))):
        for w in weeks:
            for h, a, hs, as_ in (("Strong U", "Weak St", 42, 10), ("Mid U", "Low Tech", 24, 20),
                                  ("Weak St", "Mid U", 14, 28), ("Low Tech", "Strong U", 7, 38)):
                gid += 1
                rows.append(dict(game_id=gid, season=season, week=w, season_type=2, neutral_site=False,
                                 home_team=h, away_team=a, home_score=hs, away_score=as_,
                                 status="STATUS_FINAL"))
    for s in (2025, 2026):
        pd.DataFrame([r for r in rows if r["season"] == s]).to_csv(tmp_path / f"cfb_schedule_{s}.csv", index=False)
    cm.load.cache_clear()
    cm.market_lines.cache_clear()
    yield tmp_path
    cm.load.cache_clear()
    cm.market_lines.cache_clear()


def test_ratings_rank_teams_and_predict(cfb):
    v = cm.game_view("Strong U", "Weak St")
    assert v["mu"] > 10 and v["source"] == "ratings only"
    assert cm.p_side(v["mu"], 0, True) > 0.7
    assert cm.game_view("Nobody A", "Nobody B") is None


def test_market_line_gets_the_market_weight(cfb):
    v = cm.game_view("Mid U", "Low Tech", market_spread=-3.0, market_total=45.0)
    assert v["mu"] == pytest.approx(cm.MARKET_WEIGHT * 3.0 + (1 - cm.MARKET_WEIGHT) * v["ratings_margin"])
    assert v["total"] == pytest.approx(cm.MARKET_WEIGHT * 45.0 + (1 - cm.MARKET_WEIGHT) * v["ratings_total"])


def test_side_and_total_probabilities_are_complementary():
    assert cm.p_side(3.0, 2.5, True) + cm.p_side(3.0, -2.5, False) == pytest.approx(1.0)
    assert cm.p_total(50.0, 51.5, True) + cm.p_total(50.0, 51.5, False) == pytest.approx(1.0)
    assert cm.p_side(0.0, 0.0, True) == pytest.approx(0.5)


def test_joint_prob_matches_marginals_and_correlation_sign():
    v = {"mu": 7.0, "total": 50.0}
    p_fav = cm.p_side(7.0, -3.5, True)
    p_over = cm.p_total(50.0, 49.5, True)
    joint_fav_over = cm.joint_prob(v, [("side", True, -3.5), ("total", 49.5, True)], 400_000)
    joint_dog_over = cm.joint_prob(v, [("side", False, 3.5), ("total", 49.5, True)], 400_000)
    assert joint_fav_over > p_fav * p_over                  # favourite covering goes with points
    assert joint_dog_over < (1 - p_fav) * p_over
    single = cm.joint_prob(v, [("total", 49.5, True)], 400_000)
    assert single == pytest.approx(p_over, abs=0.005)


def test_slip_prices_a_college_same_game_block(cfb, monkeypatch):
    (cfb / "lines.json").write_text('{"Weak St @ Strong U": {"home_spread": -20.5, "total": 52.5}}')
    cm.market_lines.cache_clear()
    slip = ("Multi apuesta del mismo partido (2\n2,90\nStrong U - Weak St\nStrong U (-14.5)\n"
            "Hándicap (incl. tiempo adicional)\nSobre 50.5\nTotal (incl. tiempo adicional)\n"
            "Apuesta\n5.00000000\nPago\n14.50000000\n")
    t = sp.parse(slip)[0]
    r = sp.price_ticket(t, {}, n_sims=200_000)
    legs = r["blocks"][0]["legs"]
    assert all(x["prob"] is not None and "college ratings+market" in x["note"] for x in legs)
    assert r["prob_all"] is not None and not r["unpriced"]
    assert r["blocks"][0]["corr_games"] == cm.BACKTEST_GAMES


def test_small_sample_prop_is_pulled_toward_even(monkeypatch):
    monkeypatch.setattr(sp, "_roster_ids", lambda: {"rookie back": ("id1", "SEA")})
    monkeypatch.setattr(sp, "player_log", lambda pid, idc, val: pd.Series([52.0, 52.0], index=["g1", "g2"]))
    leg = sp.Leg("prop", "x", line=43.5, over=True, player="Rookie Back",
                 stat='["rusher_player_id", "rushing_yards"]')
    p, note, _ = sp.price_prop(leg)
    raw = sp.prop_prob(np.array([52.0, 52.0]), 43.5, True, False)
    assert 0.5 < p < raw and "SMALL SAMPLE" in note
