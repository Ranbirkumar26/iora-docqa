"""Shared LLM errors."""


class RateLimitError(RuntimeError):
    """Raised when an LLM provider is rate-limited.

    Subclasses RuntimeError so the API's RuntimeError handler still maps an
    exhausted chain (all providers limited) to HTTP 429.
    """
