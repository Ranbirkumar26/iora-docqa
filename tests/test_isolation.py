"""Cross-user isolation tests.

The app enforces isolation in application code (service_client bypasses RLS), so
these exercise the real endpoints against a fake Supabase that *does* apply .eq /
.in_ filters. User A and user B share the same organization, so any path that
scopes by organization_id instead of user_id would leak B's rows to A and fail
here — exactly the A2/A3 footgun class.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.main as main
import app.core.outputs as outputs_mod
import app.core.report as report_mod
import app.core.search as search_mod
from app.api.main import app, get_auth_context
from app.core.orgs import AuthContext

A = "user-A"
B = "user-B"
ORG = "shared-org"  # both users in the same workspace

DB = {
    "files": [
        {"id": "fa", "user_id": A, "organization_id": ORG, "filename": "a.txt",
         "file_type": "txt", "char_count": 1, "upload_date": "2026-01-01", "indexed": True},
        {"id": "fb", "user_id": B, "organization_id": ORG, "filename": "b.txt",
         "file_type": "txt", "char_count": 1, "upload_date": "2026-01-02", "indexed": True},
    ],
    "generated_outputs": [
        {"id": "oa", "user_id": A, "organization_id": ORG, "kind": "report",
         "title": "A out", "content": "x", "format": "md", "sources": [],
         "metadata": {}, "file_id": None, "storage_path": None, "created_at": "2026-01-01"},
        {"id": "ob", "user_id": B, "organization_id": ORG, "kind": "report",
         "title": "B out", "content": "x", "format": "md", "sources": [],
         "metadata": {}, "file_id": None, "storage_path": None, "created_at": "2026-01-02"},
    ],
    "conversation_messages": [
        {"id": "ma", "user_id": A, "organization_id": ORG, "role": "user",
         "content": "A msg", "mode": None, "sources": [], "metadata": {}, "created_at": "2026-01-01"},
        {"id": "mb", "user_id": B, "organization_id": ORG, "role": "user",
         "content": "B msg", "mode": None, "sources": [], "metadata": {}, "created_at": "2026-01-02"},
    ],
    "reports": [
        {"id": "ra", "user_id": A, "organization_id": ORG, "title": "A rep",
         "report": "x", "mode": "direct", "sources": [], "created_at": "2026-01-01"},
        {"id": "rb", "user_id": B, "organization_id": ORG, "title": "B rep",
         "report": "x", "mode": "direct", "sources": [], "created_at": "2026-01-02"},
    ],
}


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self._in = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def in_(self, col, vals):
        self._in = (col, set(vals))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def execute(self):
        out = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]
        if self._in:
            col, vals = self._in
            out = [r for r in out if r.get(col) in vals]
        return SimpleNamespace(data=[dict(r) for r in out])


class FakeClient:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return FakeQuery(self.db.get(name, []))


@pytest.fixture
def client_as_A(monkeypatch):
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        A, ORG, "W", role="user"
    )
    fake = lambda: FakeClient(DB)
    monkeypatch.setattr(main, "service_client", fake)
    monkeypatch.setattr(outputs_mod, "service_client", fake)
    monkeypatch.setattr(report_mod, "service_client", fake)
    main.limiter.enabled = False
    yield TestClient(app)
    app.dependency_overrides.clear()
    main.limiter.enabled = True


def test_files_endpoint_scoped_to_caller(client_as_A):
    r = client_as_A.get("/api/files")
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()["files"]]
    assert ids == ["fa"]  # B's "fb" must not leak despite the shared org


def test_outputs_endpoint_scoped_to_caller(client_as_A):
    r = client_as_A.get("/api/outputs")
    assert r.status_code == 200
    ids = [o["id"] for o in r.json()["outputs"]]
    assert "oa" in ids and "ob" not in ids


def test_conversation_scoped_to_caller(client_as_A):
    r = client_as_A.get("/api/conversation")
    assert r.status_code == 200
    contents = [m["content"] for m in r.json()["messages"]]
    assert "A msg" in contents and "B msg" not in contents


def test_reports_scoped_to_caller(client_as_A):
    r = client_as_A.get("/api/reports")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["reports"]]
    assert ids == ["ra"]


def test_search_rpc_is_strictly_user_scoped(monkeypatch):
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        A, ORG, "W", role="user"
    )
    main.limiter.enabled = False
    captured = {}

    class _Rpc:
        def __init__(self, args):
            captured.update(args)

        def execute(self):
            return SimpleNamespace(data=[])

    class _SearchClient:
        def rpc(self, name, args):
            return _Rpc(args)

    monkeypatch.setattr(search_mod, "service_client", lambda: _SearchClient())
    try:
        r = TestClient(app).get("/api/search?q=hello")
    finally:
        app.dependency_overrides.clear()
        main.limiter.enabled = True
    assert r.status_code == 200
    # search_chunks must always pass the caller's user id and NEVER an org id
    assert captured["p_user_id"] == A
    assert captured["p_organization_id"] is None
