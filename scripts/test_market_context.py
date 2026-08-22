"""Tests for scripts/market_context.py — offline: the upstream modules and the
cache directory are monkeypatched, so nothing here touches Linemate or Betting
Insider and nothing writes into the real data/_cache."""
import json
import time

import pytest

import market_context as mc


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "CACHE_DIR", tmp_path / "_cache")


# ── Team matching: the safety-critical part ─────────────────────────────────
# Attaching the WRONG team's injuries to a pick is worse than attaching none.

NFL = {
    "BAL": {"name": "Ravens", "city": "Baltimore"},
    "SEA": {"name": "Seahawks", "city": "Seattle"},
    "LA":  {"name": "Rams", "city": "Los Angeles"},
    "LAC": {"name": "Chargers", "city": "Los Angeles"},
}
EPL = {
    "BRI": {"name": "Brighton & Hove Albion FC", "city": ""},
    "ARS": {"name": "Arsenal FC", "city": ""},
    "BOU": {"name": "AFC Bournemouth", "city": ""},
    "MCI": {"name": "Manchester City FC", "city": ""},
    "MUN": {"name": "Manchester United FC", "city": ""},
}


def test_matches_city_plus_nickname():
    assert mc.match_team("Baltimore Ravens", NFL) == "BAL"
    assert mc.match_team("Seattle Seahawks", NFL) == "SEA"


def test_matches_bare_nickname_and_code():
    assert mc.match_team("Ravens", NFL) == "BAL"
    assert mc.match_team("BAL", NFL) == "BAL"


def test_club_suffixes_are_ignored():
    assert mc.match_team("Arsenal", EPL) == "ARS"
    assert mc.match_team("Bournemouth", EPL) == "BOU"   # vs "AFC Bournemouth"


def test_partial_club_name_resolves_via_token_subset():
    # The app says "Brighton"; Linemate says "Brighton & Hove Albion FC".
    assert mc.match_team("Brighton", EPL) == "BRI"


def test_two_manchester_clubs_are_not_confused():
    assert mc.match_team("Manchester City", EPL) == "MCI"
    assert mc.match_team("Manchester United", EPL) == "MUN"


def test_ambiguous_city_refuses_rather_than_guessing():
    # Two LA teams — "Los Angeles" alone must NOT silently pick one.
    assert mc.match_team("Los Angeles", NFL) is None


def test_unknown_team_returns_none():
    assert mc.match_team("Toronto Maple Leafs", NFL) is None


def test_empty_inputs_are_safe():
    assert mc.match_team("", NFL) is None
    assert mc.match_team("Ravens", {}) is None
    assert mc.match_team("!!!", NFL) is None


def test_normalise_strips_noise_and_punctuation():
    assert mc.normalise("Brighton & Hove Albion FC") == "brighton hove albion"
    assert mc.normalise("Arsenal F.C.") == "arsenal"


# ── TTL cache ───────────────────────────────────────────────────────────────

def test_producer_runs_once_within_the_ttl():
    calls = []

    def producer():
        calls.append(1)
        return {"v": len(calls)}

    v1, m1 = mc.cached("k", 600, producer)
    v2, m2 = mc.cached("k", 600, producer)
    assert calls == [1]                  # upstream hit exactly once
    assert v1 == v2
    assert m1["from_cache"] is False and m2["from_cache"] is True


def test_expired_cache_refetches():
    calls = []

    def producer():
        calls.append(1)
        return len(calls)

    mc.cached("k", ttl=0, producer=producer)
    time.sleep(0.01)
    v, meta = mc.cached("k", ttl=0, producer=producer)
    assert len(calls) == 2
    assert v == 2 and meta["from_cache"] is False


def test_upstream_failure_serves_stale_cache_and_says_so():
    """Old ATS records beat no ATS records — but the caller must be told."""
    mc.cached("k", 600, lambda: {"good": True})
    time.sleep(0.01)

    def boom():
        raise RuntimeError("upstream 503")

    v, meta = mc.cached("k", ttl=0, producer=boom)
    assert v == {"good": True}
    assert meta["stale"] is True
    assert "503" in meta["error"]


def test_upstream_failure_with_no_cache_returns_none_not_an_exception():
    def boom():
        raise RuntimeError("dead")
    v, meta = mc.cached("cold", 600, boom)
    assert v is None
    assert meta["error"] == "dead"


def test_corrupt_cache_file_is_ignored(monkeypatch):
    mc.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mc._cache_path("k").write_text("{not json")
    v, meta = mc.cached("k", 600, lambda: "fresh")
    assert v == "fresh" and meta["from_cache"] is False


def test_cache_key_is_filesystem_safe():
    p = mc._cache_path("sharp_mlb?x=1/../etc")
    assert "/" not in p.name and ".." not in p.name


# ── team_context ────────────────────────────────────────────────────────────

def test_team_context_attaches_ats_and_injuries(monkeypatch):
    monkeypatch.setattr(mc.lmt, "team_records", lambda lg: {
        "BAL": {"name": "Ravens", "city": "Baltimore", "ats_hit_rate": 0.41}})
    monkeypatch.setattr(mc.lmt, "injuries", lambda lg: {
        "BAL": [{"name": "Justice Hill", "position": "RB", "status": "IR"}]})
    ctx = mc.team_context("NFL", "Baltimore Ravens")
    assert ctx["matched"] == "BAL"
    assert ctx["ats"]["ats_hit_rate"] == 0.41
    assert ctx["injuries"][0]["name"] == "Justice Hill"


def test_unmatched_team_says_so_without_erroring(monkeypatch):
    monkeypatch.setattr(mc.lmt, "team_records", lambda lg: {
        "BAL": {"name": "Ravens", "city": "Baltimore"}})
    monkeypatch.setattr(mc.lmt, "injuries", lambda lg: {})
    ctx = mc.team_context("NFL", "Some FC")
    assert ctx["matched"] is None
    assert ctx["ats"] is None
    assert "not matched" in ctx["note"]


def test_uncovered_sport_is_declared_not_stubbed():
    # Linemate has no tennis. Saying so beats returning empty stats that read
    # like "this player has no injuries".
    ctx = mc.team_context("TENNIS", "Jannik Sinner")
    assert ctx["matched"] is None
    assert "does not cover" in ctx["note"]


def test_dead_upstream_does_not_raise(monkeypatch):
    def boom(lg):
        raise mc.lmt.LinemateError("down")
    monkeypatch.setattr(mc.lmt, "team_records", boom)
    ctx = mc.team_context("NFL", "Baltimore Ravens")
    assert ctx["matched"] is None       # degraded, not crashed


# ── sharp_context ───────────────────────────────────────────────────────────

def test_sharp_context_returns_moves(monkeypatch):
    monkeypatch.setattr(mc.tbi, "sharp_moves",
                        lambda sp, m: [{"player": "X", "pinnacle_over_move_pct": -37.0}])
    out = mc.sharp_context("mlb")
    assert out["count"] == 1


def test_sharp_context_declines_uncovered_sports():
    for sport in ("soccer", "tennis"):
        out = mc.sharp_context(sport)
        assert out["moves"] is None
        assert "covers only" in out["note"]


def test_sharp_context_survives_a_dead_feed(monkeypatch):
    def boom(sp, m):
        raise mc.tbi.BettingInsiderError("503")
    monkeypatch.setattr(mc.tbi, "sharp_moves", boom)
    out = mc.sharp_context("mlb")
    assert out["moves"] is None and "503" in out["note"]


# ── match_context ───────────────────────────────────────────────────────────

def test_match_context_carries_both_sides_and_the_caveat(monkeypatch):
    monkeypatch.setattr(mc.lmt, "team_records", lambda lg: {
        "BAL": {"name": "Ravens", "city": "Baltimore"},
        "CHI": {"name": "Bears", "city": "Chicago"}})
    monkeypatch.setattr(mc.lmt, "injuries", lambda lg: {})
    monkeypatch.setattr(mc.tbi, "sharp_moves", lambda sp, m: [])
    ctx = mc.match_context("NFL", "Baltimore Ravens", "Chicago Bears")
    assert ctx["home"]["matched"] == "BAL"
    assert ctx["away"]["matched"] == "CHI"
    # The caveat is load-bearing: these are cited stats, not model output.
    assert "never overrides the engine" in ctx["caveat"]


# ── Empty injury feed must not read as "everyone is fit" ────────────────────

def test_league_wide_empty_injuries_is_treated_as_no_coverage(monkeypatch):
    """Linemate lists all 23 EPL clubs with zero injuries — it has no soccer
    injury feed. Reporting that as 'none ruled out' would claim a fully fit
    Premier League squad."""
    monkeypatch.setattr(mc.lmt, "team_records", lambda lg: {
        "ARS": {"name": "Arsenal FC", "city": ""},
        "CHE": {"name": "Chelsea FC", "city": ""}})
    monkeypatch.setattr(mc.lmt, "injuries", lambda lg: {"ARS": [], "CHE": []})
    ctx = mc.team_context("SOCCER", "Arsenal")
    assert ctx["matched"] == "ARS"
    assert ctx["injuries"] is None          # None = unknown, not "healthy"
    assert ctx["injuries_covered"] is False
    assert "NOT a clean bill of health" in ctx["note"]


def test_a_genuinely_empty_team_in_a_covered_league_stays_empty(monkeypatch):
    """If OTHER teams have injuries, the league IS covered, so this team really
    does have nobody listed — that empty list is real data."""
    monkeypatch.setattr(mc.lmt, "team_records", lambda lg: {
        "BAL": {"name": "Ravens", "city": "Baltimore"},
        "CHI": {"name": "Bears", "city": "Chicago"}})
    monkeypatch.setattr(mc.lmt, "injuries", lambda lg: {
        "BAL": [], "CHI": [{"name": "X", "status": "IR"}]})
    ctx = mc.team_context("NFL", "Baltimore Ravens")
    assert ctx["injuries"] == []
    assert ctx["injuries_covered"] is True
