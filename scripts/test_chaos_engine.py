"""Tests for the chaos engine. Pure math — no network, no API."""
import chaos_engine as ce


def _canada_bosnia() -> ce.MatchInput:
    # Modest favourite (Canada) with a live draw — the Canada lesson.
    return ce.MatchInput(
        home=ce.TeamForm(name="Canada", gf=1, ga=1, gp=1, strength=0.02),
        away=ce.TeamForm(name="Bosnia", gf=1, ga=1, gp=1, strength=0.01),
        market_home=0.50, market_draw=0.27, market_away=0.23,
        fav_decimal_odds=1.83, draw_decimal_odds=3.40,
        model_home=0.46, model_draw=0.31, model_away=0.23,
        home_tag="CAN_DRAW", away_tag=None,
    )


# ── DRAW SCORE ────────────────────────────────────────────────────────────────
def test_draw_score_in_unit_interval():
    out = ce.draw_score(_canada_bosnia())
    assert 0.0 <= out["draw_score"] <= 1.0


def test_draw_score_cites_evidence_for_each_present_component():
    out = ce.draw_score(_canada_bosnia())
    assert set(out["components"]) >= {"parity", "low_scoring", "motivation", "model_gap"}
    assert len(out["evidence"]) >= 4


def test_missing_model_drops_model_gap_component_no_invention():
    m = ce.replace_model(_canada_bosnia(), None, None, None)
    out = ce.draw_score(m)
    assert "model_gap" not in out["components"]
    assert 0.0 <= out["draw_score"] <= 1.0


# ── Chaos grading ─────────────────────────────────────────────────────────────
def test_mid_fav_underpriced_draw_flags_chaos_lite():
    res = ce.assess_match(_canada_bosnia())
    assert res.grade == "LITE"
    assert res.favourite == "Canada"
    assert res.side == "Draw"


def test_heavy_overpriced_fav_with_live_dog_flags_chaos_full():
    m = ce.MatchInput(
        home=ce.TeamForm(name="BigDog", gf=2, ga=2, gp=1, strength=0.18),
        away=ce.TeamForm(name="Minnow", gf=1, ga=2, gp=1, strength=0.04),
        market_home=0.66, market_draw=0.20, market_away=0.14,
        fav_decimal_odds=1.45,
        model_home=0.54, model_draw=0.24, model_away=0.22,
    )
    res = ce.assess_match(m)
    assert res.grade == "FULL"
    assert res.side == "Minnow"


def test_clean_strong_fav_no_chaos():
    m = ce.MatchInput(
        home=ce.TeamForm(name="Germany", gf=7, ga=1, gp=1, strength=0.12),
        away=ce.TeamForm(name="Curacao", gf=1, ga=7, gp=1, strength=0.001),
        market_home=0.93, market_draw=0.05, market_away=0.02,
        fav_decimal_odds=1.04,
        model_home=0.93, model_draw=0.05, model_away=0.02,
    )
    res = ce.assess_match(m)
    assert res.grade == "NONE"


def test_lite_value_check_uses_draw_price():
    res = ce.assess_match(_canada_bosnia())  # model draw 31% > implied 1/3.40 = 29%
    assert res.value_ok is True


# ── Slate weather ─────────────────────────────────────────────────────────────
def test_slate_weather_cagey_when_many_draw_leans():
    results = [ce.assess_match(_canada_bosnia()) for _ in range(4)]
    w = ce.slate_weather(results)
    assert w["weather"] == "CAGEY"
    assert w["draw_lean_share"] >= 0.5
    assert w["n_matches"] == 4


def test_slate_weather_normal_on_empty():
    w = ce.slate_weather([])
    assert w["weather"] == "NORMAL"
    assert w["chaos_count"] == 0
