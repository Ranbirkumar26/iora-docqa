"""Grounded decision-support answers.

This path is separate from factual/SQL Q&A. It turns uploaded evidence into
recommendations, caveats, and next actions without letting the model invent
facts outside the corpus.
"""
import re

from app.core.corpus import fetch_all_texts
from app.core.report import MAX_REPORT_CONTEXT_CHARS, _table_stats
from app.core.structured import load_tables
from app.db.client import service_client
from app.llm.provider import complete
from app.rag.embed import embed_query

DECISION_TOP_K = 20

_DECISION_RE = re.compile(
    r"\b("
    r"recommend|recommendation|suggest|suggestion|advice|should|next step|"
    r"next action|action plan|prioriti[sz]e|improve|opportunit|risk|strategy|"
    r"decision|what can we do|what should we do|how can we|focus on|"
    r"where should|which .* should"
    r")\b",
    re.I,
)

SYSTEM = (
    "You are a decision-support analyst. Use ONLY the uploaded documents and "
    "computed table signals as evidence. You may make recommendations, but every "
    "recommendation must be grounded in the supplied evidence. If evidence is "
    "thin, say confidence is low and explain what data is missing."
)


def looks_decision_support(question: str) -> bool:
    """Return true when a question asks for advice, prioritization, or actions."""
    return bool(_DECISION_RE.search(question))


def _scope_column(use_org: bool) -> str:
    return "organization_id" if use_org else "user_id"


def _source_files(scope_id: str, use_org: bool) -> list[str]:
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


def _direct_context(scope_id: str, use_org: bool) -> str:
    context = fetch_all_texts(scope_id, use_org)
    if len(context) <= MAX_REPORT_CONTEXT_CHARS:
        return context
    return (
        context[:MAX_REPORT_CONTEXT_CHARS]
        + "\n\n[Context truncated. Ask narrower follow-ups for more detail.]"
    )


def _retrieved_context(
    user_id: str,
    organization_id: str,
    question: str,
    use_org: bool,
) -> tuple[str, list[str]]:
    emb = embed_query(
        question
        + " recommendations risks opportunities pain points blockers next actions"
    )
    rpc_args = {
        "p_user_id": user_id,
        "query_embedding": str(emb),
        "match_count": DECISION_TOP_K,
    }
    if use_org:
        rpc_args["p_organization_id"] = organization_id

    rows = (
        service_client()
        .rpc("match_chunks", rpc_args)
        .execute()
        .data
        or []
    )
    context = "\n\n".join(f"[Source: {r['filename']}]\n{r['content']}" for r in rows)
    return context, sorted({r["filename"] for r in rows})


def answer_decision(
    user_id: str,
    organization_id: str,
    question: str,
    stats: dict,
    use_org: bool = True,
) -> dict:
    scope_id = organization_id if use_org else user_id
    sources = _source_files(scope_id, use_org)
    tables = load_tables(scope_id, use_org)
    structured = _table_stats(tables)

    if stats["mode"] == "rag":
        context, retrieved_sources = _retrieved_context(
            user_id, organization_id, question, use_org
        )
        if retrieved_sources:
            sources = retrieved_sources
    else:
        context = _direct_context(scope_id, use_org)

    prompt = (
        "Answer the user's decision-support question using this exact markdown "
        "shape:\n"
        "## Recommendation\n"
        "Give the clearest recommendation in 1-3 bullets.\n\n"
        "## Evidence\n"
        "List the strongest facts, counts, patterns, or quoted signals. Mention "
        "source filenames when available.\n\n"
        "## Risks / Caveats\n"
        "State what could make the recommendation wrong, including missing or weak "
        "data.\n\n"
        "## Next Actions\n"
        "Give practical steps the team can take next.\n\n"
        "## Confidence\n"
        "Use High, Medium, or Low, with one short reason.\n\n"
        "Rules:\n"
        "- Do not invent facts, metrics, or customer quotes.\n"
        "- Prefer computed table signals over model-estimated numbers.\n"
        "- If the evidence is insufficient, recommend what data to collect next.\n\n"
        f"Question: {question}\n\n"
        f"Corpus stats: {stats}\n"
        f"Source files: {sources}\n\n"
        f"Computed table signals:\n{structured}\n\n"
        f"Document evidence:\n{context}"
    )
    answer = complete(SYSTEM, prompt, max_tokens=1800, temperature=0)
    return {"answer": answer, "mode": "decision", "sources": sources}


__all__ = ["answer_decision", "looks_decision_support"]
