import sqlite3
import json
from datetime import datetime

def ingest_legacy_parlay():
    db_path = 'v12_omniscience/data/memory_matrix.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Create a "Legacy Prediction" entry for the parlay
    parlay_id = "legacy_v11_parlay_20260308"
    matchup = "LEGACY PARLAY: 9-Leg NBA Multiplex"
    total_odds = 16.86
    bet_amount = 5.0 # Total bet
    
    # Details of the legs for the feature_vector_json (Contextual record)
    legs = [
        {"player": "LeBron James", "prop": "O 4.5 Ast", "odds": 1.35},
        {"player": "Jalen Duren", "prop": "O 24.5 P+R", "odds": 1.44},
        {"player": "Cooper Flagg", "prop": "O 25.5 P+A+R", "odds": 1.44},
        {"player": "Saddiq Bey", "prop": "O 14.5 Pts", "odds": 1.30},
        {"player": "Victor Wembanyama", "prop": "O 34.5 P+A+R", "odds": 1.42},
        {"player": "Desmond Bane", "prop": "O 16.5 Pts", "odds": 1.32},
        {"player": "Matas Buzelis", "prop": "O 15.5 Pts", "odds": 1.44},
        {"player": "Donovan Clingan", "prop": "O 20.5 P+R", "odds": 1.29},
        {"player": "Devin Booker", "prop": "O 19.5 Pts", "odds": 1.32}
    ]
    
    cursor.execute('''
    INSERT OR IGNORE INTO predictions (
        prediction_id, timestamp, matchup, sport, model_name, 
        model_probability, status, feature_vector_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        parlay_id, 
        "2026-03-08 13:06:00", 
        matchup, 
        "NBA", 
        "Legacy_V11", 
        0.06, # ~1/16.86 approx
        "active", 
        json.dumps(legs)
    ))
    
    # 2. Log in Bet Ledger
    cursor.execute('''
    INSERT OR IGNORE INTO bet_ledger (prediction_id, amount_usd, placed_odds, status)
    VALUES (?, ?, ?, ?)
    ''', (parlay_id, bet_amount, total_odds, "active"))
    
    conn.commit()
    conn.close()
    print(f"📥 Legacy Parlay ({parlay_id}) ingested into V12 Accountability Ledger.")

if __name__ == "__main__":
    ingest_legacy_parlay()
