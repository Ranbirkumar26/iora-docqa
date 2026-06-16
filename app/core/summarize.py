"""Summarization with individual outputs and explicit collective analysis."""
from app.config import STORAGE_BUCKET
from app.core.corpus import corpus_stats
from app.core.outputs import save_output
from app.db.client import service_client
from app.llm.provider import complete
from app.parsers.parse import parse_file

SYSTEM = "You are a document assistant that writes clear, faithful summaries."
MAX_FILE_SUMMARY_CHARS = 60_000


def _scope_column(use_org: bool) -> str:
    return "organization_id" if use_org else "user_id"


def _files_with_text(scope_id: str, use_org: bool = True) -> list[dict]:
    sb = service_client()
    files = (
        sb.table("files")
        .select("id, filename, storage_path, parsed_text")
        .eq(_scope_column(use_org), scope_id)
        .order("upload_date")
        .execute()
        .data
        or []
    )
    for f in files:
        if f.get("parsed_text") is None:
            raw = sb.storage.from_(STORAGE_BUCKET).download(f["storage_path"])
            f["parsed_text"] = parse_file(f["filename"], raw)
    return files


def _truncate(text: str, limit: int = MAX_FILE_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[Document truncated for summary generation.]"


def summarize(
    user_id: str,
    organization_id: str,
    use_org: bool = True,
    collective: bool = False,
) -> dict:
    scope_id = organization_id if use_org else user_id
    stats = corpus_stats(scope_id, use_org)
    if stats["total_files"] == 0:
        return {"summary": "No documents uploaded yet.", "mode": "none"}

    files = _files_with_text(scope_id, use_org)
    sections = []
    for f in files:
        text = _truncate(f.get("parsed_text") or "")
        summary = complete(
            SYSTEM,
            "Summarize this single document faithfully. Include key entities, "
            "important numbers, decisions, risks, and open questions when present. "
            f"Document: {f['filename']}\n\n{text}",
            max_tokens=900,
            temperature=0,
        )
        sections.append(f"## {f['filename']}\n\n{summary}")
        save_output(
            user_id,
            organization_id,
            "summary",
            f"Summary: {f['filename']}",
            summary,
            use_org,
            file_id=f["id"],
            sources=[f["filename"]],
            metadata={"collective": False, "mode": stats["mode"]},
        )

    combined = "# Individual Summaries\n\n" + "\n\n".join(sections)
    save_output(
        user_id,
        organization_id,
        "summary_batch",
        "Individual summaries",
        combined,
        use_org,
        sources=[f["filename"] for f in files],
        metadata={"file_count": len(files), "collective": False, "mode": stats["mode"]},
    )

    if not collective:
        return {"summary": combined, "mode": stats["mode"], "collective": False}

    overall = complete(
        SYSTEM,
        "The user explicitly requested a collective summary. Combine the individual "
        "summaries below into overall trends, common observations, shared issues or "
        "themes, and a final consolidated conclusion. Do not invent unsupported facts.\n\n"
        f"{combined}",
        max_tokens=1600,
        temperature=0,
    )
    collective_text = f"{combined}\n\n# Collective Summary\n\n{overall}"
    save_output(
        user_id,
        organization_id,
        "collective_summary",
        "Collective summary",
        overall,
        use_org,
        sources=[f["filename"] for f in files],
        metadata={"file_count": len(files), "collective": True, "mode": stats["mode"]},
    )
    return {"summary": collective_text, "mode": stats["mode"], "collective": True}
