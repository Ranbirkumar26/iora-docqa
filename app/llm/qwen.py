"""Qwen LLM wrapper via an OpenAI-compatible endpoint (DashScope by default).

Used as the automatic fallback when Gemini is rate-limited. Uses `requests`
directly so no extra SDK dependency.
"""
import requests

from app.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.llm.errors import RateLimitError


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    body: dict = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        body["temperature"] = temperature

    r = requests.post(
        f"{QWEN_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {QWEN_API_KEY}"},
        json=body,
        timeout=120,
    )
    if r.status_code == 429:
        raise RateLimitError("Qwen rate limit hit")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""
