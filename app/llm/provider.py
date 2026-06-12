"""LLM provider chain with automatic fallback.

LLM_CHAIN is an ordered list of provider names. The first is the everyday
primary; each next is tried when the previous is rate-limited (or unreachable).
Providers without a configured key are skipped, so the chain works incrementally
as keys are added. If every available provider is rate-limited, the
RateLimitError propagates and the API returns HTTP 429.
"""
import requests

import app.config as cfg
from app.llm.errors import RateLimitError


def _resolve(name: str):
    """Return (complete_fn, has_key) for a provider name, or (None, False)."""
    if name == "gemini":
        from app.llm import gemini
        return gemini.complete, bool(cfg.GEMINI_API_KEY)
    if name == "groq":
        from app.llm import groq
        return groq.complete, bool(cfg.GROQ_API_KEY)
    if name == "qwen":
        from app.llm import qwen
        return qwen.complete, bool(cfg.QWEN_API_KEY)
    if name == "claude":
        from app.llm import claude
        return claude.complete, bool(cfg.ANTHROPIC_API_KEY)
    return None, False


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    chain = [c.strip() for c in cfg.LLM_CHAIN.split(",") if c.strip()]
    last_err = None
    for name in chain:
        fn, has_key = _resolve(name)
        if fn is None or not has_key:
            continue
        try:
            return fn(system, user, max_tokens, temperature)
        except RateLimitError as e:
            last_err = e  # provider is rate-limited -> try the next one
            continue
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e  # transient -> try the next one
            continue
    if last_err is not None:
        raise last_err
    raise RuntimeError(
        f"No LLM provider available. Set a key for one of: {cfg.LLM_CHAIN}"
    )


__all__ = ["complete"]
