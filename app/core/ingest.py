"""Upload pipeline: parse -> store raw -> insert metadata -> chunk -> embed -> store chunks.

Indexing is inline (synchronous) for v1 simplicity. For very large batches this
could be moved to a background worker; noted as future work.
"""
import hashlib
import uuid

from app.config import STORAGE_BUCKET
from app.db.client import service_client
from app.parsers.parse import parse_file
from app.rag.chunk import chunk_for_type
from app.rag.embed import embed_documents


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dedupe_check(organization_id: str, filename: str, data: bytes):
    """Decide what to do with an incoming file.

    Returns one of:
      ("skip", reason)        — identical content already stored
      ("replace", file_id)    — same filename, changed content -> re-index
      ("new", None)           — brand new
    """
    sb = service_client()
    h = _hash(data)
    dup = (
        sb.table("files")
        .select("id")
        .eq("organization_id", organization_id)
        .eq("content_hash", h)
        .execute()
        .data
    )
    if dup:
        return ("skip", "duplicate — identical content already uploaded")
    same_name = (
        sb.table("files")
        .select("id")
        .eq("organization_id", organization_id)
        .eq("filename", filename)
        .execute()
        .data
    )
    if same_name:
        return ("replace", same_name[0]["id"])
    return ("new", None)


def delete_file(organization_id: str, file_id: str) -> None:
    """Remove a file's storage object + metadata row (chunks cascade via FK)."""
    sb = service_client()
    row = (
        sb.table("files")
        .select("storage_path")
        .eq("id", file_id)
        .eq("organization_id", organization_id)
        .execute()
        .data
    )
    if not row:
        return
    try:
        sb.storage.from_(STORAGE_BUCKET).remove([row[0]["storage_path"]])
    except Exception:
        pass
    sb.table("files").delete().eq("id", file_id).eq("organization_id", organization_id).execute()


def ingest_one(user_id: str, organization_id: str, filename: str, data: bytes) -> dict:
    """Full pipeline for a single file. Raises ValueError on unsupported type."""
    sb = service_client()

    # 1. parse -> text (raises ValueError for unsupported type)
    text = parse_file(filename, data)
    char_count = len(text)

    file_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    storage_path = f"{organization_id}/{file_id}/{filename}"

    # 2. store raw bytes
    sb.storage.from_(STORAGE_BUCKET).upload(
        storage_path, data, {"content-type": "application/octet-stream"}
    )

    # 3. metadata row + parsed text + content hash (direct mode reads parsed_text;
    #    content_hash powers dedup / incremental re-index)
    sb.table("files").insert(
        {
            "id": file_id,
            "organization_id": organization_id,
            "user_id": user_id,
            "filename": filename,
            "file_type": ext,
            "storage_path": storage_path,
            "char_count": char_count,
            "parsed_text": text,
            "content_hash": _hash(data),
            "indexed": False,
        }
    ).execute()

    # 4. chunk (structure-aware) + embed + store
    chunks = chunk_for_type(text, ext)
    if chunks:
        embeddings = embed_documents(chunks)
        rows = [
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": i,
                "content": c,
                "embedding": str(e),  # pgvector accepts text form "[...]"
            }
            for i, (c, e) in enumerate(zip(chunks, embeddings))
        ]
        sb.table("document_chunks").insert(rows).execute()

    # 5. mark indexed
    sb.table("files").update({"indexed": True}).eq("id", file_id).execute()

    return {"file_id": file_id, "filename": filename, "char_count": char_count}
