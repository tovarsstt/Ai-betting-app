"""Tests for the staking tier router + sizer. Pure math — no network."""
import staking as st


def test_normal_tier_for_high_winprob():
    assert st.route_tier(0.62, "NONE") == "NORMAL"


def test_mild_tier_for_mid_winprob():
    assert st.route_tier(0.45, "NONE") == "MILD"


def test_chaos_lite_routes_mild_even_if_low_winprob():
    assert st.route_tier(0.30, "LITE") == "MILD"


def test_chaos_full_routes_wild():
    assert st.route_tier(0.30, "FULL") == "WILD"


def test_low_winprob_no_chaos_routes_wild():
    assert st.route_tier(0.25, "NONE") == "WILD"


def _cand(market, side, wp, grade="NONE", odds=2.0):
    return st.Candidate(market=market, side=side, win_prob=wp,
                        decimal_odds=odds, chaos_grade=grade, evidence="x")


def test_size_card_respects_tier_pools_and_bankroll():
    cands = [
        _cand("Total 2.5", "Under", 0.62),               # NORMAL
        _cand("Double Chance", "1X", 0.45),              # MILD
        _cand("Underdog Win", "Minnow", 0.22, "FULL"),   # WILD
    ]
    cfg = st.TierConfig(bankroll=200.0)
    picks = st.size_card(cands, cfg)
    by_tier = {p.tier: p for p in picks}
    # Normal pool = 70% of 200 = 140 (single pick gets it all)
    assert abs(by_tier["NORMAL"].stake_usd - 140.0) < 0.01
    # Wild pick capped at 0.25u (1u = 1% of 200 = $2) -> <= $0.50
    assert by_tier["WILD"].stake_usd <= 0.50 + 1e-9


def test_size_card_caps_number_of_wild_picks():
    cfg = st.TierConfig(bankroll=200.0, max_wild=2)
    cands = [_cand(f"dog{i}", f"D{i}", 0.20, "FULL") for i in range(5)]
    picks = st.size_card(cands, cfg)
    assert sum(1 for p in picks if p.tier == "WILD") == 2


def test_size_card_does_not_mutate_input():
    cands = [_cand("Total 2.5", "Under", 0.62)]
    snapshot = cands[0]
    st.size_card(cands, st.TierConfig())
    assert cands[0] is snapshot  # immutability
