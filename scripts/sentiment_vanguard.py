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

def calculate_narrative_friction(tweet_text: str) -> float:
    """
    Analyzes social sentiment to find 'Micro-Injuries' or 'Locker Room Beef'.
    Returns a Narrative Penalty score from 0.0 to 1.5.
    """
    if not nlp:
        return 1.0 # fallback
        
    doc = nlp(tweet_text.lower())
    negative_triggers = ["limping", "soreness", "questionable", "beef", "frustrated", "limited"]
    
    friction_score = 1.0
    for token in doc:
        if token.text in negative_triggers:
            friction_score += 0.15 # Each trigger increases the quantitative risk
            
    return min(friction_score, 1.5)

@app.post("/analyze-sentiment", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest):
    score = calculate_narrative_friction(request.tweet_text)
    return SentimentResponse(friction_score=score)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
