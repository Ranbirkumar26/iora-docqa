"""LLM fallback chain: Gemini rate-limit -> Qwen. No network (wrappers patched)."""
import app.config as cfg
import app.llm.gemini as gemini
import app.llm.qwen as qwen
from app.llm.errors import RateLimitError
from app.llm.provider import complete


def test_falls_back_to_qwen_on_rate_limit(monkeypatch):
    monkeypatch.setattr(cfg, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(cfg, "LLM_FALLBACK", "qwen")
    monkeypatch.setattr(cfg, "QWEN_API_KEY", "test-key")

    def boom(*a, **k):
        raise RateLimitError("gemini limited")

    monkeypatch.setattr(gemini, "complete", boom)
    monkeypatch.setattr(qwen, "complete", lambda *a, **k: "QWEN_ANSWER")

    assert complete("sys", "q") == "QWEN_ANSWER"


def test_uses_primary_when_not_limited(monkeypatch):
    monkeypatch.setattr(cfg, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(gemini, "complete", lambda *a, **k: "GEMINI_ANSWER")
    assert complete("sys", "q") == "GEMINI_ANSWER"


def test_rate_limit_propagates_without_fallback_key(monkeypatch):
    monkeypatch.setattr(cfg, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(cfg, "QWEN_API_KEY", "")  # no fallback configured

    def boom(*a, **k):
        raise RateLimitError("gemini limited")

    monkeypatch.setattr(gemini, "complete", boom)
    try:
        complete("sys", "q")
        assert False, "expected RateLimitError"
    except RateLimitError:
        pass
