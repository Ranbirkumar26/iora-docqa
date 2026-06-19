"""Per-user profile (about details).

Scoped strictly by user_id. Degrades to empty until the profiles table is
applied, matching the rest of the app's graceful-schema behavior.
"""
from datetime import datetime, timezone

from app.db.client import service_client

FIELDS = ("full_name", "gender", "age", "phone", "city", "country", "bio")


def _schema_missing(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "profiles" in msg and (
        "does not exist" in msg
        or "could not find" in msg
        or "schema cache" in msg
        or "pgrst205" in msg
        or "42p01" in msg
    )


def get_profile(user_id: str) -> dict:
    try:
        rows = (
            service_client()
            .table("profiles")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else {}
    except Exception as exc:
        if _schema_missing(exc):
            return {}
        raise


def upsert_profile(user_id: str, fields: dict) -> dict:
    payload = {k: fields.get(k) for k in FIELDS}
    payload["user_id"] = user_id
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        service_client().table("profiles").upsert(payload).execute()
    except Exception as exc:
        if _schema_missing(exc):
            return {}
        raise
    return get_profile(user_id)
