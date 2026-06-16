"""Organisation helpers.

Every user gets a personal organisation by default. The rest of the app scopes
shared corpus data by organisation_id while keeping auth/memory user-scoped.
"""
from dataclasses import dataclass

from postgrest.exceptions import APIError

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

    @property
    def scope_id(self) -> str:
        return self.read_scope_id

    @property
    def can_read_all(self) -> bool:
        return self.role in {"author", "admin"}

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
        return self.org_enabled and self.can_read_all

    @property
    def read_scope_id(self) -> str:
        return self.organization_id if self.read_scope_uses_org else self.user_id

    @property
    def write_scope_uses_org(self) -> bool:
        return self.org_enabled and self.can_write_all

    @property
    def write_scope_id(self) -> str:
        return self.organization_id if self.write_scope_uses_org else self.user_id


def normalize_role(role: str | None) -> str:
    return ROLE_ALIASES.get((role or "user").strip().lower(), "user")


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


@transient_retry()
def create_personal_org(user_id: str, email: str | None = None) -> AuthContext:
    """Create the default organisation for a new user if needed."""
    sb = service_client()
    try:
        existing = (
            sb.table("organization_members")
            .select("organization_id, role, organizations(name)")
            .eq("user_id", user_id)
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
        return AuthContext(
            user_id,
            row["organization_id"],
            org.get("name") or "Workspace",
            normalize_role(row.get("role")),
        )

    name = _name_from_email(email)
    org = (
        sb.table("organizations")
        .insert({"name": name, "created_by": user_id})
        .execute()
        .data[0]
    )
    sb.table("organization_members").insert(
        {"organization_id": org["id"], "user_id": user_id, "role": "admin"}
    ).execute()
    return AuthContext(user_id, org["id"], org["name"], "admin")


@transient_retry()
def get_user_org(user_id: str, email: str | None = None) -> AuthContext:
    """Return the user's active org; create a personal one when none exists."""
    return create_personal_org(user_id, email)


def list_org_members(organization_id: str) -> list[dict]:
    rows = (
        service_client()
        .table("organization_members")
        .select("organization_id, user_id, role, created_at")
        .eq("organization_id", organization_id)
        .execute()
        .data
        or []
    )
    return [{**row, "role": normalize_role(row.get("role"))} for row in rows]


def set_org_member_role(organization_id: str, user_id: str, role: str) -> dict | None:
    raw = (role or "").strip().lower()
    if raw not in ROLE_ALIASES:
        raise ValueError("Role must be user, author, or admin")
    normalized = normalize_role(role)
    if normalized not in VALID_ROLES:
        raise ValueError("Role must be user, author, or admin")
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
