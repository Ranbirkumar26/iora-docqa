"""IDOR tests: user A must not reach user B's resources by id, despite the
shared org. Exercises the real per-id endpoints against a filtering fake DB.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.main as main
import app.core.memory as memory_mod
import app.core.outputs as outputs_mod
import app.core.report as report_mod
from app.api.main import app, get_auth_context
from app.core.orgs import AuthContext

A = "user-A"
B = "user-B"
ORG = "shared-org"

DB = {
    "files": [
        {"id": "fa", "user_id": A, "organization_id": ORG, "storage_path": "p/a"},
        {"id": "fb", "user_id": B, "organization_id": ORG, "storage_path": "p/b"},
    ],
    "generated_outputs": [
        {"id": "oa", "user_id": A, "organization_id": ORG, "title": "A", "content": "x",
         "metadata": {}, "storage_path": None, "format": "text"},
        {"id": "ob", "user_id": B, "organization_id": ORG, "title": "B", "content": "x",
         "metadata": {}, "storage_path": None, "format": "text"},
    ],
    "reports": [
        {"id": "ra", "user_id": A, "organization_id": ORG, "title": "A", "report": "x",
         "mode": "direct", "sources": [], "structured_analysis": "", "qualitative_analysis": "",
         "created_at": "t"},
        {"id": "rb", "user_id": B, "organization_id": ORG, "title": "B", "report": "x",
         "mode": "direct", "sources": [], "structured_analysis": "", "qualitative_analysis": "",
         "created_at": "t"},
    ],
    "memories": [
        {"id": "ma", "user_id": A, "content": "A secret"},
        {"id": "mb", "user_id": B, "content": "B secret"},
    ],
}

DELETES = []


class FakeQuery:
    def __init__(self, rows, table):
        self.rows = rows
        self.table = table
        self.filters = []
        self._action = "select"

    def select(self, *a, **k):
        self._action = "select"
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, c, v):
        self.filters.append((c, v))
        return self

    def limit(self, n):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        match = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]
        if self._action == "delete":
            DELETES.append((self.table, dict(self.filters)))
            for r in list(match):
                self.rows.remove(r)
        return SimpleNamespace(data=[dict(r) for r in match])


class FakeClient:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return FakeQuery(self.db[name], name)


@pytest.fixture
def client_as_A(monkeypatch):
    DELETES.clear()
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        A, ORG, "W", role="user"
    )
    fake = lambda: FakeClient(DB)
    monkeypatch.setattr(main, "service_client", fake)
    monkeypatch.setattr(outputs_mod, "service_client", fake)
    monkeypatch.setattr(report_mod, "service_client", fake)
    monkeypatch.setattr(memory_mod, "service_client", fake)
    main.limiter.enabled = False
    yield TestClient(app)
    app.dependency_overrides.clear()
    main.limiter.enabled = True


def test_cannot_delete_another_users_file(client_as_A):
    assert client_as_A.delete("/api/files/fb").status_code == 404


def test_cannot_download_another_users_output(client_as_A):
    assert client_as_A.get("/api/outputs/ob/download").status_code == 404


def test_cannot_read_another_users_report(client_as_A):
    assert client_as_A.get("/api/reports/rb").status_code == 404


def test_cannot_delete_another_users_memory(client_as_A):
    r = client_as_A.delete("/api/memories/mb")  # B's memory
    assert r.status_code == 200  # endpoint response is generic...
    # ...but the delete is scoped to A, so B's memory is untouched
    assert "mb" in [m["id"] for m in DB["memories"]]
    assert ("memories", {"id": "mb", "user_id": A}) in DELETES
