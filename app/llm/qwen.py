"""Qwen via an OpenAI-compatible endpoint (OpenRouter by default)."""
from app.config import (
    OPENROUTER_REFERER,
    OPENROUTER_TITLE,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MODEL,
)
from app.llm.openai_compat import chat


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    headers = None
    if "openrouter.ai" in QWEN_BASE_URL:
        headers = {"HTTP-Referer": OPENROUTER_REFERER, "X-Title": OPENROUTER_TITLE}
    return chat(
        QWEN_BASE_URL,
        QWEN_API_KEY,
        QWEN_MODEL,
        system,
        user,
        max_tokens,
        temperature,
        extra_headers=headers,
    )
