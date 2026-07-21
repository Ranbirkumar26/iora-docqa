"""Signup approval requests.

The preferred storage is the signup_requests table. Older deployments may not
have that table yet, so we fall back to audit_events; this keeps the live app
usable until the schema is applied from app/db/schema.sql.
"""
from __future__ import annotations

from datetime import datetime, timezone

from postgrest.exceptions import APIError

from app.db.client import service_client, transient_retry

VALID_SIGNUP_REQUEST_STATUSES = {"pending", "approved", "rejected"}
_ACTIONS = {
    "signup_request_pending": "pending",
    "signup_request_approved": "approved",
    "signup_request_rejected": "rejected",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    if code:
        return code
    if exc.args and isinstance(exc.args[0], dict):
        value = exc.args[0].get("code")
        return str(value) if value else None
    return None


def _api_error_message(exc: APIError) -> str:
    message = str(getattr(exc, "message", "") or "")
    if message:
        return message
    if exc.args and isinstance(exc.args[0], dict):
        return str(exc.args[0].get("message") or "")
    return str(exc)


def _signup_table_missing(exc: APIError) -> bool:
    message = _api_error_message(exc).lower()
    return _api_error_code(exc) in {"PGRST205", "42P01"} and "signup_requests" in message


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_row(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "email": _normalize_email(row.get("email") or row.get("target_email")),
        "status": row.get("status", "pending"),
        "requested_at": row.get("requested_at") or row.get("created_at"),
        "decided_at": row.get("decided_at"),
        "decided_by": row.get("decided_by") or row.get("actor_user_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _audit_rows() -> list[dict]:
    rows = (
        service_client()
        .table("audit_events")
        .select("id, action, target_email, actor_user_id, created_at")
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
        .data
        or []
    )
    return [row for row in rows if row.get("action") in _ACTIONS and row.get("target_email")]


def _latest_audit_requests() -> list[dict]:
    latest: dict[str, dict] = {}
    for row in _audit_rows():
        email = _normalize_email(row.get("target_email"))
        if not email or email in latest:
            continue
        latest[email] = {
            "id": row.get("id"),
            "email": email,
            "status": _ACTIONS.get(row.get("action"), "pending"),
            "requested_at": row.get("created_at"),
            "decided_at": row.get("created_at")
            if row.get("action") != "signup_request_pending"
            else None,
            "decided_by": row.get("actor_user_id")
            if row.get("action") != "signup_request_pending"
            else None,
            "created_at": row.get("created_at"),
            "updated_at": row.get("created_at"),
        }
    return list(latest.values())


def _audit_request_for_email(email: str) -> dict | None:
    normalized = _normalize_email(email)
    return next(
        (row for row in _latest_audit_requests() if row.get("email") == normalized),
        None,
    )


def _write_audit_request(
    email: str,
    status: str,
    organization_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict:
    payload = {
        "organization_id": organization_id,
        "actor_user_id": actor_user_id,
        "action": f"signup_request_{status}",
        "target_email": _normalize_email(email),
        "detail": f"signup request {status}",
    }
    row = service_client().table("audit_events").insert(payload).execute().data[0]
    return _normalize_row(
        {
            **row,
            "email": email,
            "status": status,
            "requested_at": row.get("created_at"),
            "decided_at": row.get("created_at") if status != "pending" else None,
            "decided_by": actor_user_id if status != "pending" else None,
        }
    )


@transient_retry()
def is_signup_approved(email: str) -> bool:
    normalized = _normalize_email(email)
    try:
        rows = (
            service_client()
            .table("signup_requests")
            .select("status")
            .eq("email", normalized)
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(rows and rows[0].get("status") == "approved")
    except APIError as exc:
        if not _signup_table_missing(exc):
            raise
    row = _audit_request_for_email(normalized)
    return bool(row and row.get("status") == "approved")


@transient_retry()
def create_signup_request(email: str, organization_id: str | None = None) -> dict:
    normalized = _normalize_email(email)
    try:
        existing = (
            service_client()
            .table("signup_requests")
            .select("*")
            .eq("email", normalized)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            row = existing[0]
            if row.get("status") == "approved":
                return _normalize_row(row)
            payload = {
                "status": "pending",
                "requested_at": _now_iso(),
                "decided_at": None,
                "decided_by": None,
                "updated_at": _now_iso(),
            }
            updated = (
                service_client()
                .table("signup_requests")
                .update(payload)
                .eq("id", row["id"])
                .execute()
                .data
                or []
            )
            return _normalize_row(updated[0] if updated else {**row, **payload})
        inserted = (
            service_client()
            .table("signup_requests")
            .insert({"email": normalized, "status": "pending"})
            .execute()
            .data
            or []
        )
        return _normalize_row(inserted[0])
    except APIError as exc:
        if not _signup_table_missing(exc):
            raise
    existing = _audit_request_for_email(normalized)
    if existing and existing.get("status") == "approved":
        return existing
    return _write_audit_request(normalized, "pending", organization_id)


@transient_retry()
def list_signup_requests() -> list[dict]:
    try:
        rows = (
            service_client()
            .table("signup_requests")
            .select("*")
            .order("requested_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
        return [_normalize_row(row) for row in rows]
    except APIError as exc:
        if not _signup_table_missing(exc):
            raise
    return _latest_audit_requests()


@transient_retry()
def set_signup_request_status(
    request_id: str,
    status: str,
    organization_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict | None:
    if status not in {"approved", "rejected"}:
        raise ValueError("Status must be approved or rejected")
    try:
        payload = {
            "status": status,
            "decided_at": _now_iso(),
            "decided_by": actor_user_id,
            "updated_at": _now_iso(),
        }
        rows = (
            service_client()
            .table("signup_requests")
            .update(payload)
            .eq("id", request_id)
            .execute()
            .data
            or []
        )
        return _normalize_row(rows[0]) if rows else None
    except APIError as exc:
        if not _signup_table_missing(exc):
            raise
    current = next((row for row in _latest_audit_requests() if row.get("id") == request_id), None)
    if not current:
        return None
    return _write_audit_request(
        current["email"],
        status,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
