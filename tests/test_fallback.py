"""LLM fallback chain order + skipping. No network (provider modules patched)."""
import app.config as cfg
import app.llm.gemini as gemini
import app.llm.groq as groq
import app.llm.qwen as qwen
from app.llm.errors import RateLimitError
from app.llm.provider import complete


def _all_keys(monkeypatch):
    monkeypatch.setattr(cfg, "LLM_CHAIN", "qwen,groq,gemini")
    monkeypatch.setattr(cfg, "QWEN_API_KEY", "k")
    monkeypatch.setattr(cfg, "GROQ_API_KEY", "k")
    monkeypatch.setattr(cfg, "GEMINI_API_KEY", "k")


def test_primary_first(monkeypatch):
    _all_keys(monkeypatch)
    monkeypatch.setattr(qwen, "complete", lambda *a, **k: "QWEN")
    monkeypatch.setattr(groq, "complete", lambda *a, **k: "GROQ")
    monkeypatch.setattr(gemini, "complete", lambda *a, **k: "GEMINI")
    assert complete("s", "q") == "QWEN"


def test_falls_through_on_rate_limit(monkeypatch):
    _all_keys(monkeypatch)

    def limited(*a, **k):
        raise RateLimitError("limited")

    monkeypatch.setattr(qwen, "complete", limited)  # qwen out
    monkeypatch.setattr(groq, "complete", lambda *a, **k: "GROQ")  # groq serves
    monkeypatch.setattr(gemini, "complete", lambda *a, **k: "GEMINI")
    assert complete("s", "q") == "GROQ"


def test_falls_to_last_when_two_limited(monkeypatch):
    _all_keys(monkeypatch)

    def limited(*a, **k):
        raise RateLimitError("limited")

    monkeypatch.setattr(qwen, "complete", limited)
    monkeypatch.setattr(groq, "complete", limited)
    monkeypatch.setattr(gemini, "complete", lambda *a, **k: "GEMINI")
    assert complete("s", "q") == "GEMINI"


def test_skips_providers_without_keys(monkeypatch):
    # only gemini has a key -> qwen/groq skipped, gemini used
    monkeypatch.setattr(cfg, "LLM_CHAIN", "qwen,groq,gemini")
    monkeypatch.setattr(cfg, "QWEN_API_KEY", "")
    monkeypatch.setattr(cfg, "GROQ_API_KEY", "")
    monkeypatch.setattr(cfg, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini, "complete", lambda *a, **k: "GEMINI")
    assert complete("s", "q") == "GEMINI"


def test_all_limited_raises(monkeypatch):
    _all_keys(monkeypatch)

    def limited(*a, **k):
        raise RateLimitError("limited")

    for m in (qwen, groq, gemini):
        monkeypatch.setattr(m, "complete", limited)
    try:
        complete("s", "q")
        assert False, "expected RateLimitError"
    except RateLimitError:
        pass
