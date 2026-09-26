"""
Tests for the cache read/write side of fetch_international_results.py.
Deliberately does NOT call fetch() — no network access in tests, ever.
"""
from pathlib import Path

from fetch_international_results import load_cached, save_cache

SAMPLE_CSV = (
    "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
    "2026-06-27,DR Congo,Uzbekistan,3,1,FIFA World Cup,Atlanta,United States,TRUE\n"
    "2026-06-28,South Africa,Canada,0,1,FIFA World Cup,Inglewood,United States,TRUE\n"
)


def test_save_cache_writes_file_and_returns_row_count(tmp_path: Path):
    dest = tmp_path / "international_results.csv"
    n = save_cache(SAMPLE_CSV, path=dest)
    assert n == 2
    assert dest.exists()


def test_load_cached_round_trips_the_written_rows(tmp_path: Path):
    dest = tmp_path / "international_results.csv"
    save_cache(SAMPLE_CSV, path=dest)
    rows = load_cached(path=dest)
    assert len(rows) == 2
    assert rows[0]["home_team"] == "DR Congo"
    assert rows[0]["home_score"] == "3"


def test_load_cached_returns_empty_list_when_no_cache_exists(tmp_path: Path):
    missing = tmp_path / "does_not_exist.csv"
    assert load_cached(path=missing) == []
