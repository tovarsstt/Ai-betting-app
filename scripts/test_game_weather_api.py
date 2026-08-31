"""Endpoint test for /game-weather — FastAPI TestClient, indoor path only
(outdoor path hits free network APIs, exercised manually per debug rule)."""
from fastapi.testclient import TestClient
import edge_api


client = TestClient(edge_api.app)


def test_dome_game_short_circuits_no_network():
    r = client.post("/game-weather", json={
        "city": "Atlanta", "state": "GA", "indoor": True,
        "kickoff": "2026-09-07T18:00Z",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["indoor"] is True
    assert body["weather"] is None
    assert body["impact"]["level"] == "NONE"


def test_missing_city_is_422():
    r = client.post("/game-weather", json={"kickoff": "2026-09-07T18:00Z"})
    assert r.status_code == 422
