"""Tests for scripts/linemate.py — all offline: _get is monkeypatched, so the
suite never touches the live Linemate API (same rule the odds feeds follow)."""
import pytest

import linemate as lm


# ── Fixtures shaped exactly like the live payloads (captured 2026-08-19) ─────

TRENDS_RAW = [{
    "gameId": "20260819-SEA-MIL",
    "timestamp": "2026-08-19T23:40:00.000+00:00",
    "type": "player",
    "player": {"fullName": "Taylor Ward", "position": "LF"},
    "team": {"code": "SEA", "name": "Mariners"},
    "opposingTeam": {"code": "MIL", "name": "Brewers"},
    "home": False,
    "line": 1.5,
    "outcome": "over",
    "market": {
        "type": "OVER_UNDER",
        "name": "HITTER_HITS",
        "books": {
            "caesars": {"over": {"current": {"value": 1.5,
                                             "odds": {"decimal": 2.2, "american": 120}},
                                 "opening": None}},
            "draftkings": {"over": {"current": {"value": 1.5,
                                                "odds": {"decimal": 2.45, "american": 145}},
                                    "opening": None}},
            # A book that lists the market but hasn't posted a price yet.
            "fanduel": {"over": {"current": None, "opening": None}},
        },
    },
    "signals": [{"type": "RECENT_FORM", "description": "Hit in 10 of last 11 games",
                 "hitRecord": {"games": 11, "hits": 10, "hitRate": 90.909}}],
}]

INJURIES_RAW = {
    "JAX": [
        {"fullName": "Travis Hunter", "position": "WR", "injury": "Knee", "status": "IR"},
        {"fullName": "Dyami Brown", "position": "WR",
         "injury": "Coach's Decision", "status": "INACTIVE"},
    ],
    "SEA": "not-a-list",  # malformed team must be skipped, not crash
}

RANKINGS_RAW = [
    {"code": "SEA", "name": "Seahawks", "city": "Seattle", "gamesPlayed": 17,
     "streak": "W2",
     "hitRecords": {"againstTheSpread": {"games": 17, "hits": 12},
                    "homeAgainstTheSpread": {"games": 8, "hits": 4},
                    "totalOver": {"games": 0, "hits": 0}}},
    {"name": "No Code Team"},  # missing code must be skipped
]


@pytest.fixture
def stub_get(monkeypatch):
    """Route every _get through a routing table keyed on the path suffix."""
    def _install(table: dict):
        def fake(path, timeout=lm.TIMEOUT):
            for suffix, payload in table.items():
                if path.endswith(suffix):
                    return payload
            raise AssertionError(f"unexpected path {path}")
        monkeypatch.setattr(lm, "_get", fake)
    return _install


# ── League validation ───────────────────────────────────────────────────────

def test_unknown_league_is_rejected_before_any_request():
    with pytest.raises(lm.LinemateError, match="unknown league"):
        lm.trends("quidditch")


def test_league_slug_is_case_insensitive(stub_get):
    stub_get({"v1/trends/straights": TRENDS_RAW})
    assert lm.trends("EPL")[0]["subject"] == "Taylor Ward"


def test_tennis_is_not_claimed_as_covered():
    # Linemate has no tennis feed; the map must not pretend otherwise.
    assert "TENNIS" not in lm.SPORT_LEAGUES


# ── Trends ──────────────────────────────────────────────────────────────────

def test_trend_picks_the_best_price_across_books(stub_get):
    stub_get({"v1/trends/straights": TRENDS_RAW})
    t = lm.trends("mlb")[0]
    assert t["best_decimal"] == 2.45
    assert t["best_book"] == "draftkings"


def test_trend_counts_every_book_offering_the_market(stub_get):
    stub_get({"v1/trends/straights": TRENDS_RAW})
    assert lm.trends("mlb")[0]["books_offering"] == 3


def test_trend_carries_quantified_signal_hit_record(stub_get):
    stub_get({"v1/trends/straights": TRENDS_RAW})
    sig = lm.trends("mlb")[0]["signals"][0]
    assert sig["games"] == 11 and sig["hits"] == 10
    assert sig["type"] == "RECENT_FORM"


def test_line_move_is_none_when_opening_absent(stub_get):
    # Linemate never populates `opening` — this must read n/a, never a fake 0%.
    stub_get({"v1/trends/straights": TRENDS_RAW})
    t = lm.trends("mlb")[0]
    assert t["opening_decimal"] is None
    assert t["line_move_pct"] is None


def test_trends_rejects_non_list_payload(stub_get):
    stub_get({"v1/trends/straights": {"error": "nope"}})
    with pytest.raises(lm.LinemateError, match="expected list"):
        lm.trends("mlb")


# ── Injuries ────────────────────────────────────────────────────────────────

def test_injuries_normalises_players_and_skips_malformed_teams(stub_get):
    stub_get({"v3/teams/injuries": INJURIES_RAW})
    inj = lm.injuries("nfl")
    assert "SEA" not in inj
    assert inj["JAX"][0] == {"name": "Travis Hunter", "position": "WR",
                             "injury": "Knee", "status": "IR"}


def test_injuries_keeps_coach_decision_inactives(stub_get):
    # Preseason signal ESPN omits — it must survive normalisation.
    stub_get({"v3/teams/injuries": INJURIES_RAW})
    statuses = {p["status"] for p in lm.injuries("nfl")["JAX"]}
    assert "INACTIVE" in statuses


# ── Team records ────────────────────────────────────────────────────────────

def test_team_records_computes_hit_rates_from_real_counts(stub_get):
    stub_get({"v3/teams/rankings": RANKINGS_RAW})
    rec = lm.team_records("nfl")["SEA"]
    assert rec["ats_hit_rate"] == round(12 / 17, 4)
    assert rec["home_ats_hit_rate"] == 0.5


def test_team_records_returns_none_for_zero_game_samples(stub_get):
    # 0 games must be n/a, not a 0% hit rate that reads like a real stat.
    stub_get({"v3/teams/rankings": RANKINGS_RAW})
    assert lm.team_records("nfl")["SEA"]["total_over_hit_rate"] is None


def test_team_records_skips_teams_without_a_code(stub_get):
    stub_get({"v3/teams/rankings": RANKINGS_RAW})
    assert list(lm.team_records("nfl")) == ["SEA"]


# ── Sport-level aggregation ─────────────────────────────────────────────────

def test_trends_for_sport_skips_dark_leagues(monkeypatch):
    # A league erroring (or out of season) must not kill the whole sport.
    def fake(league):
        if league == "epl":
            return [{"subject": "x"}]
        raise lm.LinemateError("dark")
    monkeypatch.setattr(lm, "trends", fake)
    assert lm.trends_for_sport("SOCCER") == [{"subject": "x"}]


def test_trends_for_sport_unknown_sport_is_empty(monkeypatch):
    assert lm.trends_for_sport("QUIDDITCH") == []
