"""Claude wrapper. Single entry point for all LLM calls."""
import anthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = None


def _claude():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def complete(system: str, user: str, max_tokens: int = 2048) -> str:
    """One-shot completion. Returns concatenated text blocks."""
    msg = _claude().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
