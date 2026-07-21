"""Admin audit log.

Records privileged actions (role changes, suspend/reinstate, member removal).
Best-effort: writing an audit row must never break the primary action, and the
whole feature degrades to a no-op until the audit_events table is applied.
"""
from app.db.client import service_client


def _schema_missing(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "audit_events" in msg and (
        "does not exist" in msg
        or "could not find" in msg
        or "schema cache" in msg
        or "pgrst205" in msg
        or "42p01" in msg
    )


def write_audit(
    organization_id: str | None,
    actor_user_id: str | None,
    action: str,
    target_user_id: str | None = None,
    detail: str | None = None,
    target_email: str | None = None,
) -> None:
    """Record one audit event. Swallows all errors — auditing is never allowed
    to fail the action it is logging."""
    try:
        service_client().table("audit_events").insert(
            {
                "organization_id": organization_id,
                "actor_user_id": actor_user_id,
                "action": action,
                "target_user_id": target_user_id,
                "target_email": target_email,
                "detail": detail,
            }
        ).execute()
    except Exception:
        return


def list_audit(organization_id: str, limit: int = 100) -> list[dict]:
    try:
        return (
            service_client()
            .table("audit_events")
            .select(
                "id, actor_user_id, action, target_user_id, target_email, detail, created_at"
            )
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        if _schema_missing(exc):
            return []
        raise
