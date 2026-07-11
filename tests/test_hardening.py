"""Hardening tests: sanitized 500 handler, formula-injection guard, and input
validation (EmailStr + length caps)."""
from fastapi.testclient import TestClient

import app.api.main as main
from app.api.main import app, get_auth_context
from app.core.orgs import AuthContext
from app.core.outputs import _excel_safe


def test_excel_safe_quotes_formula_leads():
    assert _excel_safe("=1+1") == "'=1+1"
    assert _excel_safe("+x") == "'+x"
    assert _excel_safe("-x") == "'-x"
    assert _excel_safe("@x") == "'@x"
    assert _excel_safe("safe") == "safe"
    assert _excel_safe(5) == 5  # non-strings pass through


def _boom():
    raise ValueError("boom")


def test_unhandled_exception_returns_sanitized_500():
    app.dependency_overrides[get_auth_context] = _boom
    main.limiter.enabled = False
    try:
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/status")
    finally:
        app.dependency_overrides.clear()
        main.limiter.enabled = True
    assert r.status_code == 500
    # sanitized: no traceback / internals leaked
    assert r.json() == {"detail": "Something went wrong. Please try again."}


def test_signup_rejects_malformed_email():
    main.limiter.enabled = False
    try:
        r = TestClient(app).post(
            "/api/auth/signup", json={"email": "notanemail", "password": "secret12"}
        )
    finally:
        main.limiter.enabled = True
    assert r.status_code == 422  # EmailStr rejects before any provider call


def test_ask_rejects_overlong_question():
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        "u", "o", "W", role="user"
    )
    main.limiter.enabled = False
    try:
        r = TestClient(app).post("/api/ask", json={"question": "x" * 9000})
    finally:
        app.dependency_overrides.clear()
        main.limiter.enabled = True
    assert r.status_code == 422  # Field(max_length=8000)


def test_spa_shell_is_served_without_stale_cache():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache, must-revalidate"
    assert r.headers.get("pragma") == "no-cache"
