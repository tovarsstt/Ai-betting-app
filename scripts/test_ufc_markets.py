"""Tests for the UFC markets engine. Pure math — no network, no API."""
import math

import ufc_markets as um


def _book(**kw):
    a = um.Fighter("A", **{k[2:]: v for k, v in kw.items() if k.startswith("a_")})
    b = um.Fighter("B", **{k[2:]: v for k, v in kw.items() if k.startswith("b_")})
    return a, b


# ── Moneyline devig ─────────────────────────────────────────────────────────
def test_devig_2way_sums_to_one_and_reports_vig():
    dv = um.devig_2way(-200, 170)
    assert math.isclose(dv["a"] + dv["b"], 1.0, abs_tol=1e-9)
    assert dv["vig_pct"] > 0


def test_favorite_has_higher_devig_prob():
    dv = um.devig_2way(-250, 200)  # A favored
    assert dv["a"] > dv["b"]


# ── Win prob sourcing ─────────────────────────────────────────────────────────
def test_win_prob_from_moneyline():
    a, b = _book()
    fb = um.build_fight(a, b, moneyline=(-300, 240))
    assert fb.p_a > fb.p_b
    assert math.isclose(fb.p_a + fb.p_b, 1.0, abs_tol=1e-9)


def test_explicit_win_prob_overrides():
    a = um.Fighter("A", win_prob=0.7)
    b = um.Fighter("B", win_prob=0.3)
    fb = um.build_fight(a, b, moneyline=(-110, -110))
    assert math.isclose(fb.p_a, 0.7, abs_tol=1e-9)


# ── Market identities ─────────────────────────────────────────────────────────
def test_method_probs_partition_each_fighter_win():
    a, b = _book()
    fb = um.build_fight(a, b, moneyline=(-150, 130))
    assert math.isclose(fb.a_ko + fb.a_sub + fb.a_dec, fb.p_a, abs_tol=1e-6)
    assert math.isclose(fb.b_ko + fb.b_sub + fb.b_dec, fb.p_b, abs_tol=1e-6)


def test_distance_complement_equals_finish():
    fb = um.build_fight(*_book(), moneyline=(-200, 170))
    assert math.isclose(fb.goes_distance + fb.not_distance, 1.0, abs_tol=1e-6)
    # goes_distance == sum of decision outcomes
    assert math.isclose(fb.goes_distance, fb.a_dec + fb.b_dec, abs_tol=1e-9)


def test_grouped_method_matches_per_fighter():
    fb = um.build_fight(*_book(), moneyline=(-150, 130))
    assert math.isclose(fb.ko_any, fb.a_ko + fb.b_ko, abs_tol=1e-9)
    assert math.isclose(fb.sub_any, fb.a_sub + fb.b_sub, abs_tol=1e-9)


def test_finish_by_round_sums_to_total_finish():
    fb = um.build_fight(*_book(), moneyline=(-200, 170))
    # finish_by_round is rounded to 4 dp for output, so allow rounding slack
    assert math.isclose(sum(fb.finish_by_round), fb.not_distance, abs_tol=1e-3)


def test_finishes_skew_to_early_rounds():
    fb = um.build_fight(*_book(), moneyline=(-200, 170))
    # geometric decay → each round's finish mass below the previous
    fr = fb.finish_by_round
    assert all(fr[i] > fr[i + 1] for i in range(len(fr) - 1))


def test_five_round_fight_has_extra_lines():
    fb3 = um.build_fight(*_book(), scheduled_rounds=3, moneyline=(-150, 130))
    fb5 = um.build_fight(*_book(), scheduled_rounds=5, moneyline=(-150, 130))
    assert set(fb3.round_totals) == {1.5, 2.5}
    assert set(fb5.round_totals) == {1.5, 2.5, 3.5, 4.5}
    assert len(fb5.finish_by_round) == 5


def test_round_totals_complementary():
    fb = um.build_fight(*_book(), moneyline=(-150, 130))
    for v in fb.round_totals.values():
        assert math.isclose(v["over"] + v["under"], 1.0, abs_tol=1e-9)


# ── Fallback policy ───────────────────────────────────────────────────────────
def test_empirical_flag_set_when_stats_missing():
    fb = um.build_fight(*_book(), moneyline=(-150, 130))
    assert fb.used_empirical is True


def test_empirical_flag_clear_with_full_stats():
    a = um.Fighter("A", finish_rate=0.6, ko_share=0.7, sub_share=0.3)
    b = um.Fighter("B", finish_rate=0.4, ko_share=0.5, sub_share=0.5)
    fb = um.build_fight(a, b, moneyline=(-150, 130))
    assert fb.used_empirical is False


# ── Recommendation ────────────────────────────────────────────────────────────
def test_heavy_finisher_favorite_routed_to_not_distance():
    a = um.Fighter("Khabib", win_prob=0.78, finish_rate=0.75, ko_share=0.4, sub_share=0.6)
    b = um.Fighter("Dog", win_prob=0.22)
    fb = um.build_fight(a, b, scheduled_rounds=5)
    rec = um.recommend(fb)
    assert rec["favorite"] == "Khabib"
    assert "NOT go the distance" in rec["primary_pick"]["market"]
    assert rec["value_alternative"]["market"] == "Moneyline"


def test_heavy_decision_favorite_routed_to_decision():
    a = um.Fighter("Grinder", win_prob=0.72, finish_rate=0.15, ko_share=0.5, sub_share=0.5)
    b = um.Fighter("Dog", win_prob=0.28)
    fb = um.build_fight(a, b)
    rec = um.recommend(fb)
    assert "Decision" in rec["primary_pick"]["market"]


def test_competitive_fight_stays_on_moneyline():
    fb = um.build_fight(*_book(), moneyline=(-130, 110))  # ~55/45
    rec = um.recommend(fb)
    assert rec["primary_pick"]["market"] == "Moneyline"


def test_ev_computed_when_odds_supplied():
    fb = um.build_fight(*_book(), moneyline=(-150, 130))
    rec = um.recommend(fb, um.UFCOdds(ml_a=-150, ml_b=130))
    assert "ev_pct" in rec["primary_pick"]
