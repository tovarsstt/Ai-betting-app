import psycopg2
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

def poll_breaking_news():
    print("📡 SENTINEL ACTIVE: Scanning for OSINT Alpha...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url: return
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    while True:
        try:
            # 1. SCRAPE TARGET (Example: Scrape an injury news aggregator or RSS)
            # In production, replace this with a real X/Twitter or News API call
            # Mock Alert for demonstration:
            news_items = [
                {"name": "Anthony Davis", "status": "OUT", "note": "Foot soreness detected in warmups"}
            ]

            for item in news_items:
                # 2. CHECK IF WE ALREADY RECORDED THIS TO PREVENT DUPLICATES
                cur.execute("SELECT id FROM osint_alerts WHERE player_name = %s AND status = %s", (item['name'], item['status']))
                if not cur.fetchone():
                    # 3. INSERT FRESH INTELLIGENCE
                    cur.execute("""
                        INSERT INTO osint_alerts (player_name, status, raw_source)
                        VALUES (%s, %s, %s)
                    """, (item['name'], item['status'], item['note']))
                    print(f"🚨 [SENTINEL ALERT] {item['name']} is {item['status']}: {item['note']}")
            
            conn.commit()
            time.sleep(60) # Scan every 60 seconds

        except Exception as e:
            print(f"Sentinel Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    poll_breaking_news()
