"""Organisation-style corpus report generation.

This is the first slice of the larger workflow: deterministic statistics for
tabular files plus LLM qualitative synthesis over the uploaded corpus.
"""
from __future__ import annotations

import math

import pandas as pd

from app.config import STORAGE_BUCKET
from app.core.corpus import corpus_stats, fetch_all_texts
from app.core.jobs import create_job, update_job
from app.core.outputs import save_output
from app.core.structured import load_tables
from app.db.client import service_client
from app.llm.provider import complete
from app.parsers.parse import parse_file

SYSTEM = (
    "You are a senior research and business analyst. Write grounded, concise "
    "reports from the user's uploaded documents only. Do not invent facts."
)

MAX_REPORT_CONTEXT_CHARS = 90_000


def _fmt_num(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _table_stats(tables: list[tuple[str, pd.DataFrame, str]]) -> str:
    """Return compact deterministic analysis for uploaded csv/xlsx tables."""
    if not tables:
        return "No tabular files found."

    parts: list[str] = []
    for table_name, df, source in tables:
        rows, cols = df.shape
        parts.append(f"### {source} / `{table_name}`\nRows: {rows:,}; columns: {cols:,}.")

        missing = df.isna().sum()
        missing = missing[missing > 0].sort_values(ascending=False).head(8)
        if not missing.empty:
            miss = ", ".join(f"{col}: {int(count):,}" for col, count in missing.items())
            parts.append(f"Missing values: {miss}.")

        numeric = df.select_dtypes(include="number")
        if not numeric.empty:
            parts.append("Numeric signals:")
            for col in numeric.columns[:8]:
                s = numeric[col].dropna()
                if s.empty:
                    continue
                parts.append(
                    "- "
                    f"{col}: avg {_fmt_num(s.mean())}, min {_fmt_num(s.min())}, "
                    f"max {_fmt_num(s.max())}, std {_fmt_num(s.std(ddof=0))}"
                )

        categorical = df.select_dtypes(exclude="number")
        if not categorical.empty:
            parts.append("Top categorical values:")
            for col in categorical.columns[:5]:
                vc = categorical[col].dropna().astype(str).value_counts().head(3)
                if vc.empty:
                    continue
                vals = ", ".join(f"{idx} ({count})" for idx, count in vc.items())
                parts.append(f"- {col}: {vals}")
    return "\n".join(parts)


def _scope_column(use_org: bool) -> str:
    return "organization_id" if use_org else "user_id"


def _source_files(scope_id: str, use_org: bool = True) -> list[str]:
    rows = (
        service_client()
        .table("files")
        .select("filename")
        .eq(_scope_column(use_org), scope_id)
        .order("upload_date")
        .execute()
        .data
        or []
    )
    return [r["filename"] for r in rows]


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


def _corpus_context(scope_id: str, use_org: bool = True) -> str:
    context = fetch_all_texts(scope_id, use_org)
    if len(context) <= MAX_REPORT_CONTEXT_CHARS:
        return context
    return (
        context[:MAX_REPORT_CONTEXT_CHARS]
        + "\n\n[Context truncated for report generation. Use Ask for targeted follow-ups.]"
    )


def _qualitative_analysis(context: str) -> str:
    prompt = (
        "Extract qualitative signals from these documents. Return short markdown "
        "sections for: pain points, sentiment, competitor mentions, risks, "
        "opportunities, and notable entities. Cite source filenames when visible.\n\n"
        f"Documents:\n{context}"
    )
    return complete(SYSTEM, prompt, max_tokens=1600, temperature=0)


def _save_report(
    user_id: str,
    organization_id: str,
    report: str,
    mode: str,
    sources: list[str],
    structured: str,
    qualitative: str,
    title: str = "Corpus report",
) -> dict:
    row = (
        service_client()
        .table("reports")
        .insert(
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "title": title,
                "report": report,
                "mode": mode,
                "sources": sources,
                "structured_analysis": structured,
                "qualitative_analysis": qualitative,
            }
        )
        .execute()
        .data[0]
    )
    return row


def list_reports(scope_id: str, use_org: bool = True, limit: int = 20) -> list[dict]:
    scope_col = "organization_id" if use_org else "user_id"
    return (
        service_client()
        .table("reports")
        .select("id, title, report, mode, sources, created_at")
        .eq(scope_col, scope_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def get_report(scope_id: str, report_id: str, use_org: bool = True) -> dict | None:
    scope_col = "organization_id" if use_org else "user_id"
    rows = (
        service_client()
        .table("reports")
        .select(
            "id, title, report, mode, sources, structured_analysis, "
            "qualitative_analysis, created_at"
        )
        .eq(scope_col, scope_id)
        .eq("id", report_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _single_file_report(
    filename: str,
    text: str,
    stats: dict,
    structured: str,
    qualitative: str,
) -> str:
    context = text
    if len(context) > MAX_REPORT_CONTEXT_CHARS:
        context = (
            context[:MAX_REPORT_CONTEXT_CHARS]
            + "\n\n[Document truncated for report generation.]"
        )
    prompt = (
        "Create a structured markdown report for this single uploaded document. "
        "Use these sections exactly: Executive Summary, Key Findings, Extracted "
        "User/Customer Details, Statistical Signals, Qualitative Signals, Risks, "
        "Opportunities, Recommendations, Sources.\n\n"
        f"Document: {filename}\n"
        f"Corpus stats: {stats}\n\n"
        f"Structured statistical analysis for this file:\n{structured}\n\n"
        f"Qualitative extraction for this file:\n{qualitative}\n\n"
        f"Document text:\n{context}\n\n"
        "The report must be grounded only in this document."
    )
    return complete(SYSTEM, prompt, max_tokens=2200, temperature=0)


def _generate_individual_reports(
    user_id: str,
    organization_id: str,
    use_org: bool,
    stats: dict,
    job_id: str | None,
) -> dict:
    scope_id = organization_id if use_org else user_id
    files = _files_with_text(scope_id, use_org)
    tables = load_tables(scope_id, use_org)
    sections: list[str] = []
    saved_reports: list[dict] = []

    for f in files:
        filename = f["filename"]
        file_tables = [table for table in tables if table[2] == filename]
        structured = _table_stats(file_tables)
        text = f.get("parsed_text") or ""
        qualitative = _qualitative_analysis(
            text[:MAX_REPORT_CONTEXT_CHARS]
            if len(text) > MAX_REPORT_CONTEXT_CHARS
            else text
        )
        report = _single_file_report(filename, text, stats, structured, qualitative)
        title = f"Report: {filename}"
        sections.append(f"## {filename}\n\n{report}")

        saved_id = None
        created_at = None
        if use_org:
            saved = _save_report(
                user_id,
                organization_id,
                report,
                stats["mode"],
                [filename],
                structured,
                qualitative,
                title=title,
            )
            saved_id = saved["id"]
            created_at = saved["created_at"]
            saved_reports.append(saved)

        save_output(
            user_id,
            organization_id,
            "report",
            title,
            report,
            use_org,
            file_id=f["id"],
            sources=[filename],
            metadata={
                "report_id": saved_id,
                "created_at": created_at,
                "collective": False,
                "mode": stats["mode"],
            },
        )

    batch = "# Individual Reports\n\n" + "\n\n".join(sections)
    save_output(
        user_id,
        organization_id,
        "report_batch",
        "Individual reports",
        batch,
        use_org,
        sources=[f["filename"] for f in files],
        metadata={
            "file_count": len(files),
            "report_ids": [r["id"] for r in saved_reports],
            "collective": False,
            "mode": stats["mode"],
        },
    )
    if job_id:
        update_job(
            job_id,
            "completed",
            metadata={"report_ids": [r["id"] for r in saved_reports]},
        )
    return {
        "id": saved_reports[0]["id"] if saved_reports else None,
        "report_ids": [r["id"] for r in saved_reports],
        "created_at": saved_reports[0]["created_at"] if saved_reports else None,
        "report": batch,
        "mode": stats["mode"],
        "sources": [f["filename"] for f in files],
        "structured_analysis": "\n\n".join(
            f"### {f['filename']}\n{_table_stats([t for t in tables if t[2] == f['filename']])}"
            for f in files
        ),
        "qualitative_analysis": "Saved inside each individual report.",
        "job_id": job_id,
        "collective": False,
    }


def generate_report(
    user_id: str,
    organization_id: str,
    use_org: bool = True,
    collective: bool = False,
) -> dict:
    """Generate individual reports by default; collective only when requested."""
    scope_id = organization_id if use_org else user_id
    stats = corpus_stats(scope_id, use_org)
    if stats["total_files"] == 0:
        return {
            "id": None,
            "report": "No documents uploaded yet.",
            "mode": "none",
            "sources": [],
            "structured_analysis": "",
            "qualitative_analysis": "",
            "job_id": None,
            "collective": collective,
        }

    job_kind = "collective_report_generation" if collective else "individual_report_generation"
    job_id = create_job(user_id, organization_id, job_kind) if use_org else None
    try:
        if not collective:
            return _generate_individual_reports(
                user_id, organization_id, use_org, stats, job_id
            )

        sources = _source_files(scope_id, use_org)
        tables = load_tables(scope_id, use_org)
        structured = _table_stats(tables)
        context = _corpus_context(scope_id, use_org)
        qualitative = _qualitative_analysis(context)

        prompt = (
            "Create a structured markdown report for this organisation's uploaded "
            "documents. Use these sections exactly: Executive Summary, Key Findings, "
            "Statistical Signals, Qualitative Signals, Risks, Opportunities, "
            "Recommendations, Sources.\n\n"
            f"Corpus stats: {stats}\n"
            f"Source files: {sources}\n\n"
            f"Structured statistical analysis:\n{structured}\n\n"
            f"Qualitative extraction:\n{qualitative}\n\n"
            "The final report must be grounded only in the supplied analysis and files."
        )
        report = complete(SYSTEM, prompt, max_tokens=3000, temperature=0)
        if use_org:
            saved = _save_report(
                user_id,
                organization_id,
                report,
                stats["mode"],
                sources,
                structured,
                qualitative,
                title="Collective report",
            )
            saved_id = saved["id"]
            created_at = saved["created_at"]
            update_job(job_id, "completed", metadata={"report_id": saved_id})
        else:
            saved_id = None
            created_at = None
        save_output(
            user_id,
            organization_id,
            "collective_report",
            "Collective report",
            report,
            use_org,
            sources=sources,
            metadata={"report_id": saved_id, "collective": True, "mode": stats["mode"]},
        )
        return {
            "id": saved_id,
            "created_at": created_at,
            "report": report,
            "mode": stats["mode"],
            "sources": sources,
            "structured_analysis": structured,
            "qualitative_analysis": qualitative,
            "job_id": job_id,
            "collective": True,
        }
    except Exception as e:
        if job_id:
            update_job(job_id, "failed", detail=str(e))
        raise


__all__ = ["generate_report", "list_reports", "get_report", "_table_stats"]
