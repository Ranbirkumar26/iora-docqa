"""OpenAI-compatible client error handling. No network."""
import json

import pytest
import requests

from app.llm.errors import RateLimitError
from app.llm.openai_compat import chat


def _response(status: int, payload: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode("utf-8")
    r.headers["content-type"] = "application/json"
    r.url = "https://example.test/chat/completions"
    return r


def test_413_rate_limit_error_falls_through(monkeypatch):
    """Groq reports TPM exhaustion as HTTP 413 + rate_limit_exceeded."""
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _response(
            413,
            {
                "error": {
                    "message": "Request too large for service tier TPM limit",
                    "type": "tokens",
                    "code": "rate_limit_exceeded",
                }
            },
        ),
    )

    with pytest.raises(RateLimitError):
        chat("https://example.test", "key", "model", "system", "user")


def test_success_reads_message_content(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _response(
            200, {"choices": [{"message": {"content": "hello"}}]}
        ),
    )

    assert chat("https://example.test", "key", "model", "system", "user") == "hello"
