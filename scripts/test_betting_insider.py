"""Tests for scripts/betting_insider.py — fully offline (_get monkeypatched),
so the suite never hits the live feed."""
import pytest

import betting_insider as bi


def _prop(**over):
    """One row shaped like the live payload (captured 2026-08-19)."""
    base = {
        "player_name": "Jake Bauers", "position": "First Baseman",
        "team_name": "Milwaukee Brewers", "game_id": "MLB-20260818-SEA-MIL",
        "game_time": "2026-08-19T23:40:00Z",
        "home_team": "Brewers", "away_team": "Mariners",
        "stat_type": "total_bases",
        "current_line": 1.5, "opening_line": 1.5,
        "current_over_odds": 131, "current_under_odds": -175,
        "opening_over_odds": 124, "opening_under_odds": -165,
        "pinnacle_line": 1.5, "pinnacle_over_odds": 120,
        "pinnacle_under_odds": -160,
        "pinnacle_opening_over_odds": 150,
        "consensus_over_pct": 38.8, "prizepicks_entries": 250,
        "sleeper_over_pct": 40, "sleeper_picks": 10,
        "fade_bet_side": "under", "fade_perf_hit_rate": 72.6,
        "fade_perf_total": 1614, "fade_perf_roi": 13.1,
        "signal": "", "signal_side": "",
    }
    base.update(over)
    return base


@pytest.fixture
def stub(monkeypatch):
    def _install(props, success=True):
        monkeypatch.setattr(bi, "_get",
                            lambda url, timeout=bi.TIMEOUT: {"success": success,
                                                             "props": props})
    return _install


# ── Odds math ───────────────────────────────────────────────────────────────

def test_american_to_decimal_both_signs():
    assert bi.american_to_decimal(100) == 2.0
    assert bi.american_to_decimal(-200) == 1.5


def test_odds_helpers_are_none_safe():
    # A missing price must stay missing, never become 1.0 or 0.
    assert bi.american_to_decimal(None) is None
    assert bi.implied(None) is None
    assert bi.american_to_decimal(0) is None


def test_devig_pinnacle_sums_to_one():
    fair = bi.devig_pinnacle(120, -160)
    assert round(fair["over"] + fair["under"], 6) == 1.0
    assert fair["vig_pct"] > 0


def test_devig_refuses_one_sided_price():
    # A one-sided devig would be an invented number.
    assert bi.devig_pinnacle(120, None) is None


# ── Consensus trap (the whole point of this module's guards) ────────────────

def test_consensus_100_is_flagged_unreliable(stub):
    # 100 tracks a tiny Sleeper sample, NOT public money.
    stub([_prop(consensus_over_pct=100, prizepicks_entries=0)])
    s = bi.signals("mlb")[0]
    assert s["consensus_pct"] == 100
    assert s["consensus_reliable"] is False
    assert "not public money" in s["consensus_note"]


def test_consensus_with_zero_prizepicks_entries_is_unreliable(stub):
    # Live feed has prizepicks_entries == 0 on every row today.
    stub([_prop(consensus_over_pct=38.8, prizepicks_entries=0)])
    assert bi.signals("mlb")[0]["consensus_reliable"] is False


def test_consensus_reliable_only_with_real_sample(stub):
    stub([_prop(consensus_over_pct=38.8, prizepicks_entries=250)])
    s = bi.signals("mlb")[0]
    assert s["consensus_reliable"] is True
    assert s["consensus_note"] is None


# ── CLV / movement ─────────────────────────────────────────────────────────

def test_movement_positive_when_price_drifts_out(stub):
    # opening +124 (2.24) -> current +131 (2.31): you get paid more now.
    stub([_prop()])
    assert bi.signals("mlb")[0]["over_move_pct"] > 0


def test_pinnacle_movement_negative_when_money_comes_in(stub):
    # pinnacle opened +150 (2.5), now +120 (2.2) — steam on the over.
    stub([_prop()])
    assert bi.signals("mlb")[0]["pinnacle_over_move_pct"] < 0


def test_movement_is_none_without_an_opening_price(stub):
    stub([_prop(opening_over_odds=None)])
    assert bi.signals("mlb")[0]["over_move_pct"] is None


def test_line_moved_flag(stub):
    stub([_prop(opening_line=2.5, current_line=1.5)])
    assert bi.signals("mlb")[0]["line_moved"] is True


# ── Coverage honesty ───────────────────────────────────────────────────────

def test_soccer_and_tennis_are_rejected_not_stubbed():
    for sport in ("soccer", "tennis"):
        with pytest.raises(bi.BettingInsiderError, match="unsupported sport"):
            bi.signals(sport)


def test_empty_props_is_not_an_error(stub):
    # Preseason / offseason returns 0 props — a normal day, not a failure.
    stub([])
    assert bi.signals("nfl") == []


def test_bad_payload_raises(stub):
    stub([], success=False)
    with pytest.raises(bi.BettingInsiderError, match="unexpected payload"):
        bi.signals("mlb")


# ── sharp_moves filter ─────────────────────────────────────────────────────

def test_sharp_moves_filters_and_sorts_by_absolute_move(monkeypatch):
    rows = [
        {"pinnacle_over_move_pct": 2.0},    # below threshold
        {"pinnacle_over_move_pct": -37.0},
        {"pinnacle_over_move_pct": 12.0},
        {"pinnacle_over_move_pct": None},   # no opening price
    ]
    monkeypatch.setattr(bi, "signals", lambda sport: rows)
    out = bi.sharp_moves("mlb", min_move_pct=5.0)
    assert [r["pinnacle_over_move_pct"] for r in out] == [-37.0, 12.0]
