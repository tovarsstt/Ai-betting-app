#!/usr/bin/env python3
"""Tests for bank_builder.py — the 3-5x growth-lane ticket constructor."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bank_builder as bb


def leg(match, sel, dec, prob):
    return {"match": match, "selection": sel, "decimal": dec, "prob": prob}


# A realistic board: chalk MLs + a strong total across different matches.
# Every prob clears the implied prob of its price (model edge = +EV leg).
BOARD = [
    leg("Brasil v Chile", "Brasil ML", 1.45, 0.70),
    leg("Francia v Peru", "Francia ML", 1.48, 0.68),
    leg("Alemania v Egipto", "Alemania ML", 1.42, 0.72),
    leg("Japon v Honduras", "Over 2.5", 1.85, 0.58),
]


def test_builds_ticket_in_target_lane():
    out = bb.build_tickets(BOARD)
    assert out["tickets"], "board has valid combos — must build"
    t = out["tickets"][0]
    assert 2 <= len(t["legs"]) <= 3
    assert bb.TARGET_MIN <= t["combined"] <= bb.TARGET_MAX
    assert t["lane"] == "target"


def test_never_two_legs_same_match():
    board = BOARD + [leg("Brasil v Chile", "Over 2.5", 1.80, 0.59)]
    out = bb.build_tickets(board)
    for t in out["tickets"]:
        matches = [l["match"] for l in t["legs"]]
        assert len(matches) == len(set(matches))


def test_prob_floor_excludes_weak_legs():
    board = BOARD + [leg("Suiza v Argelia", "BTTS Yes", 2.10, 0.50)]
    out = bb.build_tickets(board)
    for t in out["tickets"]:
        for l in t["legs"]:
            assert l["prob"] >= bb.MIN_LEG_PROB


def test_negative_ev_legs_excluded():
    # 0.60 prob at 1.40 => EV -16% — a probable event priced badly is still a leak
    board = BOARD + [leg("Italia v Ghana", "Italia ML", 1.40, 0.60)]
    out = bb.build_tickets(board)
    for t in out["tickets"]:
        assert all(l["selection"] != "Italia ML" for l in t["legs"])


def test_ranked_by_joint_prob_first():
    out = bb.build_tickets(BOARD)
    probs = [t["joint_prob"] for t in out["tickets"]]
    assert probs == sorted(probs, reverse=True)


def test_returned_tickets_share_no_legs():
    # Jodar rule: one leg cloned into 2 slips = one bet bought twice
    out = bb.build_tickets(BOARD, n_tickets=3)
    seen = set()
    for t in out["tickets"]:
        for l in t["legs"]:
            key = (l["match"], l["selection"])
            assert key not in seen
            seen.add(key)


def test_fallback_pattern_lane_flagged():
    # only two chalk legs available: combined 1.45*1.48 = 2.15 — below even
    # pattern lane; add one soft fav so 2.3-6.0 is reachable but 3.0-5.0 is not
    board = [
        leg("Brasil v Chile", "Brasil ML", 1.45, 0.70),
        leg("Japon v Honduras", "Over 2.5", 1.85, 0.58),
    ]
    out = bb.build_tickets(board)
    assert out["tickets"], "2.68 combined sits in the proven 2.3-6.0 pattern lane"
    assert out["tickets"][0]["lane"] == "pattern"


def test_empty_board_is_a_pass():
    out = bb.build_tickets([])
    assert out["tickets"] == []
    assert out["pass"] is True


def test_ticket_ev_is_joint_prob_math():
    out = bb.build_tickets(BOARD)
    t = out["tickets"][0]
    assert math.isclose(t["ev_pct"], round((t["joint_prob"] * t["combined"] - 1) * 100, 1),
                        abs_tol=0.11)


def test_tickets_survive_slip_linter():
    out = bb.build_tickets(BOARD)
    for t in out["tickets"]:
        assert t["verdict"] == "ACCEPT"


# ── Strong singles: 1.75+ odds, high model prob, quarter-Kelly sized ─────────

SINGLES_BOARD = [
    leg("Brasil v Chile", "Brasil ML", 1.45, 0.70),      # great prob, pays too thin
    leg("Japon v Honduras", "Over 2.5", 1.85, 0.62),     # qualifies: EV +14.7%
    leg("Francia v Peru", "BTTS Yes", 1.90, 0.56),       # prob under 0.58 floor
    leg("Italia v Ghana", "Italia ML", 1.75, 0.59),      # EV +3.3% — edge too thin
    leg("Alemania v Egipto", "Under 3.5", 1.80, 0.60),   # qualifies: EV +8.0%
]


def test_strong_singles_gates():
    out = bb.strong_singles(SINGLES_BOARD)
    picks = {s["selection"] for s in out}
    assert picks == {"Over 2.5", "Under 3.5"}


def test_strong_singles_sorted_by_prob_first():
    out = bb.strong_singles(SINGLES_BOARD)
    probs = [s["prob"] for s in out]
    assert probs == sorted(probs, reverse=True)


def test_strong_singles_quarter_kelly_capped():
    out = bb.strong_singles(SINGLES_BOARD)
    for s in out:
        dec, p = s["decimal"], s["prob"]
        full_kelly = (p * dec - 1.0) / (dec - 1.0)
        expected = min(full_kelly * bb.KELLY_FRACTION * 100, bb.KELLY_CAP_PCT)
        assert math.isclose(s["stake_pct"], round(expected, 2), abs_tol=0.011)
        assert s["stake_pct"] <= bb.KELLY_CAP_PCT


def test_strong_singles_stake_usd_from_bankroll():
    out = bb.strong_singles(SINGLES_BOARD, bankroll=200.0)
    for s in out:
        assert math.isclose(s["stake_usd"], round(200.0 * s["stake_pct"] / 100, 2), abs_tol=0.011)


def test_strong_singles_empty_board():
    assert bb.strong_singles([]) == []
