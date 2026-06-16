from app.core.orgs import AuthContext, normalize_role


def test_role_aliases_normalize_legacy_values():
    assert normalize_role("owner") == "admin"
    assert normalize_role("member") == "user"
    assert normalize_role("author") == "author"
    assert normalize_role("unknown") == "user"


def test_user_role_reads_and_writes_own_scope():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="user")

    assert not ctx.can_read_all
    assert ctx.can_upload
    assert ctx.can_delete
    assert ctx.scope_id == "user-1"
    assert ctx.read_scope_uses_org is False
    assert ctx.write_scope_id == "user-1"
    assert ctx.write_scope_uses_org is False


def test_author_role_is_org_wide_read_only():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="author")

    assert ctx.can_read_all
    assert ctx.is_read_only
    assert not ctx.can_upload
    assert not ctx.can_delete
    assert ctx.scope_id == "org-1"
    assert ctx.read_scope_uses_org is True
    assert ctx.write_scope_id == "user-1"
    assert ctx.write_scope_uses_org is False


def test_admin_role_is_org_wide_read_write():
    ctx = AuthContext("user-1", "org-1", "Workspace", role="admin")

    assert ctx.can_read_all
    assert ctx.can_write_all
    assert ctx.can_upload
    assert ctx.can_delete
    assert ctx.scope_id == "org-1"
    assert ctx.write_scope_id == "org-1"
    assert ctx.write_scope_uses_org is True
