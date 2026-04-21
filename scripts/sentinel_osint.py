import time
import requests
import psycopg2
import os
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

X_RAPID_API_KEY = os.getenv("TWITTER_API_KEY", "YOUR_API_KEY_HERE")

def setup_db():
    if not DB_URL: 
        print("⚠️ DATABASE_URL not found in .env. Run locally without logging.")
        return
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS live_injuries (
                player_name TEXT PRIMARY KEY,
                team TEXT,
                status TEXT,
                news_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ Postgres 'live_injuries' matrix verified.")
    except Exception as e:
        print(f"[-] DB Setup error: {e}")

def parse_osint_feed():
    print(f"\\n[\u26A1 {datetime.now().strftime('%H:%M:%S')}] Sentinel OSINT Agent active. Sweeping Underdog/Rotoworld nodes...")
    
    urgent_keywords = ["OUT", "SCRATCHED", "GAME-TIME DECISION", "QUESTIONABLE", "DOUBTFUL"]
    
    # In production, use your Twitter API or RSS hook here.
    # Ex: url = "https://api.twitter.com/2/tweets/search/recent?query=from:Underdog__NBA"
    
    # For now, we simulate scraping a live feed of injury updates:
    simulated_tweets = [
        {"player": "Joel Embiid", "team": "PHI", "text": "Joel Embiid (knee) will be OUT tonight vs Celtics."},
        {"player": "Jayson Tatum", "team": "BOS", "text": "Jayson Tatum (ankle) is a GAME-TIME DECISION."},
        {"player": "Luka Doncic", "team": "DAL", "text": "Luka Doncic (calf) has been SCRATCHED from the starting lineup."}
    ]
    
    live_updates = []
    
    for tweet in simulated_tweets:
        status_match = "ACTIVE"
        for kw in urgent_keywords:
            if kw in tweet["text"].upper():
                status_match = kw
                break
        
        if status_match != "ACTIVE":
            live_updates.append({
                "player": tweet["player"],
                "team": tweet["team"],
                "status": status_match,
                "text": tweet["text"]
            })
            print(f"  🚨 ANOMALY DETECTED: {tweet['player']} -> {status_match}")

    save_to_db(live_updates)

def save_to_db(updates):
    if not DB_URL or len(updates) == 0: return
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        for update in updates:
            cur.execute("""
                INSERT INTO live_injuries (player_name, team, status, news_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (player_name) DO UPDATE 
                SET status = EXCLUDED.status, news_text = EXCLUDED.news_text, updated_at = CURRENT_TIMESTAMP
            """, (update["player"], update["team"], update["status"], update["text"]))
        conn.commit()
        conn.close()
        print(f"  💾 Vector Stored: {len(updates)} records injected into Quantum Pipeline.")
    except Exception as e:
        print(f"[-] Postgres Error: {e}")

if __name__ == "__main__":
    print("==================================================")
    print("👁️   V13.5 SENTINEL OSINT WORKER INITIALIZED   👁️")
    print("==================================================")
    setup_db()
    
    while True:
        parse_osint_feed()
        print("  [zZz] Perimeter secured. Sleeping for 300s (5m)...")
        time.sleep(300)
