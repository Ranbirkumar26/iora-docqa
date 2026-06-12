"""Groq via its OpenAI-compatible endpoint."""
from app.config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL
from app.llm.openai_compat import chat


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    return chat(GROQ_BASE_URL, GROQ_API_KEY, GROQ_MODEL, system, user, max_tokens, temperature)
