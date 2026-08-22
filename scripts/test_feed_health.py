"""Tests for scripts/feed_health.py — offline: `probe` is monkeypatched so the
suite never touches a live host (and never depends on today's weather)."""
import urllib.error

import pytest

import feed_health as fh

FEEDS = (
    fh.Feed("espn-tennis", "fetch_tennis_ratings.py",
            "https://sports.core.api.espn.com/x", ("tennis",)),
    fh.Feed("linemate", "linemate.py", "https://api.linemate.io/x", ()),
)


def _freeze(monkeypatch, results: dict):
    monkeypatch.setattr(fh, "probe",
                        lambda feed, timeout=fh.TIMEOUT: results[feed.name])


# ── Verdict logic ───────────────────────────────────────────────────────────

def test_all_up_and_current_is_ok(monkeypatch):
    _freeze(monkeypatch, {"espn-tennis": {"reachable": True, "http": 200, "error": None},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={"tennis": {"status": "OK", "age_days": 1}})
    assert rep["worst"] == "OK"
    assert rep["feeds"]["espn-tennis"]["verdict"] == "OK"


def test_unreachable_source_is_dead_even_if_data_looks_fresh(monkeypatch):
    # The exact shape of the bug: the file on disk can look recent while the
    # source that maintains it has been refusing every request.
    _freeze(monkeypatch, {"espn-tennis": {"reachable": False, "http": 403, "error": "HTTP 403"},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={"tennis": {"status": "OK", "age_days": 0}})
    assert rep["feeds"]["espn-tennis"]["verdict"] == "DEAD"
    assert rep["worst"] == "DEAD"


def test_reachable_but_stale_data_is_stale(monkeypatch):
    _freeze(monkeypatch, {"espn-tennis": {"reachable": True, "http": 200, "error": None},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={"tennis": {"status": "STALE", "age_days": 32}})
    assert rep["feeds"]["espn-tennis"]["verdict"] == "STALE"
    assert rep["worst"] == "STALE"


def test_dead_outranks_stale_in_the_summary(monkeypatch):
    _freeze(monkeypatch, {"espn-tennis": {"reachable": False, "http": None, "error": "timeout"},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={"tennis": {"status": "STALE", "age_days": 40}})
    assert rep["worst"] == "DEAD"


def test_feed_with_no_freshness_keys_is_judged_on_reachability_only(monkeypatch):
    # linemate/betting_insider write no cached file — they can only be up or down.
    _freeze(monkeypatch, {"espn-tennis": {"reachable": True, "http": 200, "error": None},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={"tennis": {"status": "OK", "age_days": 0}})
    assert rep["feeds"]["linemate"]["data_stale"] is False
    assert rep["feeds"]["linemate"]["verdict"] == "OK"


def test_missing_freshness_entry_does_not_crash(monkeypatch):
    _freeze(monkeypatch, {"espn-tennis": {"reachable": True, "http": 200, "error": None},
                          "linemate": {"reachable": True, "http": 200, "error": None}})
    rep = fh.check(FEEDS, freshness={})
    assert rep["feeds"]["espn-tennis"]["verdict"] == "OK"


# ── probe() itself ──────────────────────────────────────────────────────────

def test_probe_reports_http_error_without_raising(monkeypatch):
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(fh.urllib.request, "urlopen", boom)
    res = fh.probe(FEEDS[0])
    assert res["reachable"] is False
    assert res["http"] == 403


def test_probe_adds_the_espn_user_agent_hint_on_403(monkeypatch):
    """The 403 is caused by sending a browser UA; the hint must say so, because
    the instinctive fix is to add one and that makes it permanent."""
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(fh.urllib.request, "urlopen", boom)
    assert "do NOT add one" in fh.probe(FEEDS[0])["error"]


def test_probe_survives_a_network_failure(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("connection refused")
    monkeypatch.setattr(fh.urllib.request, "urlopen", boom)
    res = fh.probe(FEEDS[0])
    assert res["reachable"] is False and res["http"] is None


def test_probe_treats_an_empty_200_as_broken(monkeypatch):
    class FakeResp:
        status = 200
        def read(self, n=0): return b""
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(fh.urllib.request, "urlopen", lambda req, timeout=0: FakeResp())
    res = fh.probe(FEEDS[0])
    assert res["reachable"] is False
    assert res["error"] == "empty response"


def test_probe_sends_no_user_agent(monkeypatch):
    """A probe that passes where the fetcher fails is worse than no probe."""
    seen = {}

    class FakeResp:
        status = 200
        def read(self, n=0): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def capture(req, timeout=0):
        seen["headers"] = dict(req.header_items())
        return FakeResp()

    monkeypatch.setattr(fh.urllib.request, "urlopen", capture)
    fh.probe(FEEDS[0])
    assert not any(k.lower() == "user-agent" for k in seen["headers"])


# ── Registry sanity ─────────────────────────────────────────────────────────

def test_every_registered_feed_has_a_script_and_url():
    for f in fh.FEEDS:
        assert f.script.endswith(".py")
        assert f.url.startswith("http")


def test_registry_covers_the_feeds_that_silently_died():
    names = {f.name for f in fh.FEEDS}
    assert {"espn-tennis-ranks", "espn-nfl"} <= names


def test_no_quota_metered_host_is_probed():
    """CLAUDE.md: never call the Odds API / BallDontLie outside real usage."""
    banned = ("the-odds-api.com", "balldontlie", "api-football", "api-sports.io")
    for f in fh.FEEDS:
        assert not any(b in f.url for b in banned), f.name
