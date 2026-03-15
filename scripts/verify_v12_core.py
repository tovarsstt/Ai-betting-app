import requests
import json

def test_v12_core_api():
    base_url = "http://127.0.0.1:8001"
    
    print("🚀 Verifying V12 Unified Strategy Engine...")

    # Test 1: Soccer (Poisson)
    print("\n[TEST 1] Soccer Matchup (xG Logic)...")
    payload_soccer = {
        "matchup": "Arsenal vs Porto",
        "sport": "soccer",
        "features": {
            "xg_a": 2.1,
            "xg_b": 0.8,
            "market_odds": 1.69
        },
        "narrative_psych_score": 0.5
    }
    try:
        res = requests.post(f"{base_url}/analyze", json=payload_soccer, timeout=5)
        data = res.json()
        if data.get("status") == "V12_SHARP_ACTIVE":
            print("✅ Status Correct: V12_SHARP_ACTIVE")
            block = data["analysis"]["SYNDICATION_BLOCK"]
            print(f"✅ Header: {block['HEADER']}")
            print(f"✅ Model Prob: {block['METRICS']['MODEL_PROB']}")
            print(f"✅ Suggested Stake: {block['RISK_MGMT']['SUGGESTED_STAKE']}")
        else:
            print(f"❌ Error: Unexpected status {data.get('status')}")
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

    # Test 2: NBA (Gaussian)
    print("\n[TEST 2] NBA Matchup (Gaussian Logic)...")
    payload_nba = {
        "matchup": "Lakers vs Celtics",
        "sport": "NBA",
        "features": {
            "proj_a": 114.5,
            "proj_b": 110.0,
            "market_odds": 1.55
        },
        "narrative_psych_score": 0.8
    }
    try:
        res = requests.post(f"{base_url}/analyze", json=payload_nba, timeout=5)
        data = res.json()
        if data.get("status") == "V12_SHARP_ACTIVE":
            print("✅ Status Correct: V12_SHARP_ACTIVE")
            block = data["analysis"]["SYNDICATION_BLOCK"]
            print(f"✅ Model Prob: {block['METRICS']['MODEL_PROB']}")
            print(f"✅ Confidence: {block['RISK_MGMT']['CONFIDENCE']}")
        else:
            print(f"❌ Error: Unexpected status {data.get('status')}")
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    test_v12_core_api()
