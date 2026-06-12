"""Gemini LLM wrapper. Free tier, no card. Matches claude.complete() signature."""
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.llm.errors import RateLimitError

_client = None


def _gemini():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    # On 429 raise RateLimitError immediately (no backoff) so the provider layer
    # can fall back to Qwen fast — Gemini free tier is per-minute, retrying is moot.
    try:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            # disable "thinking" so output tokens go to the answer
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if temperature is not None:
            cfg.temperature = temperature
        resp = _gemini().models.generate_content(
            model=GEMINI_MODEL, contents=user, config=cfg
        )
        return resp.text or ""
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) == 429:
            raise RateLimitError("Gemini rate limit hit") from e
        raise
