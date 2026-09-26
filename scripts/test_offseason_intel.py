"""Tests for the offseason intel fetchers' pure logic — fixtures, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_nfl_rosters import diff_rosters
from fetch_summer_league import aggregate_players, parse_game


def test_roster_diff_adds_removes_and_qb_flag():
    old = {"Kansas City Chiefs": [{"name": "A QB", "pos": "QB", "exp": 8},
                                  {"name": "B WR", "pos": "WR", "exp": 3}]}
    new = {"Kansas City Chiefs": [{"name": "C QB", "pos": "QB", "exp": 0},
                                  {"name": "B WR", "pos": "WR", "exp": 3}]}
    d = diff_rosters(old, new)
    e = d["Kansas City Chiefs"]
    assert e["added"] == ["C QB"] and e["removed"] == ["A QB"]
    assert e["qb_changes"] == {"in": ["C QB"], "out": ["A QB"]}
    assert 0 < e["churn_share"] <= 1


def test_roster_diff_silent_when_unchanged():
    same = {"Team": [{"name": "X", "pos": "RB", "exp": 2}]}
    assert diff_rosters(same, same) == {}


def _summary_fixture():
    return {"boxscore": {"players": [
        {"statistics": [{
            "names": ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO",
                      "STL", "BLK", "OREB", "DREB", "PF", "+/-"],
            "athletes": [
                {"athlete": {"id": "1", "displayName": "Rook One"},
                 "stats": ["30", "22", "8-15", "2-5", "4-6", "7", "3", "2",
                           "1", "0", "2", "5", "3", "+10"]},
                {"athlete": {"id": "2", "displayName": "Bench Guy"},
                 "stats": ["0", "0", "0-0", "0-0", "0-0", "0", "0", "0",
                           "0", "0", "0", "0", "0", "0"]},
            ]}]}]}}


def test_parse_game_extracts_lines_and_officiating():
    rows, off = parse_game(_summary_fixture())
    assert len(rows) == 1                       # 0-minute rows dropped
    r = rows[0]
    assert (r["name"], r["pts"], r["fta"], r["pf"]) == ("Rook One", 22.0, 6.0, 3.0)
    assert off["fta"] == 6.0 and off["pf"] == 3.0


def test_aggregate_players_averages_across_games():
    rows = [{"id": "1", "name": "Rook One", "min": 30, "pts": 22, "reb": 7,
             "ast": 3, "stl": 1, "blk": 0, "to": 2, "pf": 3, "fta": 6},
            {"id": "1", "name": "Rook One", "min": 20, "pts": 10, "reb": 3,
             "ast": 1, "stl": 0, "blk": 1, "to": 1, "pf": 1, "fta": 2}]
    agg = aggregate_players(rows)
    assert agg[0]["games"] == 2
    assert agg[0]["ptspg"] == 16.0
    assert agg[0]["minpg"] == 25.0
