import app.db.client as dbc


def test_read_client_routes_by_token(monkeypatch):
    monkeypatch.setattr(dbc, "user_client", lambda t: ("user", t))
    monkeypatch.setattr(dbc, "service_client", lambda: ("service",))
    # flag ON: a token routes to the RLS-scoped user client
    monkeypatch.setattr(dbc, "RLS_SCOPED_READS", True)
    assert dbc.read_client("tok") == ("user", "tok")
    assert dbc.read_client(None) == ("service",)
    assert dbc.read_client("") == ("service",)
    # flag OFF (default): always the service client, even with a token
    monkeypatch.setattr(dbc, "RLS_SCOPED_READS", False)
    assert dbc.read_client("tok") == ("service",)


def test_user_client_sets_user_bearer():
    from app.config import SUPABASE_URL

    if not SUPABASE_URL:
        import pytest

        pytest.skip("no SUPABASE_URL configured in test env")
    dbc.user_client.cache_clear()
    c = dbc.user_client("abc123")
    assert c.postgrest.headers.get("Authorization") == "Bearer abc123"
