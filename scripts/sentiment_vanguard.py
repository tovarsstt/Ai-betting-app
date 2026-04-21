import spacy
from fastapi import FastAPI
from pydantic import BaseModel
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load NLP Model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logging.warning("en_core_web_sm not found. Please run 'python3 -m spacy download en_core_web_sm'.")
    nlp = None

app = FastAPI()

class SentimentRequest(BaseModel):
    tweet_text: str

class SentimentResponse(BaseModel):
    friction_score: float
    detected_alerts: list[str] = []

def calculate_narrative_friction(tweet_text: str):
    """
    Analyzes social sentiment to find 'Micro-Injuries' or 'Locker Room Beef'.
    Returns (friction_score, alerts).
    """
    if not nlp:
        return 1.0, [] # fallback
        
    doc = nlp(tweet_text.lower())
    negative_triggers = ["limping", "soreness", "questionable", "beef", "frustrated", "limited", "out", "inactive", "injury", "dtd", "gtd", "scratched"]
    
    friction_score = 1.0
    alerts = []
    
    # Simple extraction: if a player name (token or phrase) is near an injury trigger
    # For now, we return any sentence containing a trigger as an 'alert'
    for sent in doc.sents:
        if any(trigger in sent.text for trigger in negative_triggers):
            alerts.append(sent.text.strip())
            friction_score += 0.15
            
    return min(friction_score, 1.5), list(set(alerts))

@app.post("/analyze-sentiment", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest):
    score, alerts = calculate_narrative_friction(request.tweet_text)
    return SentimentResponse(friction_score=score, detected_alerts=alerts)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
