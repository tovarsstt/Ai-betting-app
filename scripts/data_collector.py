import requests
import os
import pandas as pd
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BALLDONTLIE_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def fetch_season_games(seasons=[2023, 2024]):
    all_games = []
    print(f"🏀 [DATA COLLECTION] Fetching historical results for seasons: {seasons}...")
    
    for season in seasons:
        cursor = 0
        while True:
            url = f"https://api.balldontlie.io/v1/games?seasons[]={season}&per_page=100"
            if cursor: url += f"&cursor={cursor}"
            
            try:
                res = requests.get(url, headers=HEADERS, timeout=15).json()
                if "data" not in res:
                    print(f"⚠️ Rate limit or Error: {res}")
                    time.sleep(60) # Back off for a full minute
                    continue

                games = res.get('data', [])
                if not games: break
                
                for g in games:
                    if g['status'] == 'Final':
                        all_games.append({
                            "game_id": g['id'],
                            "date": g['date'],
                            "home_team": g['home_team']['full_name'],
                            "away_team": g['visitor_team']['full_name'],
                            "home_score": g['home_team_score'],
                            "away_score": g['visitor_team_score'],
                            "season": season
                        })
                
                meta = res.get('meta', {})
                cursor = meta.get('next_cursor')
                if not cursor: break
                print(f"   - Season {season}: Collected {len(all_games)} games (Cursor: {cursor})...")
                time.sleep(15) # Increased sleep for tight limits
            except Exception as e:
                print(f"❌ Error fetching: {e}")
                time.sleep(30)
                continue
    
    df = pd.DataFrame(all_games)
    df.to_csv("data/nba_historical.csv", index=False)
    print(f"✅ SUCCESS: Saved {len(df)} games to data/nba_historical.csv")

if __name__ == "__main__":
    if not os.path.exists("data"): os.makedirs("data")
    fetch_season_games()
