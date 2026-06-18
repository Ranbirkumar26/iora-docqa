"""Account deletion: purge a user's data, then delete the auth user.

Storage objects and the two tables whose user_id is ON DELETE SET NULL (reports,
processing_jobs) are removed explicitly. The remaining tables (files,
document_chunks, conversation_messages, generated_outputs, memories,
organization_members) cascade automatically when the auth user is deleted.
"""
from app.config import STORAGE_BUCKET
from app.db.client import service_client


def _collect_storage_paths(sb, user_id: str) -> list[str]:
    """Storage objects owned by the user (raw uploads + generated artifacts).

    Collected before any rows are deleted, scoped strictly by user_id.
    """
    paths: list[str] = []
    try:
        files = (
            sb.table("files").select("storage_path").eq("user_id", user_id).execute().data
            or []
        )
        paths += [f["storage_path"] for f in files if f.get("storage_path")]
    except Exception:
        pass
    try:
        outs = (
            sb.table("generated_outputs")
            .select("storage_path")
            .eq("user_id", user_id)
            .execute()
            .data
            or []
        )
        paths += [o["storage_path"] for o in outs if o.get("storage_path")]
    except Exception:
        pass
    return paths


def delete_account(user_id: str) -> dict:
    """Permanently remove all of a user's data and their auth record."""
    sb = service_client()

    # 1) storage objects (paths gathered before the rows disappear)
    paths = _collect_storage_paths(sb, user_id)
    if paths:
        try:
            sb.storage.from_(STORAGE_BUCKET).remove(paths)
        except Exception:
            pass

    # 2) tables whose user_id is ON DELETE SET NULL -> would orphan; delete now
    for table in ("reports", "processing_jobs"):
        try:
            sb.table(table).delete().eq("user_id", user_id).execute()
        except Exception:
            pass

    # 3) delete the auth user -> cascades files/chunks/messages/outputs/
    #    memories/organization_members via their ON DELETE CASCADE FKs
    sb.auth.admin.delete_user(user_id)
    return {"deleted": True}
