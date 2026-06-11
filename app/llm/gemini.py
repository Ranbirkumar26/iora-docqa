"""Gemini LLM wrapper. Free tier, no card. Matches claude.complete() signature."""
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = None


def _gemini():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    last = None
    for attempt in range(3):
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
            last = e
            if getattr(e, "code", None) == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))  # brief burst — short backoff
                continue
            if getattr(e, "code", None) == 429:
                # surfaced as HTTP 429 by the API layer
                raise RuntimeError(
                    "Gemini free-tier rate limit hit (20 requests/min). "
                    "Wait ~1 minute and try again."
                )
            raise
    raise last
