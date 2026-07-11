from types import SimpleNamespace

import app.core.orgs as orgs
from app.core.orgs import (
    AuthContext,
    email_domain_allowed,
    is_bootstrap_admin,
    list_org_members,
    normalize_role,
)


def test_email_domain_open_when_no_allowlist(monkeypatch):
    monkeypatch.setattr(orgs, "APP_ALLOWED_EMAIL_DOMAINS", set())
    assert email_domain_allowed("anyone@anywhere.com") is True


def test_email_domain_allowlist_enforced(monkeypatch):
    monkeypatch.setattr(orgs, "APP_ALLOWED_EMAIL_DOMAINS", {"acme.com"})
    assert email_domain_allowed("a@acme.com") is True
    assert email_domain_allowed("a@ACME.com") is True
    assert email_domain_allowed("a@evil.com") is False
    assert email_domain_allowed(None) is False
    assert email_domain_allowed("noatsign") is False


def test_role_aliases_normalize_legacy_values():
    assert normalize_role("owner") == "admin"
    assert normalize_role("member") == "user"
    assert normalize_role("author") == "author"
    assert normalize_role("unknown") == "user"


def test_only_configured_email_is_bootstrap_admin():
    assert is_bootstrap_admin("rk26.ftw@gmail.com")
    assert is_bootstrap_admin(" RK26.FTW@GMAIL.COM ")
    assert not is_bootstrap_admin("someone@example.com")


def test_user_role_reads_and_writes_own_scope():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="user")

    assert not ctx.can_read_all
    assert ctx.can_upload
    assert ctx.can_delete
    assert ctx.scope_id == "user-1"
    assert ctx.read_scope_uses_org is False
    assert ctx.write_scope_id == "user-1"
    assert ctx.write_scope_uses_org is False


def test_author_role_is_read_only_for_own_data():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="author")

    assert not ctx.can_read_all
    assert ctx.is_read_only
    assert not ctx.can_upload
    assert not ctx.can_delete
    assert ctx.scope_id == "user-1"
    assert ctx.read_scope_uses_org is False
    assert ctx.write_scope_id == "user-1"
    assert ctx.write_scope_uses_org is False


def test_admin_role_manages_roles_but_data_stays_user_scoped():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="admin")

    assert not ctx.can_read_all
    assert ctx.can_write_all
    assert ctx.can_upload
    assert ctx.can_delete
    assert ctx.scope_id == "user-1"
    assert ctx.write_scope_id == "user-1"
    assert ctx.write_scope_uses_org is False


def test_list_members_backfills_auth_users_missing_membership(monkeypatch):
    store = {
        "organization_members": [
            {
                "organization_id": "org-1",
                "user_id": "admin-1",
                "role": "admin",
                "created_at": "now",
            }
        ]
    }
    auth_users = {
        "admin-1": SimpleNamespace(
            id="admin-1", email="rk26.ftw@gmail.com", banned_until=None
        ),
        "missing-1": SimpleNamespace(
            id="missing-1",
            email="ranbir.kumar2023@vitstudent.ac.in",
            banned_until=None,
        ),
    }

    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = {}
            self.payload = None

        def select(self, *_args):
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def insert(self, payload):
            self.payload = payload if isinstance(payload, list) else [payload]
            return self

        def execute(self):
            if self.payload is not None:
                store[self.table].extend(self.payload)
                return SimpleNamespace(data=self.payload)
            rows = [
                row
                for row in store[self.table]
                if all(row.get(k) == v for k, v in self.filters.items())
            ]
            return SimpleNamespace(data=rows)

    class Admin:
        def list_users(self, page=None, per_page=None):
            return list(auth_users.values()) if page == 1 else []

        def get_user_by_id(self, uid):
            return SimpleNamespace(user=auth_users[uid])

    class Client:
        auth = SimpleNamespace(admin=Admin())

        def table(self, table):
            return Query(table)

    monkeypatch.setattr(orgs, "service_client", lambda: Client())

    members = list_org_members("org-1")

    emails = {member["email"] for member in members}
    assert "ranbir.kumar2023@vitstudent.ac.in" in emails
    missing = next(
        member
        for member in members
        if member["email"] == "ranbir.kumar2023@vitstudent.ac.in"
    )
    assert missing["role"] == "user"
