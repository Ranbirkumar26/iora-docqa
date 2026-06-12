"""Question answering. Auto-switches direct (full context) vs RAG (retrieval)."""
import re

from app.core.corpus import corpus_stats, fetch_all_texts
from app.core.memory import add_memory, detect_remember, memory_block
from app.core.structured import answer_structured, looks_quantitative
from app.db.client import service_client
from app.llm.provider import complete
from app.rag.embed import embed_query

SYSTEM = (
    "You are a document analyst. Use ONLY the provided documents as your source of "
    "facts — never invent facts that are not present or derivable from them.\n"
    "You MAY analyze, compute, compare, rank, and draw reasoned conclusions from the "
    "data in the documents.\n"
    "When the user asks for a judgment, recommendation, or 'best/top' that the documents "
    "do not state outright but contain relevant data for, derive a best-effort answer "
    "from that data and briefly explain your reasoning and any assumptions.\n"
    "If the question assumes a field the documents lack (e.g. it asks about X but there "
    "is no X data), say so plainly, then offer the closest relevant insight the data "
    "DOES support.\n"
    "Only reply 'This information is not found in the uploaded documents.' when the "
    "documents contain nothing relevant to the question at all.\n"
    "Cite the source filename(s) you used."
)

RAG_TOP_K = 15


def ask(
    user_id: str,
    organization_id: str,
    question: str,
    use_org: bool = True,
) -> dict:
    # light normalize: trim + collapse whitespace (no autocorrect — would mangle
    # domain terms / proper nouns and hurt retrieval)
    question = re.sub(r"\s+", " ", question).strip()

    # 1) explicit "remember ..." -> save the fact, confirm, skip doc lookup
    fact = detect_remember(question)
    if fact:
        saved = add_memory(user_id, fact)
        return {
            "answer": f"Got it. I will remember that: {saved}",
            "mode": "memory",
            "sources": [],
        }

    mem = memory_block(user_id)
    scope_id = organization_id if use_org else user_id
    stats = corpus_stats(scope_id, use_org)

    # 2) no documents: answer from memory if we have any, else say so
    if stats["total_files"] == 0:
        if not mem:
            return {"answer": "No documents uploaded yet.", "mode": "none", "sources": []}
        answer = complete(
            "You are a helpful assistant. Answer using only the known user facts "
            "below. If the answer is not among them, say you do not have that "
            "information yet.",
            f"{mem}\n\nQuestion: {question}",
        )
        return {"answer": answer, "mode": "memory", "sources": []}

    # 3) quantitative questions over tabular data -> exact SQL via DuckDB
    if looks_quantitative(question):
        s = answer_structured(scope_id, question, use_org)
        if s is not None:
            return s

    if stats["mode"] == "direct":
        context = fetch_all_texts(scope_id, use_org)
        user_msg = f"Documents:\n\n{context}\n\nQuestion: {question}"
        sources = []
    else:
        emb = embed_query(question)
        sb = service_client()
        rpc_args = {
            "p_user_id": user_id,
            "query_embedding": str(emb),
            "match_count": RAG_TOP_K,
        }
        if use_org:
            rpc_args["p_organization_id"] = organization_id
        rows = (
            sb.rpc("match_chunks", rpc_args)
            .execute()
            .data
            or []
        )
        context = "\n\n".join(
            f"[Source: {r['filename']}]\n{r['content']}" for r in rows
        )
        sources = sorted({r["filename"] for r in rows})
        user_msg = f"Document excerpts:\n\n{context}\n\nQuestion: {question}"

    # inject saved user facts alongside the document grounding
    system = SYSTEM + (f"\n\n{mem}" if mem else "")
    answer = complete(system, user_msg)
    return {"answer": answer, "mode": stats["mode"], "sources": sources}
