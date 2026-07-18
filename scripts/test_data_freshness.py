"""Tests for data_freshness — pure logic on fixed dates, no file dependence
except the audit() smoke test which reads whatever exists."""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_freshness import audit, in_season, season_start, status_for


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def test_in_season_same_year_and_wrapping():
    assert in_season("mlb", date(2026, 7, 18)) is True
    assert in_season("mlb", date(2026, 1, 10)) is False
    assert in_season("nfl", date(2026, 1, 10)) is True      # wraps new year
    assert in_season("nfl", date(2026, 7, 18)) is False
    assert in_season("nba", date(2026, 12, 1)) is True


def test_season_start_wrapping_picks_right_year():
    assert season_start("nfl", date(2026, 1, 10)) == date(2025, 9, 4)
    assert season_start("nfl", date(2026, 10, 1)) == date(2026, 9, 4)
    assert season_start("mlb", date(2026, 7, 18)) == date(2026, 3, 20)


def test_fresh_in_season_is_ok():
    r = status_for("mlb", _dt(2026, 7, 17), date(2026, 7, 18))
    assert r["status"] == "OK"


def test_stale_in_season_flags():
    r = status_for("mlb", _dt(2026, 7, 10), date(2026, 7, 18))
    assert r["status"] == "STALE"
    assert "budget" in r["note"]


def test_offseason_is_informational():
    r = status_for("nba", _dt(2026, 6, 1), date(2026, 7, 18))
    assert r["status"] == "OFFSEASON"


def test_season_boundary_last_season_data():
    # NFL kicks off Sep 4; on Sep 10 with data from June -> boundary hazard
    r = status_for("nfl", _dt(2026, 6, 1), date(2026, 9, 10))
    assert r["status"] == "SEASON_BOUNDARY"
    assert "rosters" in r["note"]


def test_season_boundary_pre_season_window():
    # soccer club starts Aug 8; on Aug 1 with July-1 data -> early warning
    r = status_for("soccer_club", _dt(2026, 7, 1), date(2026, 8, 1))
    assert r["status"] == "SEASON_BOUNDARY"
    # wrapped sport pre-season: NBA Oct 20, on Sep 25 w/ May data -> warning too
    r2 = status_for("nba", _dt(2026, 5, 1), date(2026, 9, 25))
    assert r2["status"] == "SEASON_BOUNDARY"


def test_aliases_follow_parent_sport():
    r = status_for("tennis_form", _dt(2026, 7, 17), date(2026, 7, 18))
    assert r["status"] == "OK"          # uses tennis budget/season


def test_missing_file_reported():
    r = status_for("mlb", None, date(2026, 7, 18))
    assert r["status"] == "MISSING"


def test_audit_smoke_runs_on_real_data():
    rep = audit(date(2026, 7, 18))
    assert "sports" in rep and "worst" in rep
    assert rep["sports"]["mlb"]["status"] in ("OK", "STALE", "SEASON_BOUNDARY", "MISSING")
