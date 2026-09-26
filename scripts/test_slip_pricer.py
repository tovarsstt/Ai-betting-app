"""slip_pricer — parser + pricing math on synthetic data (no network, no feed files)."""
import numpy as np
import pandas as pd

import slip_pricer as sp

SLIP = """
Multi apuesta del mismo partido (2
3,40
California Golden Bears - Clemson Tigers
California Golden Bears (2.5)
Hándicap (incl. tiempo adicional)
Sobre 51.5
Total (incl. tiempo adicional)
Apuesta
5.00000000
Pago
17.00000000
3 Multi tramo
5,00
Multi apuesta del mismo partido (2
2,65
Miami Dolphins - Kansas City Chiefs
Sobre 199.5 Yardas por Pases
Patrick Mahomes
0
200
Seattle Seahawks
Ganador (incl. tiempo adicional)
Kansas City Chiefs (-7.5)
Hándicap (incl. prórroga)
1,63
Dom, 27 Sept
12:00
Miami Dolphins
Kansas City Chiefs
Tennessee Titans (5.5)
Hándicap (incl. prórroga)
1,54
Apuesta
1.00000000
Pago
5.00000000
"""


def test_parse_tickets_blocks_and_legs():
    t = sp.parse(SLIP)
    assert len(t) == 2
    cfb, multi = t
    assert cfb.decimal == 3.40 and cfb.stake == 5.0 and cfb.payout == 17.0
    assert [leg.kind for leg in cfb.blocks[0].legs] == ["spread", "total"]
    assert cfb.blocks[0].legs[0].line == 2.5 and cfb.blocks[0].matchup[0] == "California Golden Bears"
    assert multi.decimal == 5.0 and len(multi.blocks) == 3
    sgp = multi.blocks[0]
    assert sgp.sgp and sgp.decimal == 2.65 and [leg.kind for leg in sgp.legs] == ["prop", "ml"]
    assert sgp.legs[0].player == "Patrick Mahomes" and sgp.legs[0].line == 199.5
    kc = multi.blocks[1].legs[0]
    assert kc.team == "Kansas City Chiefs" and kc.line == -7.5 and kc.decimal == 1.63
    assert kc.matchup == ("Miami Dolphins", "Kansas City Chiefs")
    assert multi.blocks[2].legs[0].line == 5.5                       # "(5.5)" is +5.5


def test_game_legs_use_the_margin_model_and_skip_unknown_leagues():
    slate = {("Miami Dolphins", "Kansas City Chiefs"): {"mu": -10.0, "total": 45.0}}
    kc_ml, _ = sp.price_game_leg(sp.Leg("ml", "", team="Kansas City Chiefs"), slate)
    kc_75, _ = sp.price_game_leg(sp.Leg("spread", "", team="Kansas City Chiefs", line=-7.5), slate)
    mia_75, _ = sp.price_game_leg(sp.Leg("spread", "", team="Miami Dolphins", line=7.5), slate)
    assert kc_ml > kc_75 > 0.5 and abs(kc_75 + mia_75 - 1) < 1e-9
    over, _ = sp.price_game_leg(sp.Leg("total", "", line=44.5, over=True,
                                       matchup=("Miami Dolphins", "Kansas City Chiefs")), slate)
    assert 0.5 < over < 0.55
    p, note = sp.price_game_leg(sp.Leg("spread", "", team="California Golden Bears", line=2.5), slate)
    assert p is None and "no model" in note


def test_prop_prob_blends_recent_hits_with_fitted_prior():
    always = np.array([250.0] * 10)
    assert 0.9 < sp.prop_prob(always, 199.5, True, False) < 1.0      # never fully certain
    never = np.array([150.0] * 10)
    assert sp.prop_prob(never, 199.5, True, False) < 0.1
    recent = np.array([100.0] * 10 + [300.0] * 5)                      # recency weighted
    assert sp.prop_prob(recent, 199.5, True, False) > 5 / 15
    under = sp.prop_prob(always, 199.5, False, False)
    assert abs(under + sp.prop_prob(always, 199.5, True, False) - 1) < 1e-9


def test_sgp_factor_measures_correlation_and_shrinks():
    idx = [f"g{i}" for i in range(20)]
    a = pd.Series([True] * 10 + [False] * 10, index=idx)
    f_same, n = sp.sgp_factor([a, a.copy()])                           # perfectly correlated
    assert n == 20 and 1.3 < f_same < 2.0
    f_one, _ = sp.sgp_factor([a])
    assert f_one == 1.0
    b = pd.Series([True, False] * 10, index=idx)                       # independent
    assert abs(sp.sgp_factor([a, b])[0] - 1) < 0.05


def test_ticket_math_and_unpriced_legs(monkeypatch):
    slate = {("Miami Dolphins", "Kansas City Chiefs"): {"mu": -10.0, "total": 45.0},
             ("New York Giants", "Tennessee Titans"): {"mu": 2.0, "total": 38.5}}
    monkeypatch.setattr(sp, "price_prop", lambda leg: (0.7, "stub", None))
    monkeypatch.setattr(sp, "_game_hits", lambda leg: None)
    multi = sp.parse(SLIP)[1]
    r = sp.price_ticket(multi, slate, n_sims=200_000)
    probs = [b["prob"] for b in r["blocks"]]
    assert all(p is not None for p in probs)
    assert abs(r["prob_all"] - np.prod(probs)) < 1e-12 and abs(r["sim_all"] - r["prob_all"]) < 0.01
    assert abs(sum(r["hits_dist"].values()) - 1) < 1e-9 and r["need"] == 1 / 5.0
    cfb = sp.price_ticket(sp.parse(SLIP)[0], slate, n_sims=10_000)
    assert "prob_all" not in cfb and len(cfb["unpriced"]) == 2
