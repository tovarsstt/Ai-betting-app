from v12_omniscience.engine.simulators import MonteCarloSimulator
import pickle
import pandas as pd
import json
import os

def analyze_legacy_parlay():
    mc = MonteCarloSimulator(iterations=25000)
    
    # Load model if it exists
    model_path = "v12_omniscience/models/v12_omniscience_ensemble.pkl"
    meta_path = "v12_omniscience/models/v12_model_metadata.json"
    
    legs = [
        {"player": "LeBron James", "line": 4.5, "type": "ast", "avg": 8.0},
        {"player": "Jalen Duren", "line": 24.5, "type": "p+r", "avg": 28.0},
        {"player": "Cooper Flagg", "line": 25.5, "type": "p+a+r", "avg": 30.0},
        {"player": "Saddiq Bey", "line": 14.5, "type": "pts", "avg": 17.5},
        {"player": "Victor Wembanyama", "line": 34.5, "type": "p+a+r", "avg": 38.0},
        {"player": "Desmond Bane", "line": 16.5, "type": "pts", "avg": 22.0},
        {"player": "Matas Buzelis", "line": 15.5, "type": "pts", "avg": 14.0}, # Risky
        {"player": "Donovan Clingan", "line": 20.5, "type": "p+r", "avg": 23.0},
        {"player": "Devin Booker", "line": 19.5, "type": "pts", "avg": 26.0}
    ]
    
    total_parlay_prob = 1.0
    analysis = []
    
    print("🧠 V12 GOD-ENGINE PARLAY SCAN...")
    
    for leg in legs:
        # Player props usually follow Poisson
        prob = mc.simulate_player_prop(leg['avg'], leg['line'])
        total_parlay_prob *= prob
        analysis.append({
            "player": leg['player'],
            "v12_prob": round(prob, 4),
            "edge": round(prob - (1 / 1.35), 4) # Simplified edge calc
        })
    
    implied_odds = 1 / total_parlay_prob
    print(f"📊 PROJECTED TOTAL PROBABILITY: {round(total_parlay_prob * 100, 2)}%")
    print(f"📊 V12 CALCULATED FAIR ODDS: {round(implied_odds, 2)}")
    print(f"💰 MARKET ODDS: 16.86")
    
    edge = (total_parlay_prob - (1 / 16.86)) * 100
    print(f"📈 TOTAL MATHEMATICAL EDGE: {round(edge, 2)}%")
    
    with open("v12_omniscience/data/parlay_analysis.json", "w") as f:
        json.dump({
            "total_prob": total_parlay_prob,
            "fair_odds": implied_odds,
            "edge": edge,
            "legs": analysis
        }, f)

if __name__ == "__main__":
    analyze_legacy_parlay()
