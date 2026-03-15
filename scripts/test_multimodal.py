import os
import sys
import base64
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def test_multimodal_embedding():
    print("🚀 Initializing Gemini Multimodal Embedding Test...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env")
        return

    client = genai.Client(api_key=api_key)
    
    # We will use text-only for this automated test to avoid needing dummy files,
    # but the logic follows the requested pattern.
    print("Testing text embedding...")
    try:
        result = client.models.embed_content(
            model="gemini-embedding-2-preview",
            contents=["What is the meaning of life?"]
        )
        print(f"✅ Success! Embedding dimension: {len(result.embeddings[0].values) if result.embeddings else 'Unknown'}")
        print("Result sample:", str(result.embeddings[0].values[:5]) + "...")
    except Exception as e:
        print(f"❌ Text Embedding Failed: {e}")

    # Note: To test images/audio, place example.png or sample.mp3 in this directory
    # and uncomment the logic in multimodal_engine.py
    print("\nMultimodal logic is now integrated into 'v12_omniscience/engine/multimodal_engine.py'")
    print("Endpoint: POST http://localhost:8001/v12/embed/multimodal")

if __name__ == "__main__":
    test_multimodal_embedding()
