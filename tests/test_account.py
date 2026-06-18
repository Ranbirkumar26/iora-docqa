"""Account / auth endpoint tests via FastAPI TestClient.

Supabase auth (gotrue) calls are mocked so these run offline. get_auth_context
is overridden to a fixed user, mirroring a logged-in caller.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.main as main
from app.api.main import app, get_auth_context
from app.core.orgs import AuthContext


def _ctx():
    return AuthContext(
        user_id="u1", organization_id="o1", organization_name="W", role="user"
    )


class _Admin:
    def __init__(self, email="u@example.com"):
        self.email = email
        self.updated = None
        self.signed_out = None

    def get_user_by_id(self, uid):
        return SimpleNamespace(user=SimpleNamespace(id=uid, email=self.email))

    def update_user_by_id(self, uid, attrs):
        self.updated = (uid, attrs)
        return SimpleNamespace(user=SimpleNamespace(id=uid))

    def sign_out(self, jwt, scope="global"):
        self.signed_out = (jwt, scope)


class _Auth:
    def __init__(
        self, admin, signin_ok=True, signup_session=False, signup_raises=False
    ):
        self.admin = admin
        self._signin_ok = signin_ok
        self._signup_session = signup_session
        self._signup_raises = signup_raises
        self.resent = None

    def sign_in_with_password(self, creds):
        if not self._signin_ok:
            raise Exception("invalid login credentials")
        return SimpleNamespace(
            session=SimpleNamespace(access_token="t"), user=SimpleNamespace(id="u1")
        )

    def sign_up(self, creds):
        if self._signup_raises:
            raise Exception("provider error")
        return SimpleNamespace(
            user=SimpleNamespace(id="newuser"),
            session=SimpleNamespace(access_token="t") if self._signup_session else None,
        )

    def resend(self, creds):
        self.resent = creds
        return SimpleNamespace()


class _Client:
    def __init__(self, auth):
        self.auth = auth


@pytest.fixture
def client():
    app.dependency_overrides[get_auth_context] = _ctx
    main.limiter.enabled = False  # don't let rate limits flake functional tests
    yield TestClient(app)
    app.dependency_overrides.clear()
    main.limiter.enabled = True


def _wire(
    monkeypatch,
    signin_ok=True,
    signup_session=False,
    signup_raises=False,
    admin_email="u@example.com",
):
    """Point service_client + fresh_anon_client at fakes sharing one admin.

    Returns (admin, anon_auth) so tests can assert side effects.
    """
    admin = _Admin(admin_email)
    anon_auth = _Auth(admin, signin_ok, signup_session, signup_raises)
    monkeypatch.setattr(main, "service_client", lambda: _Client(_Auth(admin)))
    monkeypatch.setattr(main, "fresh_anon_client", lambda: _Client(anon_auth))
    return admin, anon_auth


# ---------- change password (logged in) ----------
def test_change_password_success(client, monkeypatch):
    admin, _ = _wire(monkeypatch, signin_ok=True)
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "old123", "new_password": "newpass1"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert admin.updated == ("u1", {"password": "newpass1"})


def test_change_password_wrong_current_is_rejected(client, monkeypatch):
    admin, _ = _wire(monkeypatch, signin_ok=False)
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newpass1"},
    )
    assert r.status_code == 403
    assert admin.updated is None  # must NOT change on bad current pw


def test_change_password_too_short_is_rejected(client, monkeypatch):
    admin, _ = _wire(monkeypatch, signin_ok=True)
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "old123", "new_password": "abc"},
    )
    assert r.status_code == 400
    assert admin.updated is None


# ---------- signup with email confirmation ----------
def test_signup_requires_confirmation_when_no_session(client, monkeypatch):
    _wire(monkeypatch, signup_session=False)
    r = client.post("/api/auth/signup", json={"email": "New@X.com", "password": "secret12"})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_confirmation"] is True
    assert "confirm" in body["message"].lower()


def test_signup_auto_ok_when_session_returned(client, monkeypatch):
    _wire(monkeypatch, signup_session=True)
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret12"})
    assert r.status_code == 200
    assert r.json()["needs_confirmation"] is False


def test_signup_masks_provider_errors_no_enumeration(client, monkeypatch):
    _wire(monkeypatch, signup_raises=True)
    r = client.post("/api/auth/signup", json={"email": "dup@b.com", "password": "secret12"})
    # generic success, never reveals the failure / existence
    assert r.status_code == 200
    assert r.json()["needs_confirmation"] is True


def test_signup_rejects_weak_password(client, monkeypatch):
    _wire(monkeypatch)
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short"})
    assert r.status_code == 400  # policy rejects before reaching the provider


def test_signup_rejects_disallowed_domain(client, monkeypatch):
    import app.core.orgs as orgs

    monkeypatch.setattr(orgs, "APP_ALLOWED_EMAIL_DOMAINS", {"company.com"})
    _wire(monkeypatch)
    r = client.post(
        "/api/auth/signup", json={"email": "x@evil.com", "password": "secret12"}
    )
    assert r.status_code == 403


def test_signup_allows_listed_domain(client, monkeypatch):
    import app.core.orgs as orgs

    monkeypatch.setattr(orgs, "APP_ALLOWED_EMAIL_DOMAINS", {"company.com"})
    _wire(monkeypatch)
    r = client.post(
        "/api/auth/signup", json={"email": "x@company.com", "password": "secret12"}
    )
    assert r.status_code == 200


# ---------- resend confirmation ----------
def test_resend_calls_gotrue_and_is_generic(client, monkeypatch):
    _, anon_auth = _wire(monkeypatch)
    r = client.post("/api/auth/resend", json={"email": "Foo@Bar.com"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert anon_auth.resent["type"] == "signup"
    assert anon_auth.resent["email"] == "foo@bar.com"  # normalized lowercase


# ---------- delete account ----------
def test_delete_account_endpoint_calls_purge(client, monkeypatch):
    called = {}
    monkeypatch.setattr(
        main, "delete_account", lambda uid: called.setdefault("uid", uid)
    )
    r = client.delete("/api/account")
    assert r.status_code == 200
    assert r.json() == {"deleted": True}
    assert called["uid"] == "u1"  # scoped to the verified token's user


def test_delete_account_endpoint_handles_failure(client, monkeypatch):
    def boom(uid):
        raise Exception("db down")

    monkeypatch.setattr(main, "delete_account", boom)
    r = client.delete("/api/account")
    assert r.status_code == 500


class _PurgeQuery:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self._action = "select"
        self._filters = {}

    def select(self, *a, **k):
        self._action = "select"
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._action == "delete":
            self.store["deleted"].append((self.table, dict(self._filters)))
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=self.store["rows"].get(self.table, []))


class _PurgeStorage:
    def __init__(self, store):
        self.store = store

    def from_(self, bucket):
        self.store["bucket"] = bucket
        return self

    def remove(self, paths):
        self.store["removed"].extend(paths)


class _PurgeAuth:
    def __init__(self, store):
        self.admin = SimpleNamespace(
            delete_user=lambda uid: store.__setitem__("deleted_user", uid)
        )


class _PurgeSB:
    def __init__(self, store):
        self.store = store
        self.auth = _PurgeAuth(store)

    def table(self, name):
        return _PurgeQuery(self.store, name)

    @property
    def storage(self):
        return _PurgeStorage(self.store)


def test_delete_account_purges_storage_setnull_tables_then_user(monkeypatch):
    import app.core.account as account

    store = {
        "rows": {
            "files": [{"storage_path": "o/f1/a.txt"}],
            "generated_outputs": [{"storage_path": "o/generated/x/y.xlsx"}],
        },
        "deleted": [],
        "removed": [],
        "deleted_user": None,
        "bucket": None,
    }
    monkeypatch.setattr(account, "service_client", lambda: _PurgeSB(store))
    account.delete_account("u1")

    # raw + generated storage objects removed
    assert store["removed"] == ["o/f1/a.txt", "o/generated/x/y.xlsx"]
    # ON DELETE SET NULL tables deleted explicitly, scoped by user
    assert ("reports", {"user_id": "u1"}) in store["deleted"]
    assert ("processing_jobs", {"user_id": "u1"}) in store["deleted"]
    # auth user deleted last -> cascades the rest
    assert store["deleted_user"] == "u1"


# ---------- suspend / remove member (admin) ----------
def _admin_override():
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        "admin1", "o1", "W", role="admin"
    )
    main.limiter.enabled = False


def test_admin_suspend_member(monkeypatch):
    _admin_override()
    admin, _ = _wire(monkeypatch)
    try:
        r = TestClient(app).post("/api/members/target1/suspend")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert admin.updated[0] == "target1"
    assert "ban_duration" in admin.updated[1]


def test_admin_remove_member_calls_delete(monkeypatch):
    _admin_override()
    called = {}
    monkeypatch.setattr(main, "delete_account", lambda uid: called.setdefault("uid", uid))
    _wire(monkeypatch)
    try:
        r = TestClient(app).delete("/api/members/target1")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert called["uid"] == "target1"


def test_suspend_requires_admin(client, monkeypatch):
    _wire(monkeypatch)  # client fixture supplies a 'user' role ctx
    r = client.post("/api/members/target1/suspend")
    assert r.status_code == 403


def test_cannot_suspend_bootstrap_admin(monkeypatch):
    _admin_override()
    admin, _ = _wire(monkeypatch, admin_email="rk26.ftw@gmail.com")
    try:
        r = TestClient(app).post("/api/members/boss/suspend")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403
    assert admin.updated is None  # bootstrap admin never banned


def test_admin_action_writes_audit(monkeypatch):
    _admin_override()
    events = []
    monkeypatch.setattr(main, "write_audit", lambda *a, **k: events.append(a))
    _wire(monkeypatch)
    try:
        TestClient(app).post("/api/members/target1/suspend")
    finally:
        app.dependency_overrides.clear()
    assert events
    assert events[0][2] == "suspend"  # action
    assert events[0][3] == "target1"  # target user id


# ---------- logout all devices ----------
def test_logout_all_revokes_global_sessions(client, monkeypatch):
    admin, _ = _wire(monkeypatch)
    r = client.post(
        "/api/auth/logout-all", headers={"Authorization": "Bearer testtoken"}
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert admin.signed_out == ("testtoken", "global")


# ---------- MFA (wiring; real TOTP needs live verification) ----------
def test_mfa_enroll_returns_qr(client, monkeypatch):
    monkeypatch.setattr(
        main.mfa,
        "enroll",
        lambda at, rt: {"factor_id": "f1", "qr_code": "data:image/svg", "secret": "S", "uri": "otpauth://"},
    )
    r = client.post(
        "/api/auth/mfa/enroll",
        headers={"Authorization": "Bearer x"},
        json={"refresh_token": "rt"},
    )
    assert r.status_code == 200
    assert r.json()["factor_id"] == "f1"


def test_mfa_verify_returns_upgraded_session(client, monkeypatch):
    monkeypatch.setattr(
        main.mfa,
        "verify",
        lambda at, rt, fid, code: {"access_token": "aal2", "refresh_token": "r2", "expires_at": 1},
    )
    r = client.post(
        "/api/auth/mfa/verify",
        headers={"Authorization": "Bearer x"},
        json={"factor_id": "f1", "code": "123456", "refresh_token": "rt"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"] == "aal2"


def test_mfa_verify_rejects_bad_code(client, monkeypatch):
    monkeypatch.setattr(main.mfa, "verify", lambda *a: {"access_token": None})
    r = client.post(
        "/api/auth/mfa/verify",
        headers={"Authorization": "Bearer x"},
        json={"factor_id": "f1", "code": "000000", "refresh_token": "rt"},
    )
    assert r.status_code == 400


def test_login_signals_mfa_required(monkeypatch):
    app.dependency_overrides.clear()
    main.limiter.enabled = False
    _wire(monkeypatch, signin_ok=True)
    monkeypatch.setattr(main.mfa, "login_mfa_state", lambda client: {"factor_id": "f1"})
    r = TestClient(app).post(
        "/api/auth/login", json={"email": "a@b.com", "password": "secret12"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True
    assert body["factor_id"] == "f1"


def test_admin_mfa_reset(monkeypatch):
    _admin_override()
    monkeypatch.setattr(main.mfa, "admin_reset", lambda uid: 2)
    events = []
    monkeypatch.setattr(main, "write_audit", lambda *a, **k: events.append(a))
    try:
        r = TestClient(app).post("/api/members/target1/mfa-reset")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["removed"] == 2
    assert events and events[0][2] == "mfa_reset"


def test_mfa_reset_requires_admin(client):
    r = client.post("/api/members/target1/mfa-reset")
    assert r.status_code == 403


# ---------- rate limiting ----------
def test_login_rate_limited_after_threshold(monkeypatch):
    app.dependency_overrides.clear()
    _wire(monkeypatch, signin_ok=False)  # each attempt -> 401
    main.limiter.enabled = True
    try:
        codes = [
            TestClient(app)
            .post("/api/auth/login", json={"email": "x@y.com", "password": "z"})
            .status_code
            for _ in range(12)
        ]
    finally:
        main.limiter.enabled = True
    assert 401 in codes  # normal rejections still happen
    assert 429 in codes  # limiter trips past 10/min for the same client


# ---------- security headers ----------
def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert "referrer-policy" in r.headers
    assert r.headers.get("strict-transport-security", "").startswith("max-age=")
    assert ("content-security-policy" in r.headers) or (
        "content-security-policy-report-only" in r.headers
    )
