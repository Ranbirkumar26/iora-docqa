import app.db.client as dbc


def test_read_client_routes_by_token(monkeypatch):
    monkeypatch.setattr(dbc, "user_client", lambda t: ("user", t))
    monkeypatch.setattr(dbc, "service_client", lambda: ("service",))
    assert dbc.read_client("tok") == ("user", "tok")  # token -> RLS-scoped client
    assert dbc.read_client(None) == ("service",)  # no token -> service client
    assert dbc.read_client("") == ("service",)  # empty token -> service client


def test_user_client_sets_user_bearer():
    from app.config import SUPABASE_URL

    if not SUPABASE_URL:
        import pytest

        pytest.skip("no SUPABASE_URL configured in test env")
    dbc.user_client.cache_clear()
    c = dbc.user_client("abc123")
    assert c.postgrest.headers.get("Authorization") == "Bearer abc123"
