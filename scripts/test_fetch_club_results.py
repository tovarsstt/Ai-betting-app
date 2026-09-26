"""
Tests for fetch_club_results.py's pure logic: date reformatting, row parsing,
season-code calculation, and cache read/write. Deliberately never calls
fetch() — no network access in tests, ever.
"""
import datetime
from pathlib import Path

from fetch_club_results import _reformat_row, _season_codes, load_cached, save_cache


# ── _reformat_row ────────────────────────────────────────────────────────────
def test_reformat_row_parses_four_digit_year():
    row = {"Date": "15/08/2025", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
           "FTHG": "2", "FTAG": "1"}
    out = _reformat_row(row, "Premier League")
    assert out["date"] == "2025-08-15"
    assert out["home_team"] == "Arsenal" and out["away_team"] == "Chelsea"
    assert out["home_score"] == 2 and out["away_score"] == 1
    assert out["neutral"] == "FALSE"
    assert out["league"] == "Premier League"


def test_reformat_row_parses_two_digit_year():
    row = {"Date": "03/09/17", "HomeTeam": "Barcelona", "AwayTeam": "Betis",
           "FTHG": "5", "FTAG": "0"}
    out = _reformat_row(row, "La Liga")
    assert out["date"] == "2017-09-03"


def test_reformat_row_returns_none_on_missing_score():
    row = {"Date": "15/08/2025", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
           "FTHG": "", "FTAG": ""}
    assert _reformat_row(row, "Premier League") is None


def test_reformat_row_returns_none_on_unparseable_date():
    row = {"Date": "not-a-date", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
           "FTHG": "1", "FTAG": "1"}
    assert _reformat_row(row, "Premier League") is None


def test_reformat_row_returns_none_on_missing_team():
    row = {"Date": "15/08/2025", "HomeTeam": "", "AwayTeam": "Chelsea",
           "FTHG": "1", "FTAG": "1"}
    assert _reformat_row(row, "Premier League") is None


# ── _season_codes ─────────────────────────────────────────────────────────────
def test_season_codes_after_july_starts_with_new_season():
    codes = _season_codes(datetime.date(2026, 8, 1), n=3)
    assert codes == ["2627", "2526", "2425"]


def test_season_codes_before_july_uses_prior_season_start():
    codes = _season_codes(datetime.date(2026, 3, 1), n=3)
    assert codes == ["2526", "2425", "2324"]


def test_season_codes_returns_requested_count():
    assert len(_season_codes(datetime.date(2026, 1, 1), n=1)) == 1


# ── cache round-trip (shared csv.DictWriter/DictReader shape) ────────────────
SAMPLE_ROWS = [
    {"date": "2025-08-15", "home_team": "Arsenal", "away_team": "Chelsea",
     "home_score": 2, "away_score": 1, "neutral": "FALSE", "league": "Premier League"},
    {"date": "2025-08-16", "home_team": "Barcelona", "away_team": "Betis",
     "home_score": 5, "away_score": 0, "neutral": "FALSE", "league": "La Liga"},
]


def test_save_cache_writes_file_and_returns_row_count(tmp_path: Path):
    dest = tmp_path / "club_results.csv"
    n = save_cache(SAMPLE_ROWS, path=dest)
    assert n == 2
    assert dest.exists()


def test_load_cached_round_trips_the_written_rows(tmp_path: Path):
    dest = tmp_path / "club_results.csv"
    save_cache(SAMPLE_ROWS, path=dest)
    rows = load_cached(path=dest)
    assert len(rows) == 2
    assert rows[0]["home_team"] == "Arsenal"
    assert rows[0]["league"] == "Premier League"
    assert rows[0]["home_score"] == "2"  # csv round-trip -> string, same as international


def test_load_cached_returns_empty_list_when_no_cache_exists(tmp_path: Path):
    missing = tmp_path / "does_not_exist.csv"
    assert load_cached(path=missing) == []
