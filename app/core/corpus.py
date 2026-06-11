"""Corpus-level helpers: size/mode stats and full-text fetch."""
from app.config import DIRECT_MODE_TOKEN_LIMIT, STORAGE_BUCKET, chars_to_tokens
from app.db.client import service_client, transient_retry
from app.parsers.parse import parse_file


@transient_retry()
def corpus_stats(user_id: str) -> dict:
    """Total files/chars/tokens for the user + which mode to use."""
    sb = service_client()
    res = sb.table("files").select("char_count").eq("user_id", user_id).execute()
    rows = res.data or []
    total_chars = sum(r["char_count"] for r in rows)
    total_tokens = chars_to_tokens(total_chars)
    mode = "direct" if total_tokens < DIRECT_MODE_TOKEN_LIMIT else "rag"
    return {
        "total_files": len(rows),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "mode": mode,
    }


@transient_retry()
def fetch_all_texts(user_id: str) -> str:
    """Concatenate every file's text (with filename separators) for direct mode.

    Reads pre-parsed text from the DB column (fast, no I/O). Legacy rows without
    it fall back to download + re-parse from storage.
    """
    sb = service_client()
    files = (
        sb.table("files")
        .select("storage_path, filename, parsed_text")
        .eq("user_id", user_id)
        .order("upload_date")
        .execute()
        .data
        or []
    )
    parts = []
    for f in files:
        text = f.get("parsed_text")
        if text is None:  # legacy row — fall back to storage
            data = sb.storage.from_(STORAGE_BUCKET).download(f["storage_path"])
            text = parse_file(f["filename"], data)
        parts.append(f"=== FILE: {f['filename']} ===\n{text}")
    return "\n\n".join(parts)
