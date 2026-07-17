"""Tests for slip_linter — the pre-bet gate. Uses fixed ROI tables so the
verdicts are deterministic and don't depend on the live slips file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
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
