"""Summarization. Direct mode = one call; RAG mode = map-reduce per file."""
from app.core.corpus import corpus_stats, fetch_all_texts
from app.db.client import service_client
from app.llm import claude

SYSTEM = "You are a document assistant that writes clear, faithful summaries."


def summarize(user_id: str) -> dict:
    stats = corpus_stats(user_id)
    if stats["total_files"] == 0:
        return {"summary": "No documents uploaded yet.", "mode": "none"}

    if stats["mode"] == "direct":
        context = fetch_all_texts(user_id)
        user_msg = (
            f"Documents:\n\n{context}\n\n"
            "First write a separate summary for each file (label it with the "
            "filename). Then write one overall summary combining all documents."
        )
        summary = claude.complete(SYSTEM, user_msg, max_tokens=3000)
        return {"summary": summary, "mode": "direct"}

    # RAG mode: summarize each file from its chunks, then combine (map-reduce)
    sb = service_client()
    files = (
        sb.table("files").select("id, filename").eq("user_id", user_id).execute().data
        or []
    )
    per_file = []
    for f in files:
        chunks = (
            sb.table("document_chunks")
            .select("content")
            .eq("file_id", f["id"])
            .order("chunk_index")
            .execute()
            .data
            or []
        )
        text = "\n".join(c["content"] for c in chunks)
        s = claude.complete(
            SYSTEM, f"Summarize this document ({f['filename']}):\n\n{text}", max_tokens=800
        )
        per_file.append(f"=== {f['filename']} ===\n{s}")

    combined = "\n\n".join(per_file)
    overall = claude.complete(
        SYSTEM,
        f"Individual document summaries below. Write one overall summary:\n\n{combined}",
        max_tokens=1000,
    )
    return {"summary": f"{combined}\n\n=== OVERALL SUMMARY ===\n{overall}", "mode": "rag"}
