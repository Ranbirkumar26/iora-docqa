"""Organisation-style corpus report generation.

This is the first slice of the larger workflow: deterministic statistics for
tabular files plus LLM qualitative synthesis over the uploaded corpus.
"""
from __future__ import annotations

import math

import pandas as pd

from app.core.corpus import corpus_stats, fetch_all_texts
from app.core.jobs import create_job, update_job
from app.core.structured import load_tables
from app.db.client import service_client
from app.llm.provider import complete

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
) -> dict:
    title = "Corpus report"
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


def list_reports(organization_id: str, limit: int = 20) -> list[dict]:
    return (
        service_client()
        .table("reports")
        .select("id, title, report, mode, sources, created_at")
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def get_report(organization_id: str, report_id: str) -> dict | None:
    rows = (
        service_client()
        .table("reports")
        .select(
            "id, title, report, mode, sources, structured_analysis, "
            "qualitative_analysis, created_at"
        )
        .eq("organization_id", organization_id)
        .eq("id", report_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def generate_report(user_id: str, organization_id: str, use_org: bool = True) -> dict:
    """Generate an executive report over the user's current corpus."""
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
        }

    job_id = create_job(user_id, organization_id, "report_generation") if use_org else None
    try:
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
            )
            saved_id = saved["id"]
            created_at = saved["created_at"]
            update_job(job_id, "completed", metadata={"report_id": saved_id})
        else:
            saved_id = None
            created_at = None
        return {
            "id": saved_id,
            "created_at": created_at,
            "report": report,
            "mode": stats["mode"],
            "sources": sources,
            "structured_analysis": structured,
            "qualitative_analysis": qualitative,
            "job_id": job_id,
        }
    except Exception as e:
        if job_id:
            update_job(job_id, "failed", detail=str(e))
        raise


__all__ = ["generate_report", "list_reports", "get_report", "_table_stats"]
