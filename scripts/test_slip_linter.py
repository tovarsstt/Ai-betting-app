"""Tests for slip_linter — the pre-bet gate. Uses fixed ROI tables so the
verdicts are deterministic and don't depend on the live slips file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pytest
import slip_linter as sl
from slip_linter import lint, leg_bucket, roi_by

# Mirrors the user's settled record: longshot wins, lottery/soft-fav bleed.
BAND = {
    "chalk anchor (<1.50)": -33.0,
    "soft favorite (1.50-1.90)": -40.0,
    "value band (1.90-2.50)": 10.0,
    "longshot (2.50-5.0)": 85.0,
    "lottery (5.0+)": -18.0,
}
SHAPE = {"single": -7.0, "2-3 legs": 83.0, "4-6 legs": 25.0, "7+ legs": -100.0}


def test_clean_two_three_leg_ticket_accepts():
    legs = [{"decimal": 3.2, "selection": "A"}, {"decimal": 2.8, "selection": "B"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "ACCEPT"
    assert v.keep_count == 2


def test_lottery_leg_gets_cut():
    legs = [{"decimal": 3.0, "selection": "A"}, {"decimal": 6.5, "selection": "moon"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "TRIM"
    assert 1 in v.cut_legs  # the 6.5 lottery leg
    assert v.keep_count == 1


def test_chalk_leg_kept_as_anchor_not_cut():
    # win-prob-first: chalk is the safest leg — keep it even if its band bled before.
    legs = [{"decimal": 1.30, "selection": "chalk"}, {"decimal": 3.0, "selection": "B"}]
    v = lint(legs, BAND, SHAPE)
    assert 0 not in v.cut_legs                 # anchor survives
    assert v.status == "ACCEPT"
    assert any("anchor" in r.lower() for r in v.reasons)


def test_two_soft_favourites_capped_to_one():
    # two 1.5-1.9 legs — keep the higher-prob (lower price), cut the rest.
    band = {**BAND, "soft favorite (1.50-1.90)": 5.0}  # positive band so only the cap bites
    legs = [{"decimal": 1.65, "selection": "flipA"},
            {"decimal": 1.80, "selection": "flipB"},
            {"decimal": 3.0, "selection": "value"}]
    v = lint(legs, band, SHAPE)
    assert 1 in v.cut_legs        # 1.80 = lower win-prob, cut first
    assert 0 not in v.cut_legs    # 1.65 survives
    assert v.keep_count == 2


def test_surviving_soft_favourite_is_flagged_not_safe():
    band = {**BAND, "soft favorite (1.50-1.90)": 5.0}
    legs = [{"decimal": 1.70, "selection": "flip"}, {"decimal": 3.0, "selection": "value"}]
    v = lint(legs, band, SHAPE)
    assert 0 not in v.cut_legs
    assert any("soft favourite" in r.lower() for r in v.reasons)


def test_pick_quality_grade_surfaces_on_each_leg():
    # legs carrying a /predict grade show [LOCK]/[LEAN] in the output.
    legs = [{"decimal": 1.30, "selection": "lock", "quality": "LOCK"},
            {"decimal": 3.0, "selection": "value", "quality": "PICK"}]
    v = lint(legs, BAND, SHAPE)
    assert any("[LOCK]" in r for r in v.reasons) or v.status == "ACCEPT"
    # nothing cut — both gradeable, neither a soft fav
    assert v.cut_legs == ()


def test_lean_grade_treated_as_soft_favourite_even_when_priced_like_value():
    # a LEAN at 2.20 (value-price) must still be capped/flagged as a soft favourite.
    band = {**BAND, "soft favorite (1.50-1.90)": 5.0}
    legs = [{"decimal": 1.70, "selection": "softA"},
            {"decimal": 2.20, "selection": "leanB", "quality": "LEAN"}]
    v = lint(legs, band, SHAPE)
    assert 1 in v.cut_legs            # 2nd soft (the LEAN) capped out
    assert any("[LEAN]" in r for r in v.reasons)


def test_seven_plus_legs_trimmed_to_cap():
    legs = [{"decimal": 2.6 + i * 0.1, "selection": f"L{i}"} for i in range(7)]
    v = lint(legs, BAND, SHAPE)
    assert v.keep_count <= 4  # hard cap enforced


def test_all_cut_bands_rejects():
    # lottery (auto-cut) + a coin-flip in a losing band → nothing left to keep.
    legs = [{"decimal": 6.0, "selection": "moon"}, {"decimal": 1.75, "selection": "flip"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "REJECT"
    assert v.keep_count == 0


def test_single_in_edge_band_warns_not_rejects():
    legs = [{"decimal": 3.0, "selection": "solo"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "ACCEPT"          # leg itself is fine
    assert any("single" in r.lower() for r in v.reasons)  # but nudged to 2-3 lane


def test_leg_bucket_boundaries():
    assert leg_bucket(1) == "single"
    assert leg_bucket(3) == "2-3 legs"
    assert leg_bucket(6) == "4-6 legs"
    assert leg_bucket(9) == "7+ legs"


def test_roi_by_computes_sign():
    items = [{"stake": 10, "payout": 0, "k": "x"}, {"stake": 10, "payout": 30, "k": "x"}]
    assert roi_by(items, lambda i: i["k"])["x"] == 50.0  # staked 20, back 30


# ── Coverage gate: "no data, no bet" (Jul 16 2026: -94 of the day's -71 came
# from esports/volleyball markets no engine models) ──────────────────────────
def test_esports_nickname_leg_cut():
    # Stake tags esports sims with a human nickname in parens: "(Mick)".
    legs = [{"decimal": 1.22, "selection": "Indiana Pacers (Mick) ML"},
            {"decimal": 3.0, "selection": "value"}]
    v = lint(legs, BAND, SHAPE)
    assert 0 in v.cut_legs
    assert any("unmodelled" in r.lower() for r in v.reasons)


def test_covered_sports_pass_gate():
    # Jul 17: volleyball (FIVB fit), lmb (statsapi), cricket (fitted on real
    # results) all earned coverage — none cut by the gate
    legs = [{"decimal": 2.25, "selection": "Argentina ML", "sport": "volleyball"},
            {"decimal": 2.10, "selection": "England ML", "sport": "cricket"},
            {"decimal": 3.0, "selection": "Dorados ML", "sport": "lmb"}]
    v = lint(legs, BAND, SHAPE)
    assert not v.cut_legs


def test_all_unmodelled_rejects_with_no_data_reason():
    legs = [{"decimal": 2.25, "selection": "GSW ML summer league"},
            {"decimal": 1.40, "selection": "Empire (Legion) esports"}]
    v = lint(legs, BAND, SHAPE)
    assert v.status == "REJECT"
    assert v.keep_count == 0
    assert any("no data" in r.lower() for r in v.reasons)


def test_explicit_sport_field_gates():
    band = {**BAND, "soft favorite (1.50-1.90)": 5.0}  # positive band so only the sport gate bites
    legs = [{"decimal": 1.70, "selection": "Patna Pirates ML", "sport": "kabaddi"},
            {"decimal": 3.0, "selection": "value", "sport": "tennis"}]
    v = lint(legs, band, SHAPE)
    assert 0 in v.cut_legs
    assert 1 not in v.cut_legs


def test_numeric_handicap_parens_not_mistaken_for_esports():
    band = {**BAND, "soft favorite (1.50-1.90)": 5.0}
    legs = [{"decimal": 1.67, "selection": "Badosa (-5.5) game handicap"},
            {"decimal": 3.0, "selection": "value"}]
    v = lint(legs, band, SHAPE)
    assert 0 not in v.cut_legs


# ── Rule 3: cumulative juice filter (was prose-only until 2026-08-19) ────────

def test_ticket_vig_computes_from_both_sides():
    # 1.90 / 1.90 two-way = 5.26% vig on that leg.
    v = sl.ticket_vig([{"decimal": 1.90, "opposite_decimal": 1.90, "selection": "A"}])
    assert v["measured"] == 1 and v["unmeasured"] == 0
    assert round(v["total_vig"], 4) == round(2 / 1.9 - 1, 4)
    assert v["exceeds"] is False


def test_ticket_vig_never_estimates_a_missing_side():
    v = sl.ticket_vig([{"decimal": 1.90, "selection": "A"}])
    assert v["measured"] == 0
    assert v["unmeasured"] == 1
    assert v["total_vig"] is None
    assert v["exceeds"] is False   # unknown is not a breach


def test_ticket_vig_flags_breach_over_cap():
    # Three fat-margin legs compound past 15%.
    legs = [{"decimal": 1.75, "opposite_decimal": 1.75, "selection": s}
            for s in ("A", "B", "C")]
    v = sl.ticket_vig(legs)
    assert v["total_vig"] > sl.MAX_CUMULATIVE_VIG
    assert v["exceeds"] is True


def test_lint_rejects_ticket_over_the_vig_cap():
    legs = [{"decimal": 1.75, "opposite_decimal": 1.75, "selection": s}
            for s in ("Team A ML", "Team B ML", "Team C ML")]
    v = sl.lint(legs, band_roi={}, shape_roi={})
    assert v.status == "REJECT"
    assert any("cumulative vig" in r for r in v.reasons)


def test_lint_notes_when_vig_is_unmeasurable():
    legs = [{"decimal": 2.10, "selection": "Team A ML"},
            {"decimal": 2.20, "selection": "Team B ML"}]
    v = sl.lint(legs, band_roi={}, shape_roi={})
    assert any("vig unmeasured" in r for r in v.reasons)


def test_lint_accepts_normal_juice():
    legs = [{"decimal": 2.10, "opposite_decimal": 1.83, "selection": "Team A ML"},
            {"decimal": 2.20, "opposite_decimal": 1.78, "selection": "Team B ML"}]
    v = sl.lint(legs, band_roi={}, shape_roi={})
    assert not any("cumulative vig" in r for r in v.reasons)


# ── Over-cap trim must cut the least likely WINNER, using OUR probability ───
# Was ranked purely on price. Price is the BOOK's proxy with their vig in it;
# when the model supplies a probability, that is the number to rank on.

def _six(probs):
    """Six legs whose PRICES disagree with the model about which is safest."""
    prices = [1.26, 1.26, 1.47, 1.09, 1.11, 1.35]
    return [{"decimal": d, "prob": p, "selection": f"leg{i}"}
            for i, (d, p) in enumerate(zip(prices, probs))]


def test_trim_cuts_lowest_model_win_prob_not_highest_price():
    # Real ticket: model rates leg0 (1.26) at 64.5% and leg5 (1.35) at 73.6%.
    # Price-ranking would cut leg2/leg5; win-prob ranking must cut leg0/leg2.
    legs = _six([0.645, 0.715, 0.658, 0.839, 0.870, 0.736])
    v = sl.lint(legs, band_roi={}, shape_roi={})
    assert set(v.cut_legs) == {0, 2}
    assert v.keep_count == 4


def test_trim_reason_names_the_win_prob_and_its_source():
    legs = _six([0.645, 0.715, 0.658, 0.839, 0.870, 0.736])
    v = sl.lint(legs, band_roi={}, shape_roi={})
    cut = [r for r in v.reasons if "CUT" in r]
    assert any("lowest win prob" in r and "model" in r for r in cut)


def test_without_model_probs_it_falls_back_to_price_order():
    # No `prob` anywhere -> 1/decimal proxy -> the old behaviour exactly.
    legs = [{"decimal": d, "selection": f"leg{i}"}
            for i, d in enumerate([1.26, 1.26, 1.47, 1.09, 1.11, 1.35])]
    v = sl.lint(legs, band_roi={}, shape_roi={})
    assert set(v.cut_legs) == {2, 5}          # the two priciest
    assert any("price-implied" in r for r in v.reasons if "CUT" in r)


def test_win_prob_helper_prefers_model_over_price():
    assert sl._win_prob({"decimal": 1.10, "prob": 0.55}) == 0.55
    assert sl._win_prob({"decimal": 2.00}) == pytest.approx(0.5)


def test_win_prob_helper_ignores_nonsense_probabilities():
    # Out-of-range or unparseable -> fall back to the price proxy, never crash.
    assert sl._win_prob({"decimal": 2.0, "prob": 1.4}) == pytest.approx(0.5)
    assert sl._win_prob({"decimal": 2.0, "prob": "abc"}) == pytest.approx(0.5)
    assert sl._win_prob({"decimal": 2.0, "prob": None}) == pytest.approx(0.5)


# ── day/slate guard (2026-11-13) ──
def _hist():
    import pandas as pd
    rows = [{"dow": "Thu", "sport": "NFL", "type": "sgm", "stake": 10.0, "payout": 0.0}] * 12 + \
           [{"dow": "Thu", "sport": "NFL", "type": "sgm", "stake": 10.0, "payout": 25.0}] * 2 + \
           [{"dow": "Thu", "sport": "tennis", "type": "single", "stake": 10.0, "payout": 0.0}] * 4 + \
           [{"dow": "Sun", "sport": "NFL", "type": "multi", "stake": 10.0, "payout": 30.0}] * 10 + \
           [{"dow": "Sun", "sport": "NFL", "type": "multi", "stake": 10.0, "payout": 0.0}] * 10
    return pd.DataFrame(rows)


def test_day_guard_warns_on_losing_day_sport_and_type():
    from slip_linter import day_guard
    w = day_guard({"weekday": "Thu", "sport": "NFL", "type": "sgm", "stake": 10, "single_game": True}, df=_hist())
    txt = " | ".join(w)
    assert "WARN Thu" in txt and "NFL on Thu" in txt and "sgm on Thu" in txt and "single-game slate" in txt


def test_day_guard_silent_on_winning_day_and_without_context():
    from slip_linter import day_guard
    assert day_guard({"weekday": "Sun", "sport": "NFL", "type": "multi"}, df=_hist()) == []
    assert day_guard(None, df=_hist()) == []


def test_day_guard_flags_oversized_stake():
    from slip_linter import day_guard
    w = day_guard({"stake": 60}, df=_hist())
    assert any("median" in x for x in w)


def test_lint_appends_guard_without_changing_status():
    import slip_linter as sl
    legs = [{"decimal": 2.1, "selection": "A"}, {"decimal": 1.9, "selection": "B"}]
    base = sl.lint(legs)
    withc = sl.lint(legs, context={"weekday": "Thu", "sport": "NFL", "type": "multi"})
    assert withc.status == base.status and len(withc.reasons) >= len(base.reasons)
