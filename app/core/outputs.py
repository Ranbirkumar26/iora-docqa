"""Durable conversation and generated-output persistence."""
from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from app.config import STORAGE_BUCKET
from app.db.client import service_client

OUTPUT_SUMMARY_KINDS = {"summary", "summary_batch", "collective_summary"}
OUTPUT_REPORT_KINDS = {"report", "report_batch", "collective_report"}
OUTPUT_PROCESSED_KINDS = {"transcript", "report", "extraction"}


def _scope_column(use_org: bool) -> str:
    return "organization_id" if use_org else "user_id"


def _schema_missing(exc: Exception, table: str | None = None) -> bool:
    msg = str(exc).lower()
    missing = (
        "could not find the table" in msg
        or "does not exist" in msg
        or "schema cache" in msg
        or "pgrst205" in msg
        or "42p01" in msg
    )
    return missing and (table is None or table.lower() in msg)


def _scope_id(user_id: str, organization_id: str | None, use_org: bool) -> str:
    return organization_id if use_org and organization_id else user_id


def _scoped_query(table: str, user_id: str, organization_id: str | None, use_org: bool):
    return (
        service_client()
        .table(table)
        .select("*")
        .eq(_scope_column(use_org), _scope_id(user_id, organization_id, use_org))
    )


def save_message(
    user_id: str,
    organization_id: str | None,
    role: str,
    content: str,
    use_org: bool = True,
    mode: str | None = None,
    sources: list[str] | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """Persist one chat message. Missing-table deployments degrade to no-op."""
    row = {
        "user_id": user_id,
        "role": role,
        "content": content,
        "mode": mode,
        "sources": sources or [],
        "metadata": metadata or {},
    }
    if organization_id:
        row["organization_id"] = organization_id
    try:
        data = (
            service_client()
            .table("conversation_messages")
            .insert(row)
            .execute()
            .data
            or []
        )
        return data[0] if data else None
    except Exception as exc:
        if _schema_missing(exc, "conversation_messages"):
            return None
        raise


def list_messages(
    user_id: str,
    organization_id: str | None,
    use_org: bool = True,
    limit: int = 250,
) -> list[dict]:
    try:
        rows = (
            _scoped_query("conversation_messages", user_id, organization_id, use_org)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        rows.reverse()
        return rows
    except Exception as exc:
        if _schema_missing(exc, "conversation_messages"):
            return []
        raise


def save_output(
    user_id: str,
    organization_id: str | None,
    kind: str,
    title: str,
    content: str,
    use_org: bool = True,
    file_id: str | None = None,
    format: str = "markdown",
    sources: list[str] | None = None,
    metadata: dict | None = None,
    storage_path: str | None = None,
) -> dict | None:
    """Persist a generated artifact. Missing-table deployments degrade to no-op."""
    row = {
        "user_id": user_id,
        "file_id": file_id,
        "kind": kind,
        "title": title,
        "content": content,
        "format": format,
        "sources": sources or [],
        "metadata": metadata or {},
        "storage_path": storage_path,
    }
    if organization_id:
        row["organization_id"] = organization_id
    try:
        data = (
            service_client()
            .table("generated_outputs")
            .insert(row)
            .execute()
            .data
            or []
        )
        return data[0] if data else None
    except Exception as exc:
        if _schema_missing(exc, "generated_outputs"):
            return None
        raise


def update_output_storage(output_id: str, storage_path: str) -> None:
    try:
        service_client().table("generated_outputs").update(
            {"storage_path": storage_path}
        ).eq("id", output_id).execute()
    except Exception as exc:
        if _schema_missing(exc, "generated_outputs"):
            return
        raise


def list_outputs(
    user_id: str,
    organization_id: str | None,
    use_org: bool = True,
    kinds: Iterable[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    try:
        query = _scoped_query("generated_outputs", user_id, organization_id, use_org)
        if kinds:
            query = query.in_("kind", list(kinds))
        return (
            query.order("created_at", desc=True).limit(limit).execute().data
            or []
        )
    except Exception as exc:
        if _schema_missing(exc, "generated_outputs"):
            return []
        raise


def get_output(
    user_id: str,
    organization_id: str | None,
    output_id: str,
    use_org: bool = True,
) -> dict | None:
    try:
        rows = (
            _scoped_query("generated_outputs", user_id, organization_id, use_org)
            .eq("id", output_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception as exc:
        if _schema_missing(exc, "generated_outputs"):
            return None
        raise


def output_counts(
    user_id: str,
    organization_id: str | None,
    use_org: bool = True,
) -> dict:
    rows = list_outputs(user_id, organization_id, use_org, limit=2000)
    counts = Counter(row["kind"] for row in rows)
    processed_file_ids = {
        row["file_id"]
        for row in rows
        if row.get("file_id") and row.get("kind") in OUTPUT_PROCESSED_KINDS
    }
    return {
        "processed_documents": len(processed_file_ids),
        "available_reports": sum(counts[k] for k in OUTPUT_REPORT_KINDS),
        "available_summaries": sum(counts[k] for k in OUTPUT_SUMMARY_KINDS),
        "exported_conversations": counts["conversation_export"],
        "generated_outputs": len(rows),
    }


def _files_for_export(user_id: str, organization_id: str | None, use_org: bool) -> list[dict]:
    try:
        return (
            service_client()
            .table("files")
            .select("id, filename, file_type, char_count, upload_date")
            .eq(_scope_column(use_org), _scope_id(user_id, organization_id, use_org))
            .order("upload_date")
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def _dt(value: str | None = None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return value


def build_conversation_export(
    user_id: str,
    organization_id: str | None,
    use_org: bool = True,
    format: str = "markdown",
) -> tuple[str, str, str]:
    """Return filename, mime type, and export body."""
    ext = "txt" if format == "txt" else "md"
    mime = "text/plain" if ext == "txt" else "text/markdown"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"iora-docqa-conversation-{stamp}.{ext}"

    files = _files_for_export(user_id, organization_id, use_org)
    messages = list_messages(user_id, organization_id, use_org)
    outputs = list_outputs(
        user_id,
        organization_id,
        use_org,
        kinds=["summary_batch", "collective_summary", "report_batch", "collective_report"],
        limit=50,
    )

    if ext == "txt":
        lines = [
            "iORA DocQA Conversation Export",
            f"Generated: {_dt()}",
            "",
            "Uploaded files",
        ]
        if files:
            lines.extend(
                f"- {f['filename']} ({f['file_type']}, {f['char_count']} chars, uploaded {f['upload_date']})"
                for f in files
            )
        else:
            lines.append("- None")
        lines.extend(["", "Conversation"])
        if messages:
            for msg in messages:
                role = msg["role"].upper()
                mode = f" [{msg['mode']}]" if msg.get("mode") else ""
                lines.extend([f"{_dt(msg.get('created_at'))} - {role}{mode}", msg["content"], ""])
        else:
            lines.append("No saved conversation yet.")
        lines.append("Generated summaries and reports")
        if outputs:
            for output in outputs:
                lines.extend([
                    f"{_dt(output.get('created_at'))} - {output['title']} ({output['kind']})",
                    output["content"],
                    "",
                ])
        else:
            lines.append("No generated summaries or reports yet.")
        return filename, mime, "\n".join(lines).strip() + "\n"

    lines = [
        "# iORA DocQA Conversation Export",
        "",
        f"Generated: `{_dt()}`",
        "",
        "## Uploaded Files",
        "",
    ]
    if files:
        lines.extend(
            f"- `{f['filename']}` ({f['file_type']}, {f['char_count']} chars, uploaded `{f['upload_date']}`)"
            for f in files
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Conversation", ""])
    if messages:
        for msg in messages:
            role = msg["role"].title()
            mode = f" `{msg['mode']}`" if msg.get("mode") else ""
            lines.extend([
                f"### {role}{mode}",
                "",
                f"`{_dt(msg.get('created_at'))}`",
                "",
                msg["content"],
                "",
            ])
    else:
        lines.append("No saved conversation yet.")
    lines.extend(["", "## Generated Summaries And Reports", ""])
    if outputs:
        for output in outputs:
            lines.extend([
                f"### {output['title']}",
                "",
                f"`{_dt(output.get('created_at'))}` · `{output['kind']}`",
                "",
                output["content"],
                "",
            ])
    else:
        lines.append("No generated summaries or reports yet.")
    return filename, mime, "\n".join(lines).strip() + "\n"


def attach_export_to_repository(
    user_id: str,
    organization_id: str | None,
    filename: str,
    content: str,
    use_org: bool = True,
) -> dict:
    from app.core.ingest import dedupe_check, delete_file, ingest_one

    data = content.encode("utf-8")
    scope_id = _scope_id(user_id, organization_id, use_org)
    action, info = dedupe_check(scope_id, filename, data, use_org)
    if action == "skip":
        return {"skipped": True, "reason": info, "filename": filename}
    if action == "replace":
        delete_file(scope_id, info, use_org)
    return ingest_one(user_id, organization_id or user_id, filename, data, use_org)


def _extract_detail_rows(filename: str, text: str, max_rows: int = 1000) -> list[dict]:
    rows: list[dict] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("[") or len(rows) >= max_rows:
            continue
        pairs: dict[str, str] = {}
        parts = [p.strip() for p in line.split(" | ") if p.strip()]
        for part in parts:
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            key = re.sub(r"\s+", " ", key).strip()
            value = value.strip()
            looks_like_label = (
                bool(re.match(r"^[A-Za-z][A-Za-z0-9 _./()-]{0,40}$", key))
                and "@" not in key
                and not key.lower().startswith(("http", "https"))
            )
            if looks_like_label and value:
                pairs[key] = value
        if pairs:
            rows.append({"source_file": filename, "source_line": idx, **pairs})

    if rows:
        return rows

    entity_rows: list[dict] = []
    patterns = {
        "email": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "phone": r"(?:\+?\d[\d\s().-]{7,}\d)",
        "url": r"https?://[^\s)]+",
        "percent": r"\b\d+(?:\.\d+)?%",
    }
    for kind, pattern in patterns.items():
        for match in re.findall(pattern, text):
            entity_rows.append({
                "source_file": filename,
                "field": kind,
                "value": match.strip(),
            })
    return entity_rows[:max_rows]


def _markdown_table(rows: list[dict], max_rows: int = 25) -> str:
    if not rows:
        return "No structured field/value details were detected."
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    preview = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in preview:
        vals = [str(row.get(col, "")).replace("|", "\\|") for col in columns]
        body.append("| " + " | ".join(vals) + " |")
    suffix = ""
    if len(rows) > max_rows:
        suffix = f"\n\nShowing {max_rows} of {len(rows)} extracted rows."
    return "\n".join([header, sep, *body]) + suffix


def build_extraction_artifact(filename: str, text: str) -> tuple[str, bytes, int]:
    rows = _extract_detail_rows(filename, text)
    df = pd.DataFrame(rows or [{"source_file": filename, "note": "No structured details detected"}])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="extracted_details", index=False)
    markdown = (
        f"## Extracted Details: {filename}\n\n"
        f"Rows extracted: {len(rows)}\n\n"
        f"{_markdown_table(rows)}"
    )
    return markdown, buf.getvalue(), len(rows)


def save_extraction_output(
    user_id: str,
    organization_id: str | None,
    file_id: str,
    filename: str,
    text: str,
    use_org: bool = True,
) -> dict | None:
    markdown, workbook, row_count = build_extraction_artifact(filename, text)
    output = save_output(
        user_id,
        organization_id,
        "extraction",
        f"Extracted details: {filename}",
        markdown,
        use_org,
        file_id=file_id,
        format="xlsx",
        sources=[filename],
        metadata={
            "row_count": row_count,
            "download_filename": f"{filename.rsplit('.', 1)[0]}-extracted-details.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )
    if not output:
        return None

    scope = _scope_id(user_id, organization_id, use_org)
    download_filename = output["metadata"]["download_filename"]
    storage_path = f"{scope}/generated/{output['id']}/{download_filename}"
    service_client().storage.from_(STORAGE_BUCKET).upload(
        storage_path,
        workbook,
        {"content-type": output["metadata"]["content_type"]},
    )
    update_output_storage(output["id"], storage_path)
    output["storage_path"] = storage_path
    return output


__all__ = [
    "attach_export_to_repository",
    "build_conversation_export",
    "build_extraction_artifact",
    "get_output",
    "list_messages",
    "list_outputs",
    "output_counts",
    "save_extraction_output",
    "save_message",
    "save_output",
]
