"""LLM provider switch + automatic fallback.

Primary picked via LLM_PROVIDER (gemini | claude). When the primary is rate-
limited, fall back to LLM_FALLBACK (qwen) if its key is set. If the fallback is
also limited (or absent), the RateLimitError propagates and the API returns 429.
"""
import app.config as cfg
from app.llm.errors import RateLimitError


def _primary(system: str, user: str, max_tokens: int, temperature):
    if cfg.LLM_PROVIDER == "claude":
        from app.llm.claude import complete as c
        return c(system, user, max_tokens, temperature)
    from app.llm.gemini import complete as c
    return c(system, user, max_tokens, temperature)


def complete(system: str, user: str, max_tokens: int = 2048, temperature: float | None = None) -> str:
    try:
        return _primary(system, user, max_tokens, temperature)
    except RateLimitError:
        # primary is rate-limited -> try the configured fallback
        if cfg.LLM_FALLBACK == "qwen" and cfg.QWEN_API_KEY:
            from app.llm.qwen import complete as qc
            return qc(system, user, max_tokens, temperature)
        raise


__all__ = ["complete"]
