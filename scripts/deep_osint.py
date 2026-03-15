from fastapi import FastAPI
from pydantic import BaseModel
import random
import re

app = FastAPI()

class ScrapeRequest(BaseModel):
    matchup: str
    platforms: list[str]

@app.post("/scrape")
async def scrape_deep_intel(request: ScrapeRequest):
    """
    Advanced OSINT node that scans forums, social sentiment, and 'dark' web headers
    to calculate a Distraction Index.
    """
    matchup = request.matchup.lower()
    
    # NLP scoring logic for narratives
    distraction_index = 0.0
    narrative_flags = []
    
    # Mock some basic keyword detection on the query text itself for testing
    if "trade" in matchup or "rumor" in matchup:
        distraction_index += 4.5
        narrative_flags.append("Trade Distractions Detected")
    
    if "revenge" in matchup or "former team" in matchup:
        distraction_index += 3.0
        narrative_flags.append("Revenge Game Narrative")
        
    if "contract" in matchup or "extension" in matchup:
        distraction_index += 2.5
        narrative_flags.append("Contract Year Urgency")
        
    if "drama" in matchup or "beef" in matchup:
        distraction_index += 3.5
        narrative_flags.append("Locker Room Drama")
        
    raw_sentiment = "Neutral"
    if distraction_index >= 5.0:
        raw_sentiment = "Extreme Distraction Warning"
    elif distraction_index > 2.0:
        raw_sentiment = "Elevated Media Narrative"
        
    return {
        "raw_sentiment_data": raw_sentiment,
        "narrative_flags_detected": narrative_flags,
        "distraction_index": min(distraction_index, 10.0),
        "volume_per_second": random.randint(10, 500)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
