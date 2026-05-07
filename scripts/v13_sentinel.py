import requests
import os
import time

INJURY_KEYWORDS = ['out', 'ruled out', 'doubtful', 'questionable', 'injured',
                   'surgery', 'fracture', 'will not play', "won't play", 'missed practice',
                   'day-to-day', 'placed on', 'dealing with']

SPORTS = [
    ('basketball/nba',  'NBA'),
    ('baseball/mlb',    'MLB'),
    ('hockey/nhl',      'NHL'),
    ('football/nfl',    'NFL'),
]

seen_headlines: set = set()

def scan_injuries():
    alerts = []
    for path, label in SPORTS:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/news?limit=20"
            r = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code != 200:
                continue
            articles = r.json().get("articles", [])
            for article in articles:
                headline = article.get("headline", "").strip()
                if not headline or headline in seen_headlines:
                    continue
                if any(kw in headline.lower() for kw in INJURY_KEYWORDS):
                    seen_headlines.add(headline)
                    alerts.append(f"[{label}] {headline}")
                    print(f"🚨 [SENTINEL] {label}: {headline}")
        except Exception as e:
            print(f"Sentinel scan error ({label}): {e}")
    return alerts

def poll_breaking_news():
    print("📡 SENTINEL ACTIVE: Scanning ESPN for real injury/news alpha...")
    while True:
        try:
            scan_injuries()
        except Exception as e:
            print(f"Sentinel Error: {e}")
        time.sleep(300)  # scan every 5 minutes

if __name__ == "__main__":
    poll_breaking_news()
