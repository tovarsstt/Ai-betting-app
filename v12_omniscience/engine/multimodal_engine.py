from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

class MultimodalEmbedder:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or provided.")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-embedding-2-preview"

    def embed_content(self, text=None, image_bytes=None, audio_bytes=None, image_mime="image/png", audio_mime="audio/mpeg"):
        """
        Generates multimodal embeddings for the provided content.
        """
        contents = []
        
        if text:
            contents.append(text)
            
        if image_bytes:
            contents.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image_mime,
                )
            )
            
        if audio_bytes:
            contents.append(
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=audio_mime,
                )
            )

        if not contents:
            raise ValueError("No content provided for embedding (text, image, or audio).")

        result = self.client.models.embed_content(
            model=self.model_name,
            contents=contents,
        )
        return result.embeddings

if __name__ == "__main__":
    # Internal Test
    try:
        embedder = MultimodalEmbedder()
        print("✅ MultimodalEmbedder initialized successfully.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
