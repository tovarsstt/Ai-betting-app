import requests
import sqlite3
import os
import json
from datetime import datetime

class LiveDataIngestion:
    """
    Ingests live sports data and odds into the V12 Memory Matrix.
    """
    
    def __init__(self, db_path='v12_omniscience/data/memory_matrix.sqlite'):
        self.db_path = db_path
        self.api_key = os.environ.get("BALLDONTLIE_API_KEY")

    def fetch_live_odds(self, sport='nba'):
        """Pulls latest odds from Action Network or Balldontlie."""
        # For V12 Alpha, we use the Action Network scoreboard logic
        url = f"https://api.actionnetwork.com/web/v1/scoreboard/{sport}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Odds Fetch Error: {e}")
        return None

    def ingest_games_to_matrix(self, sport='nba'):
        """Processes live games and stores them as 'pending' predictions for the model to analyze."""
        data = self.fetch_live_odds(sport)
        if not data or 'games' not in data:
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        count = 0
        for game in data['games']:
            teams = game.get('teams', [])
            if len(teams) < 2: continue
            
            matchup = f"{teams[0]['full_name']} @ {teams[1]['full_name']}"
            pred_id = f"v12_{game['id']}_{datetime.now().strftime('%Y%m%d')}"
            
            # Use 'INSERT OR IGNORE' to avoid duplicates
            cursor.execute('''
            INSERT OR IGNORE INTO predictions (prediction_id, matchup, sport, status)
            VALUES (?, ?, ?, ?)
            ''', (pred_id, matchup, sport.upper(), 'pending'))
            
            if cursor.rowcount > 0:
                count += 1
                
        conn.commit()
        conn.close()
        print(f"📥 Ingested {count} new {sport.upper()} games into Memory Matrix.")

if __name__ == "__main__":
    ingestor = LiveDataIngestion()
    ingestor.ingest_games_to_matrix('nba')
