"""Tests for fetch_tennis_rank_history.py and tennis_pit_backtest.py.

Offline: every network call is monkeypatched. The bug these guard against is
worth naming — `/rankings/1` under the WTA league path returns HTTP 200 with the
ATP ranking, so a hardcoded id silently filled the WTA archive with men's
players and the WTA backtest could not resolve a single competitor.
"""
import json

import pytest

import fetch_tennis_rank_history as rh
import tennis_pit_backtest as pit


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "OUT", tmp_path / "hist.json")


# ── Ranking id must be DISCOVERED, never assumed ────────────────────────────

def test_ranking_id_is_read_from_the_index(monkeypatch):
    monkeypatch.setattr(rh, "_get", lambda u: {
        "items": [{"$ref": "http://x/rankings/2?lang=en"}]})
    assert rh.ranking_id("wta", 2026, 32) == "2"


def test_missing_index_yields_no_id(monkeypatch):
    monkeypatch.setattr(rh, "_get", lambda u: {"items": []})
    assert rh.ranking_id("atp", 2026, 99) is None


def test_wrong_tour_payload_is_refused_loudly(monkeypatch):
    """A 200 is not proof you got what you asked for."""
    monkeypatch.setattr(rh, "ranking_id", lambda t, s, w: "1")
    monkeypatch.setattr(rh, "_get", lambda u: {
        "shortName": "ATP", "ranks": [], "lastUpdated": "2026-08-06T00:00Z"})
    with pytest.raises(RuntimeError, match="tour mismatch"):
        rh.week_snapshot("wta", 2026, 32, {})


def test_matching_tour_payload_is_accepted(monkeypatch):
    monkeypatch.setattr(rh, "ranking_id", lambda t, s, w: "2")
    monkeypatch.setattr(rh, "_get", lambda u: {
        "shortName": "WTA", "lastUpdated": "2026-08-06T00:00Z",
        "ranks": [{"current": 1, "points": 9000,
                   "athlete": {"$ref": "http://x/athletes/99?lang=en"}}]})
    snap = rh.week_snapshot("wta", 2026, 32, {"99": "Aryna Sabalenka"})
    assert snap["players"]["Aryna Sabalenka"]["rank"] == 1.0


# ── ranking_as_of: the whole point is "what did we know THEN" ───────────────

HIST = {"tours": {"atp": {
    "2026-11": {"date": "2026-03-12", "players": {"A": {"rank": 1, "points": 9000}}},
    "2026-20": {"date": "2026-05-14", "players": {"A": {"rank": 3, "points": 6000}}},
    "2026-32": {"date": "2026-08-06", "players": {"A": {"rank": 5, "points": 4000}}},
}}}


def test_uses_the_snapshot_in_force_on_the_match_date():
    snap = rh.ranking_as_of("atp", "2026-06-01", HIST)
    assert snap["date"] == "2026-05-14"        # most recent AT OR BEFORE


def test_exact_date_match_is_used():
    assert rh.ranking_as_of("atp", "2026-08-06", HIST)["date"] == "2026-08-06"


def test_never_reaches_forward_in_time():
    """The whole failure this replaces: using a LATER snapshot is lookahead."""
    snap = rh.ranking_as_of("atp", "2026-03-20", HIST)
    assert snap["date"] == "2026-03-12"
    assert snap["players"]["A"]["points"] == 9000


def test_before_the_archive_returns_none_not_a_fallback():
    # An honest "cannot measure" beats silently using current ranks.
    assert rh.ranking_as_of("atp", "2026-01-01", HIST) is None


def test_unknown_tour_returns_none():
    assert rh.ranking_as_of("wta", "2026-06-01", HIST) is None


# ── Archive merging ─────────────────────────────────────────────────────────

def test_existing_weeks_are_never_refetched(monkeypatch):
    calls = []

    def fake_snap(tour, season, week, names):
        calls.append((tour, week))
        return {"date": "2026-08-06", "week": week, "season": season,
                "players": {"A": {"rank": 1, "points": 1}}}

    monkeypatch.setattr(rh, "week_snapshot", fake_snap)
    rh.archive(2026, range(32, 33), tours=("atp",))
    first = len(calls)
    rh.archive(2026, range(32, 33), tours=("atp",))
    assert len(calls) == first          # second run fetched nothing


def test_archive_merges_rather_than_overwrites(monkeypatch):
    def fake_snap(tour, season, week, names):
        return {"date": f"2026-0{week}-01", "week": week, "season": season,
                "players": {"A": {"rank": week, "points": 1}}}
    monkeypatch.setattr(rh, "week_snapshot", fake_snap)
    rh.archive(2026, range(1, 2), tours=("atp",))
    out = rh.archive(2026, range(2, 3), tours=("atp",))
    assert out["total_weeks"]["atp"] == 2


# ── Point-in-time backtest: name resolution + leakage guard ────────────────

PLAYERS = {"Jannik Sinner": {"rank": 1, "points": 13450},
           "Carlos Alcaraz": {"rank": 2, "points": 8160},
           "Wang Xinyu": {"rank": 40, "points": 1200},
           "Wang Xiyu": {"rank": 55, "points": 900}}


def test_surname_initial_resolves_against_the_archive():
    assert pit._resolve("Sinner J.", PLAYERS)["rank"] == 1


def test_exact_name_resolves():
    assert pit._resolve("Carlos Alcaraz", PLAYERS)["rank"] == 2


def test_ambiguous_initial_refuses():
    # Wang Xinyu and Wang Xiyu both match "Wang X.".
    assert pit._resolve("Wang X.", PLAYERS) is None


def test_unknown_player_refuses():
    assert pit._resolve("Nobody N.", PLAYERS) is None


def test_probability_favours_more_points():
    p = pit._prob(PLAYERS["Jannik Sinner"], PLAYERS["Wang Xiyu"])
    assert p > 0.9


def test_probability_is_symmetric():
    a = pit._prob(PLAYERS["Jannik Sinner"], PLAYERS["Carlos Alcaraz"])
    b = pit._prob(PLAYERS["Carlos Alcaraz"], PLAYERS["Jannik Sinner"])
    assert a + b == pytest.approx(1.0, abs=1e-9)


def test_equal_points_is_a_coin_flip():
    same = {"rank": 5, "points": 3000}
    assert pit._prob(same, same) == pytest.approx(0.5, abs=1e-9)


def test_rank_fallback_when_points_missing():
    a = {"rank": 1, "points": None}
    b = {"rank": 100, "points": None}
    assert pit._prob(a, b) > 0.6
