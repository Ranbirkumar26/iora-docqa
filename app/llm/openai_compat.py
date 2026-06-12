"""Generic OpenAI-compatible chat client (Qwen via OpenRouter, Groq, etc.).

Uses `requests` so there's no extra SDK dependency. Raises RateLimitError on
429 so the provider chain can fall through to the next provider.
"""
import requests

from app.llm.errors import RateLimitError


def _api_error(r: requests.Response) -> tuple[str, str, str]:
    """Return provider error message/code/type from an OpenAI-style response."""
    try:
        payload = r.json()
    except ValueError:
        return (r.text or r.reason or "request failed", "", "")

    err = payload.get("error", payload) if isinstance(payload, dict) else payload
    if not isinstance(err, dict):
        return (str(err), "", "")
    return (
        str(err.get("message") or r.reason or "request failed"),
        str(err.get("code") or ""),
        str(err.get("type") or ""),
    )


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
    if not r.ok:
        message, code, typ = _api_error(r)
        # Groq can return HTTP 413 for TPM/request-size throttles while the
        # JSON body reports rate_limit_exceeded. Treat those like 429 so the
        # provider chain can fall through to Gemini/Qwen instead of surfacing a
        # generic FastAPI 500.
        if (
            r.status_code in (429, 413)
            or code == "rate_limit_exceeded"
            or typ in {"rate_limit_error", "tokens"}
        ):
            raise RateLimitError(f"{model} rate/request limit hit: {message}")
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""
