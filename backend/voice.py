"""
Voice input: turn a recorded question into text.

Gemini understands audio, so we send it the recording and ask for the exact words.
The text is then sent to the agent like any typed question.
"""

from google import genai
from google.genai import types

from backend.config import GEMINI_MODEL

# The client reads the API key (GOOGLE_API_KEY) from the environment.
client = genai.Client()

PROMPT = "Transcribe this audio exactly as spoken. Return only the transcribed text, nothing else."


async def transcribe(audio_bytes, mime_type):
    audio = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    response = await client.aio.models.generate_content(model=GEMINI_MODEL, contents=[audio, PROMPT])
    return response.text.strip()
