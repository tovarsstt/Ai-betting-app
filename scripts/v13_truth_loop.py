import psycopg2
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def run_truth_loop():
    print("🔬 [V13.5] INITIATING TRUTH LOOP & GRADIENT DESCENT...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url or "localhost" in db_url:
        print("⚠️  DATABASE_URL is placeholder/local. Skipping DB update, running in MOCK_MODE.")
        mock_mode = True
    else:
        try:
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            mock_mode = False
        except:
            print("❌ DB Connection failed. Falling back to MOCK_MODE.")
            mock_mode = True

    # 1. GRADE PENDING PICKS
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        res = requests.get(f"https://api.balldontlie.io/v1/games?dates[]={yesterday}", 
                           headers={"Authorization": os.getenv("BALLDONTLIE_API_KEY")},
                           timeout=10).json()
        actual_games = res.get('data', [])
    except:
        print("⚠️ API Request failed. Using simulated results for testing.")
        actual_games = []

    if not mock_mode:
        cur.execute("SELECT id, matchup, predicted_winner, kelly_stake FROM predictions WHERE status = 'pending'")
        pending = cur.fetchall()
    else:
        pending = [(1, "Lakers vs Warriors", "Lakers", 25.0)] # Mock Case

    for pid, matchup, pred, amount_bet in pending:
        # Real logic: Find the game in the API results
        found = False
        for g in actual_games:
            home = g['home_team']['full_name']
            away = g['visitor_team']['full_name']
            if home.lower() in matchup.lower() or away.lower() in matchup.lower():
                winner = home if g['home_team_score'] > g['visitor_team_score'] else away
                status = 'won' if pred == winner else 'lost'
                found = True
                
                stake_odds = 1.91 # Default if not logged
                if status == 'won':
                    profit = amount_bet * (stake_odds - 1)
                else:
                    profit = -amount_bet
                
                if not mock_mode:
                    cur.execute("UPDATE predictions SET status = %s WHERE id = %s", (status, pid))
                print(f"✅ {matchup}: {status.upper()} | PNL: ${profit:.2f}")

        if not found and not mock_mode:
            print(f"⌛ {matchup}: Picking still in progress or game not found.")

    # 2. SELF-EVOLVE (The Evolutionary Pulse)
    # If loss rate is high, we tell the engine to tighten its volatility
    loss_rate = 0.0
    if not mock_mode:
        cur.execute("SELECT status FROM predictions WHERE status IN ('won', 'lost') ORDER BY created_at DESC LIMIT 20")
        recent = [r[0] for r in cur.fetchall()]
        if recent:
            loss_rate = recent.count('lost') / len(recent)
    else:
        loss_rate = 0.7 # Simulate decay for testing

    if loss_rate > 0.5:
        print(f"🧬 [EVOLUTION SIGNAL] Loss Rate: {loss_rate:.2f}. Triggering Volatility Contraction...")
        try:
            requests.post("http://127.0.0.1:8001/evolve", json={"volatility_weight": 0.75}, timeout=5)
        except:
            print("⚠️ Engine node (8001) unreachable. Postponing Evolution.")
    else:
        print(f"🛡️ [STABILITY] Loss Rate: {loss_rate:.2f}. Volatility remains at 1.0.")

    if not mock_mode:
        conn.commit()
        conn.close()

if __name__ == "__main__":
    run_truth_loop()
