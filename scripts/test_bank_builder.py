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


def test_strong_singles_one_per_match():
    # Over 2.5 AND BTTS Yes of the SAME game as two "singles" = stacked
    # exposure on one game script — keep only the highest-prob one.
    board = [
        leg("Japon v Honduras", "Over 2.5", 1.85, 0.62),
        leg("Japon v Honduras", "BTTS Yes", 1.80, 0.60),
    ]
    out = bb.strong_singles(board)
    assert len(out) == 1
    assert out[0]["selection"] == "Over 2.5"


# ── Slate auto-feed: games in, day card out — no hand-built candidates ───────

GAME = {
    "name": "Brasil v Chile",
    "h2h": [1.45, 4.60, 8.00],
    "totals": [[2.5, 1.85, 1.95]],
    "btts": [1.90, 1.85],
    "dc_x2": 2.90,
}


def test_candidates_from_slate_carry_real_prices():
    cands = bb.candidates_from_slate([GAME])
    by_sel = {c["selection"]: c for c in cands}
    assert by_sel["Home ML"]["decimal"] == 1.45     # book price, not invented
    assert by_sel["Over 2.5"]["decimal"] == 1.85
    for c in cands:
        assert c["match"] == "Brasil v Chile"
        assert 0.0 < c["prob"] < 1.0


def test_day_card_returns_tickets_and_singles():
    games = [
        GAME,
        {"name": "Francia v Peru", "h2h": [1.48, 4.40, 7.50], "totals": [[2.5, 1.88, 1.92]]},
        {"name": "Alemania v Egipto", "h2h": [1.42, 4.80, 8.50], "totals": []},
    ]
    card = bb.day_card(games, bankroll=200.0)
    assert "tickets" in card and "singles" in card
    for s in card["singles"]:
        assert s["decimal"] >= bb.SINGLE_MIN_ODDS
        assert s["prob"] >= 0.58


# ── Stake-portable price floors: bet only if YOUR book's price >= min_odds ───

def test_single_min_odds_keeps_ev_floor():
    out = bb.strong_singles(SINGLES_BOARD)
    for s in out:
        # at exactly min_odds the bet still clears the +5% EV gate
        assert s["prob"] * s["min_odds"] - 1.0 >= bb.SINGLE_MIN_EV - 1e-9
        # floor is tight: one cent lower breaks the gate
        assert s["prob"] * (s["min_odds"] - 0.01) - 1.0 < bb.SINGLE_MIN_EV


def test_ticket_legs_and_combined_carry_min_odds():
    out = bb.build_tickets(BOARD)
    for t in out["tickets"]:
        for l in t["legs"]:
            assert l["min_odds"] * float(l["prob"]) >= 1.0 - 1e-9   # leg break-even
        assert t["min_combined"] * t["joint_prob"] >= 1.0 - 1e-9    # ticket break-even


# ── 2-way sports (NBA/NFL/MLB/NHL/tennis): sharp-anchored candidates ─────────

ODDS_API_EVENT = {  # exact the-odds-api /v4 event shape
    "home_team": "Lakers", "away_team": "Celtics",
    "commence_time": "2026-07-06T00:00:00Z",
    "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Lakers", "price": 1.50}, {"name": "Celtics", "price": 2.70}]}]},
        {"key": "draftkings", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Lakers", "price": 1.57}, {"name": "Celtics", "price": 2.55}]}]},
    ],
}


def test_normalize_2way_event_anchors_pinnacle_and_takes_best_price():
    from scan_slate import normalize_2way_event
    g = normalize_2way_event(ODDS_API_EVENT)
    assert g["pinnacle"] == [1.50, 2.70]
    assert g["best"] == [1.57, 2.70]           # DK better on fav, pinnacle on dog
    assert g["best_books"] == ["draftkings", "pinnacle"]


def test_normalize_2way_event_no_pinnacle_no_candidate():
    from scan_slate import normalize_2way_event
    ev = {**ODDS_API_EVENT, "bookmakers": ODDS_API_EVENT["bookmakers"][1:]}
    assert normalize_2way_event(ev) is None    # no sharp anchor -> never guess


def test_candidates_from_2way_probs_and_prices():
    from scan_slate import normalize_2way_event
    g = normalize_2way_event(ODDS_API_EVENT)
    cands = bb.candidates_from_2way([g])
    by_sel = {c["selection"]: c for c in cands}
    lak = by_sel["Lakers ML"]
    assert lak["decimal"] == 1.57              # best price, not pinnacle's
    assert 0.62 < lak["prob"] < 0.66           # devigged pinnacle fair prob
    assert by_sel["Celtics ML"]["prob"] < 0.38
    assert math.isclose(lak["prob"] + by_sel["Celtics ML"]["prob"], 1.0, abs_tol=1e-9)


def test_day_card_2way_mode_runs_the_same_gates():
    from scan_slate import normalize_2way_event
    g = normalize_2way_event(ODDS_API_EVENT)
    card = bb.day_card([g], bankroll=200.0, mode="2way")
    assert "tickets" in card and "singles" in card
    for s in card["singles"]:
        assert s["prob"] >= 0.58 and s["decimal"] >= bb.SINGLE_MIN_ODDS


# ── Best-per-match: EVERY match gets an answer with an honest verdict ────────

PER_MATCH_BOARD = [
    # match A: clear +EV probable pick -> BET
    leg("Brasil v Chile", "Brasil ML", 1.52, 0.70),        # EV +6.4%
    leg("Brasil v Chile", "Over 2.5", 1.85, 0.50),         # worse: lower prob
    # match B: nothing positive -> least-bad shown as NO_BET
    leg("Suiza v Argelia", "Suiza ML", 1.30, 0.72),        # EV -6.4%
    leg("Suiza v Argelia", "Under 2.5", 1.70, 0.56),       # EV -4.8% (least bad)
    # match C: fair-priced probable -> LEAN
    leg("Japon v Honduras", "Japon ML", 1.65, 0.61),       # EV +0.65%
]


def test_every_match_gets_exactly_one_answer():
    out = bb.best_per_match(PER_MATCH_BOARD)
    assert sorted(m["match"] for m in out) == sorted(
        ["Brasil v Chile", "Suiza v Argelia", "Japon v Honduras"])


def test_verdicts_are_honest():
    v = {m["match"]: m["verdict"] for m in bb.best_per_match(PER_MATCH_BOARD)}
    assert v["Brasil v Chile"] == "BET"        # probable AND clears +2% gate
    assert v["Japon v Honduras"] == "LEAN"     # fair-ish, no real edge
    assert v["Suiza v Argelia"] == "NO_BET"    # everything -EV: shown, not bet


def test_no_bet_row_shows_the_flip_price():
    row = next(m for m in bb.best_per_match(PER_MATCH_BOARD)
               if m["match"] == "Suiza v Argelia")
    assert row["selection"] == "Under 2.5"     # least-bad option, max EV
    # floor = price where it becomes a BET; at floor the +2% gate clears
    assert row["prob"] * row["min_odds"] - 1.0 >= 0.02 - 1e-9


def test_bet_rows_prefer_win_prob_among_positive_ev():
    board = [
        leg("X v Y", "X ML", 1.55, 0.68),      # EV +5.4%, prob 68  <- money first
        leg("X v Y", "Over 2.5", 2.10, 0.51),  # EV +7.1%, prob 51
    ]
    row = bb.best_per_match(board)[0]
    assert row["selection"] == "X ML"


def test_day_card_includes_per_match():
    games = [{"name": "Brasil v Chile", "h2h": [1.45, 4.60, 8.00],
              "totals": [[2.5, 1.85, 1.95]]}]
    card = bb.day_card(games, bankroll=200.0)
    assert "per_match" in card
    assert len(card["per_match"]) == 1
    assert card["per_match"][0]["verdict"] in ("BET", "LEAN", "NO_BET")
