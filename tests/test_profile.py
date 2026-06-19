from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.main as main
import app.core.profile as profile_mod
from app.api.main import app, get_auth_context
from app.core.orgs import AuthContext

A = "user-A"


class _Q:
    def __init__(self, store):
        self.store = store
        self.filters = []
        self._action = "select"
        self._payload = None

    def select(self, *a, **k):
        self._action = "select"
        return self

    def upsert(self, payload):
        self._action = "upsert"
        self._payload = payload
        return self

    def eq(self, c, v):
        self.filters.append((c, v))
        return self

    def limit(self, n):
        return self

    def execute(self):
        if self._action == "upsert":
            self.store["rows"] = [dict(self._payload)]
            return SimpleNamespace(data=[dict(self._payload)])
        rows = [
            r for r in self.store["rows"] if all(r.get(c) == v for c, v in self.filters)
        ]
        return SimpleNamespace(data=[dict(r) for r in rows])


class _Client:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Q(self.store)


@pytest.fixture
def client(monkeypatch):
    store = {"rows": []}
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        A, "o", "W", role="user"
    )
    monkeypatch.setattr(profile_mod, "service_client", lambda: _Client(store))
    main.limiter.enabled = False
    yield TestClient(app), store
    app.dependency_overrides.clear()
    main.limiter.enabled = True


def test_get_profile_empty(client):
    c, _ = client
    r = c.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["profile"] == {}


def test_upsert_then_get_scoped_to_caller(client):
    c, store = client
    r = c.put(
        "/api/profile",
        json={"full_name": "Ann", "gender": "Female", "age": 30, "city": "NYC"},
    )
    assert r.status_code == 200
    prof = r.json()["profile"]
    assert prof["full_name"] == "Ann"
    assert prof["user_id"] == A  # stored under the caller's id
    assert store["rows"][0]["user_id"] == A


def test_age_above_range_rejected(client):
    c, _ = client
    assert c.put("/api/profile", json={"age": 200}).status_code == 422


def test_age_below_range_rejected(client):
    c, _ = client
    assert c.put("/api/profile", json={"age": 5}).status_code == 422
