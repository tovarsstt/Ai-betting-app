"""Endpoint test for /chaos-slate — uses FastAPI TestClient, no external network."""
from fastapi.testclient import TestClient
import edge_api


def test_chaos_slate_returns_tiered_card_and_weather():
    client = TestClient(edge_api.app)
    payload = {
        "bankroll": 200.0,
        "matches": [
            {
                "home": {"name": "Canada", "gf": 1, "ga": 1, "gp": 1, "strength": 0.02},
                "away": {"name": "Bosnia", "gf": 1, "ga": 1, "gp": 1, "strength": 0.01},
                "market_home": 0.50, "market_draw": 0.27, "market_away": 0.23,
                "fav_decimal_odds": 1.83, "draw_decimal_odds": 3.40,
                "model_home": 0.46, "model_draw": 0.31, "model_away": 0.23,
                "home_tag": "CAN_DRAW",
                "win_prob": 0.58, "decimal_odds": 3.40,
                "market": "Draw (X)", "side": "Draw"
            }
        ],
    }
    r = client.post("/chaos-slate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["weather"]["n_matches"] == 1
    assert body["chaos"][0]["grade"] == "LITE"
    assert "card" in body and len(body["card"]) >= 1
