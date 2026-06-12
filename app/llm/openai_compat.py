"""Generic OpenAI-compatible chat client (Qwen via OpenRouter, Groq, etc.).

Uses `requests` so there's no extra SDK dependency. Raises RateLimitError on
429 so the provider chain can fall through to the next provider.
"""
import requests

from app.llm.errors import RateLimitError


def chat(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float | None = None,
    extra_headers: dict | None = None,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)

    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        body["temperature"] = temperature

    r = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=body,
        timeout=120,
    )
    if r.status_code == 429:
        raise RateLimitError(f"{model} rate limit hit")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""
