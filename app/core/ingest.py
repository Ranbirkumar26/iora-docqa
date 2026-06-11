"""Upload pipeline: parse -> store raw -> insert metadata -> chunk -> embed -> store chunks.

Indexing is inline (synchronous) for v1 simplicity. For very large batches this
could be moved to a background worker; noted as future work.
"""
import uuid

from app.config import STORAGE_BUCKET
from app.db.client import service_client
from app.parsers.parse import parse_file
from app.rag.chunk import chunk_text
from app.rag.embed import embed_documents


def ingest_one(user_id: str, filename: str, data: bytes) -> dict:
    """Full pipeline for a single file. Raises ValueError on unsupported type."""
    sb = service_client()

    # 1. parse -> text (raises ValueError for unsupported type)
    text = parse_file(filename, data)
    char_count = len(text)

    file_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    storage_path = f"{user_id}/{file_id}/{filename}"

    # 2. store raw bytes
    sb.storage.from_(STORAGE_BUCKET).upload(
        storage_path, data, {"content-type": "application/octet-stream"}
    )

    # 3. metadata row (indexed flips true after chunks land)
    sb.table("files").insert(
        {
            "id": file_id,
            "user_id": user_id,
            "filename": filename,
            "file_type": ext,
            "storage_path": storage_path,
            "char_count": char_count,
            "indexed": False,
        }
    ).execute()

    # 4. chunk + embed + store
    chunks = chunk_text(text)
    if chunks:
        embeddings = embed_documents(chunks)
        rows = [
            {
                "user_id": user_id,
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
