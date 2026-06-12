"""Organisation helpers.

Every user gets a personal organisation by default. The rest of the app scopes
shared corpus data by organisation_id while keeping auth/memory user-scoped.
"""
from dataclasses import dataclass

from app.db.client import service_client, transient_retry


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    organization_id: str
    organization_name: str


def _name_from_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "Personal workspace"
    return f"{email.split('@', 1)[0]}'s workspace"


@transient_retry()
def create_personal_org(user_id: str, email: str | None = None) -> AuthContext:
    """Create the default organisation for a new user if needed."""
    sb = service_client()
    existing = (
        sb.table("organization_members")
        .select("organization_id, organizations(name)")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
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
