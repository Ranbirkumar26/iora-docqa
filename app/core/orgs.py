"""Organisation helpers.

Every user gets a personal organisation by default. The rest of the app scopes
shared corpus data by organisation_id while keeping auth/memory user-scoped.
"""
from dataclasses import dataclass

from postgrest.exceptions import APIError

from app.db.client import service_client, transient_retry


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    organization_id: str
    organization_name: str
    org_enabled: bool = True

    @property
    def scope_id(self) -> str:
        return self.organization_id if self.org_enabled else self.user_id


def _name_from_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "Personal workspace"
    return f"{email.split('@', 1)[0]}'s workspace"


def _legacy_context(user_id: str, email: str | None = None) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        organization_id=user_id,
        organization_name=_name_from_email(email),
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
            .select("organization_id, organizations(name)")
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
        return AuthContext(user_id, row["organization_id"], org.get("name") or "Workspace")

    name = _name_from_email(email)
    org = (
        sb.table("organizations")
        .insert({"name": name, "created_by": user_id})
        .execute()
        .data[0]
    )
    sb.table("organization_members").insert(
        {"organization_id": org["id"], "user_id": user_id, "role": "owner"}
    ).execute()
    return AuthContext(user_id, org["id"], org["name"])


@transient_retry()
def get_user_org(user_id: str, email: str | None = None) -> AuthContext:
    """Return the user's active org; create a personal one when none exists."""
    return create_personal_org(user_id, email)
