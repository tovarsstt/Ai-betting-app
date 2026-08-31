"""Endpoint test for /soccer-live — FastAPI TestClient, no external network."""
from fastapi.testclient import TestClient
import edge_api


client = TestClient(edge_api.app)


def test_soccer_live_prices_lines_in_both_scenarios():
    payload = {
        "league": "Serie A",
        "home": "Lecce",
        "away": "Roma",
        "minute": 35,
        "score_home": 0,
        "score_away": 3,
        "total_sot": 7,
        "lines": [
            {"market": "total", "line": 4.25, "price": 1.40, "side": "over"},
            {"market": "total", "line": 4.5, "price": 2.35, "side": "under"},
            {"market": "handicap_away", "line": -3.25, "price": 1.43},
        ],
    }
    r = client.post("/soccer-live", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK"
    assert body["live"]["score"] == "0-3"
    assert 0.7 <= body["tempo_mult"] <= 1.5
    assert body["probs"]["away"] > 0.99  # 0-3 at 35' is basically done
    assert len(body["lines"]) == 3
    for row in body["lines"]:
        assert "ev_cold" in row and "ev_tempo" in row
    # over 4.25 must NOT look playable cold: exact-4 mass half-loses
    over_425 = body["lines"][0]
    assert over_425["ev_cold"] < -0.15
    assert "Rule 30" in body["market_anchor_note"]


def test_soccer_live_alias_miss_is_flagged_not_silent():
    r = client.post("/soccer-live", json={
        "league": "Serie A", "home": "Fake Team FC", "away": "Roma",
        "minute": 10, "score_home": 0, "score_away": 0,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "NO_RATINGS"
