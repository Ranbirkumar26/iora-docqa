"""Gemini LLM wrapper. Free tier, no card. Matches claude.complete() signature."""
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = None


def _gemini():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def complete(system: str, user: str, max_tokens: int = 2048) -> str:
    resp = _gemini().models.generate_content(
        model=GEMINI_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
    )
    return resp.text or ""
