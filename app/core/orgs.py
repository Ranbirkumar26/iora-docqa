"""Organisation helpers.

All users join one default organisation for role management. Document data is
always scoped to the signed-in user, regardless of role.
"""
from dataclasses import dataclass

from postgrest.exceptions import APIError

from app.config import (
    APP_ADMIN_EMAILS,
    APP_ALLOWED_EMAIL_DOMAINS,
    DEFAULT_ORGANIZATION_NAME,
)
from app.db.client import service_client, transient_retry

ROLE_ALIASES = {
    "owner": "admin",
    "admin": "admin",
    "member": "user",
    "user": "user",
    "author": "author",
}
VALID_ROLES = {"user", "author", "admin"}


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    organization_id: str
    organization_name: str
    role: str = "user"
    org_enabled: bool = True
    is_super_admin: bool = False
    access_token: str | None = None  # caller's JWT, for RLS-scoped reads

    @property
    def scope_id(self) -> str:
        return self.read_scope_id

    @property
    def can_read_all(self) -> bool:
        return False

    @property
    def can_write_all(self) -> bool:
        return self.role == "admin"

    @property
    def is_read_only(self) -> bool:
        return self.role == "author"

    @property
    def can_upload(self) -> bool:
        return self.role in {"user", "admin"}

    @property
    def can_delete(self) -> bool:
        return self.role in {"user", "admin"}

    @property
    def read_scope_uses_org(self) -> bool:
        return False

    @property
    def read_scope_id(self) -> str:
        return self.user_id

    @property
    def write_scope_uses_org(self) -> bool:
        return False

    @property
    def write_scope_id(self) -> str:
        return self.user_id


def normalize_role(role: str | None) -> str:
    return ROLE_ALIASES.get((role or "user").strip().lower(), "user")


def is_bootstrap_admin(email: str | None) -> bool:
    return bool(email and email.strip().lower() in APP_ADMIN_EMAILS)


def email_domain_allowed(email: str | None) -> bool:
    """True when signups are open (no allowlist) or the email's domain is allowed."""
    if not APP_ALLOWED_EMAIL_DOMAINS:
        return True
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[-1].strip().lower() in APP_ALLOWED_EMAIL_DOMAINS


def _name_from_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "Personal workspace"
    return f"{email.split('@', 1)[0]}'s workspace"


def _legacy_context(user_id: str, email: str | None = None) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        organization_id=user_id,
        organization_name=_name_from_email(email),
        role="user",
        org_enabled=False,
        is_super_admin=is_bootstrap_admin(email),
    )


def _org_schema_missing(exc: APIError) -> bool:
    data = getattr(exc, "args", [{}])[0]
    code = getattr(exc, "code", None)
    message = str(getattr(exc, "message", "") or "")
    if isinstance(data, dict):
        code = code or data.get("code")
        message = message or str(data.get("message") or "")
    return code == "PGRST205" and (
        "organization_members" in message or "organizations" in message
    )


def _get_or_create_default_org(sb, user_id: str | None = None) -> dict:
    rows = (
        sb.table("organizations")
        .select("id, name")
        .eq("name", DEFAULT_ORGANIZATION_NAME)
        .limit(1)
        .execute()
        .data
        or []
    )
    if rows:
        return rows[0]
    payload = {"name": DEFAULT_ORGANIZATION_NAME}
    if user_id:
        payload["created_by"] = user_id
    return sb.table("organizations").insert(payload).execute().data[0]


def _user_email(user_id: str) -> str | None:
    try:
        res = service_client().auth.admin.get_user_by_id(user_id)
        user = getattr(res, "user", None)
        return getattr(user, "email", None)
    except Exception:
        return None


def _auth_user_id(user) -> str | None:
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _auth_user_email(user) -> str | None:
    if isinstance(user, dict):
        return user.get("email")
    return getattr(user, "email", None)


def _list_auth_users(admin) -> list:
    users = []
    page = 1
    per_page = 1000
    while page <= 20:
        batch = admin.list_users(page=page, per_page=per_page) or []
        users.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return users


def _sync_org_members_from_auth(organization_id: str) -> None:
    """Ensure every Supabase Auth user appears in the shared workspace.

    Older accounts, unconfirmed accounts, or users created outside this app may
    exist in auth.users before they ever hit get_user_org(). Admin role
    management should still show them instead of making the account look
    invisible while signup correctly says it already exists.
    """
    sb = service_client()
    existing = (
        sb.table("organization_members")
        .select("user_id")
        .eq("organization_id", organization_id)
        .execute()
        .data
        or []
    )
    existing_ids = {row["user_id"] for row in existing if row.get("user_id")}
    inserts = []
    for user in _list_auth_users(sb.auth.admin):
        user_id = _auth_user_id(user)
        if not user_id or user_id in existing_ids:
            continue
        email = _auth_user_email(user)
        inserts.append(
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "role": "admin" if is_bootstrap_admin(email) else "user",
            }
        )
        existing_ids.add(user_id)
    if inserts:
        sb.table("organization_members").insert(inserts).execute()


@transient_retry()
def create_personal_org(user_id: str, email: str | None = None) -> AuthContext:
    """Return/create the default organisation membership for a user.

    Only configured bootstrap admin emails are auto-admin. Everyone else starts
    as user and can be promoted later by an admin.
    """
    sb = service_client()
    try:
        default_org = _get_or_create_default_org(sb, user_id)
        existing = (
            sb.table("organization_members")
            .select("organization_id, role, organizations(name)")
            .eq("user_id", user_id)
            .eq("organization_id", default_org["id"])
            .limit(1)
            .execute()
            .data
            or []
        )
    except APIError as e:
        if _org_schema_missing(e):
            return _legacy_context(user_id, email)
        raise
    if existing:
        row = existing[0]
        org = row.get("organizations") or {}
        role = normalize_role(row.get("role"))
        if is_bootstrap_admin(email) and role != "admin":
            row = (
                sb.table("organization_members")
                .update({"role": "admin"})
                .eq("organization_id", default_org["id"])
                .eq("user_id", user_id)
                .execute()
                .data[0]
            )
            role = normalize_role(row.get("role"))
        return AuthContext(
            user_id,
            row["organization_id"],
            org.get("name") or "Workspace",
            role,
            is_super_admin=is_bootstrap_admin(email),
        )

    role = "admin" if is_bootstrap_admin(email) else "user"
    sb.table("organization_members").insert(
        {"organization_id": default_org["id"], "user_id": user_id, "role": role}
    ).execute()
    return AuthContext(
        user_id,
        default_org["id"],
        default_org["name"],
        role,
        is_super_admin=is_bootstrap_admin(email),
    )


@transient_retry()
def get_user_org(user_id: str, email: str | None = None) -> AuthContext:
    """Return the user's active org; create default membership when missing."""
    return create_personal_org(user_id, email)


def list_org_members(organization_id: str) -> list[dict]:
    try:
        _sync_org_members_from_auth(organization_id)
    except Exception:
        pass
    rows = (
        service_client()
        .table("organization_members")
        .select("organization_id, user_id, role, created_at")
        .eq("organization_id", organization_id)
        .execute()
        .data
        or []
    )
    enriched = []
    for row in rows:
        user = None
        try:
            res = service_client().auth.admin.get_user_by_id(row["user_id"])
            user = getattr(res, "user", None)
        except Exception:
            pass
        email = getattr(user, "email", None)
        enriched.append(
            {
                **row,
                "email": email,
                "banned": bool(getattr(user, "banned_until", None)),
                "role": normalize_role(row.get("role")),
                "is_bootstrap_admin": is_bootstrap_admin(email),
                "is_super_admin": is_bootstrap_admin(email),
            }
        )
    return enriched


def set_org_member_role(organization_id: str, user_id: str, role: str) -> dict | None:
    raw = (role or "").strip().lower()
    if raw not in ROLE_ALIASES:
        raise ValueError("Role must be user, author, or admin")
    normalized = normalize_role(role)
    if normalized not in VALID_ROLES:
        raise ValueError("Role must be user, author, or admin")
    email = _user_email(user_id)
    if is_bootstrap_admin(email) and normalized != "admin":
        raise ValueError("Super Admin accounts must remain Super Admin")
    rows = (
        service_client()
        .table("organization_members")
        .update({"role": normalized})
        .eq("organization_id", organization_id)
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None
