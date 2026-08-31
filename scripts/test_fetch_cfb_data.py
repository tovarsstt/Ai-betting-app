"""Parser tests for fetch_cfb_data — pure, no network (debug rule: no live APIs)."""
from fetch_cfb_data import parse_event


def _event(odds=None, rank=14):
    comp = {
        "competitors": [
            {"homeAway": "home", "team": {"displayName": "USC Trojans"},
             "curatedRank": {"current": rank}, "records": [{"summary": "1-0"}], "score": "31"},
            {"homeAway": "away", "team": {"displayName": "San José State Spartans"},
             "curatedRank": {"current": 99}, "records": [{"summary": "0-1"}], "score": "14"},
        ],
    }
    if odds is not None:
        comp["odds"] = [odds]
    return {"name": "SJSU at USC", "date": "2026-09-05T19:30Z",
            "status": {"type": {"description": "Scheduled"}},
            "competitions": [comp]}


def test_parses_teams_ranks_records():
    row = parse_event(_event())
    assert row["home"]["team"] == "USC Trojans"
    assert row["home"]["rank"] == 14
    assert row["away"]["rank"] is None  # 99 = unranked sentinel, not a rank
    assert row["home"]["record"] == "1-0"
    assert row["odds"] is None


def test_parses_dk_line_and_moneylines():
    row = parse_event(_event(odds={
        "provider": {"name": "DraftKings"}, "details": "USC -21.5", "overUnder": 58.5,
        "moneyline": {"home": {"close": {"odds": "-2000"}}, "away": {"close": {"odds": "+1050"}}},
    }))
    assert row["odds"]["details"] == "USC -21.5"
    assert row["odds"]["over_under"] == 58.5
    assert row["odds"]["home_ml"] == "-2000"
    assert row["odds"]["away_ml"] == "+1050"


def test_malformed_event_returns_none():
    assert parse_event({"competitions": [{"competitors": [{}]}]}) is None
