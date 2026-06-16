"""Processing job records.

Jobs are synchronous for now, but these rows are the contract a future worker
queue can use without changing the UI/API shape.
"""
from datetime import datetime, timezone

from app.db.client import service_client, transient_retry


@transient_retry()
def create_job(
    user_id: str,
    organization_id: str,
    kind: str,
    status: str = "running",
    detail: str | None = None,
    metadata: dict | None = None,
) -> str:
    row = (
        service_client()
        .table("processing_jobs")
        .insert(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "kind": kind,
                "status": status,
                "detail": detail,
                "metadata": metadata or {},
            }
        )
        .execute()
        .data[0]
    )
    return row["id"]


@transient_retry()
def update_job(job_id: str, status: str, detail: str | None = None, metadata: dict | None = None):
    payload: dict = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if detail is not None:
        payload["detail"] = detail
    if metadata is not None:
        payload["metadata"] = metadata
    service_client().table("processing_jobs").update(payload).eq("id", job_id).execute()


@transient_retry()
def list_jobs(scope_id: str, use_org: bool = True, limit: int = 10) -> list[dict]:
    scope_col = "organization_id" if use_org else "user_id"
    return (
        service_client()
        .table("processing_jobs")
        .select("id, kind, status, detail, metadata, created_at, updated_at")
        .eq(scope_col, scope_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
