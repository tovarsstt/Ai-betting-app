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
    # A single Normal pick no longer swallows the whole 70% pool ($140 of $200):
    # 62% @ 2.0 -> full Kelly 24% -> quarter-Kelly 6% -> capped at 3% = $6
    assert abs(by_tier["NORMAL"].stake_usd - 6.0) < 0.01
    # Every pick respects the 3%-of-bank ceiling
    assert all(p.stake_usd <= 200.0 * st.MAX_PICK_PCT + 1e-9 for p in picks)
    # Wild pick capped at 0.25u (1u = 1% of 200 = $2) -> <= $0.50
    assert by_tier["WILD"].stake_usd <= 0.50 + 1e-9


def test_size_card_negative_ev_pick_gets_zero_stake():
    # 45% at 2.0 is -EV: Kelly <= 0 -> no money, even in a funded tier
    picks = st.size_card([_cand("Double Chance", "1X", 0.45, odds=2.0)], st.TierConfig(bankroll=200.0))
    assert picks[0].stake_usd == 0.0


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
