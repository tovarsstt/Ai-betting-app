import asyncio
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import uvicorn

app = FastAPI(title="God-Engine OSINT Sentiment Node")

class SentimentRequest(BaseModel):
    matchup: str
    platforms: List[str] = ["X", "Reddit"]

class SentimentResponse(BaseModel):
    matchup: str
    raw_sentiment_data: str
    volume_per_second: float
    panic_triggers_found: List[str]

# Mocking the scraper logic - in production, this would use tweepy and praw
MOCK_SENTIMENTS = [
    "I'm cashing out my Lakers bet, LeBron out is a disaster. Warriors are going to steamroll.",
    "Curry is on absolute fire, 12 threes in last practice? Smashing the over.",
    "Lakers are poverty without King James. Sell sell sell on Polymarket.",
    "Warriors -7.5 is a gift from the gods. Vegas doesn't know what's coming.",
    "Why are people panicking? AD is still playing. Buy the Lakers dip!",
    "Referees for tonight's game announced - they hate the Warriors. Watch out.",
    "Locker room rumors: Lakers players are 'relieved' LeBron is resting? Cognitive dissonance?",
]

@app.post("/scrape", response_model=SentimentResponse)
async def scrape_sentiment(request: SentimentRequest):
    # Simulate high-speed scraping
    await asyncio.sleep(0.5) 
    
    # Filter or select relevant mock data based on matchup keywords
    relevant_data = [s for s in MOCK_SENTIMENTS if any(word.lower() in s.lower() for word in request.matchup.split())]
    if not relevant_data:
        relevant_data = random.sample(MOCK_SENTIMENTS, 3)
    
    raw_text = " | ".join(relevant_data)
    
    return {
        "matchup": request.matchup,
        "raw_sentiment_data": raw_text,
        "volume_per_second": round(random.uniform(50, 500), 2),
        "panic_triggers_found": ["LBJ_OUT", "CURRY_HOT", "RETAIL_PANIC", "OFFSHORE_WHALE_MOVE"]
    }

@app.get("/health")
async def health():
    return {"status": "OSINT Node Online", "node": "Python-Sentiment-Scraper"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
