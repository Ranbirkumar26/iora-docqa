"""Question answering. Auto-switches direct (full context) vs RAG (retrieval)."""
import re

from app.core.corpus import corpus_stats, fetch_all_texts
from app.core.decision import answer_decision, looks_decision_support
from app.core.memory import add_memory, detect_remember, memory_block
from app.core.outputs import save_message
from app.core.search import reciprocal_rank_fusion, search_chunks
from app.core.structured import answer_structured, looks_quantitative
from app.db.client import read_client
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


def _record_answer(
    user_id: str,
    organization_id: str,
    result: dict,
    use_org: bool,
    persist: bool = True,
) -> dict:
    if persist:
        save_message(
            user_id,
            organization_id,
            "assistant",
            result.get("answer", ""),
            use_org,
            mode=result.get("mode"),
            sources=result.get("sources") or [],
            metadata={"sql": result.get("sql")} if result.get("sql") else {},
        )
    return result


def ask(
    user_id: str,
    organization_id: str,
    question: str,
    use_org: bool = True,
    persist: bool = True,
    allow_memory_write: bool = True,
    token: str | None = None,
) -> dict:
    # light normalize: trim + collapse whitespace (no autocorrect — would mangle
    # domain terms / proper nouns and hurt retrieval)
    question = re.sub(r"\s+", " ", question).strip()
    if persist:
        save_message(user_id, organization_id, "user", question, use_org)

    # 1) explicit "remember ..." -> save the fact, confirm, skip doc lookup
    fact = detect_remember(question)
    if fact:
        if not allow_memory_write:
            return _record_answer(
                user_id,
                organization_id,
                {
                    "answer": "This account is read-only, so permanent memory changes are disabled.",
                    "mode": "memory",
                    "sources": [],
                },
                use_org,
                persist,
            )
        saved = add_memory(user_id, fact)
        return _record_answer(
            user_id,
            organization_id,
            {
                "answer": f"Got it. I will remember that: {saved}",
                "mode": "memory",
                "sources": [],
            },
            use_org,
            persist,
        )

    mem = memory_block(user_id)
    scope_id = organization_id if use_org else user_id
    stats = corpus_stats(scope_id, use_org)

    # 2) no documents: answer from memory if we have any, else say so
    if stats["total_files"] == 0:
        if not mem:
            return _record_answer(
                user_id,
                organization_id,
                {"answer": "No documents uploaded yet.", "mode": "none", "sources": []},
                use_org,
                persist,
            )
        answer = complete(
            "You are a helpful assistant. Answer using only the known user facts "
            "below. If the answer is not among them, say you do not have that "
            "information yet.",
            f"{mem}\n\nQuestion: {question}",
        )
        return _record_answer(
            user_id,
            organization_id,
            {"answer": answer, "mode": "memory", "sources": []},
            use_org,
            persist,
        )

    # 3) quantitative questions over tabular data -> exact SQL via DuckDB
    if looks_quantitative(question):
        s = answer_structured(scope_id, question, use_org)
        if s is not None:
            return _record_answer(user_id, organization_id, s, use_org, persist)

    # 4) recommendations / prioritization -> grounded decision-support mode.
    # Keep this after structured Q&A so factual counts stay computed by DuckDB.
    if looks_decision_support(question):
        return _record_answer(
            user_id,
            organization_id,
            answer_decision(user_id, organization_id, question, stats, use_org),
            use_org,
            persist,
        )

    if stats["mode"] == "direct":
        context = fetch_all_texts(scope_id, use_org)
        user_msg = f"Documents:\n\n{context}\n\nQuestion: {question}"
        sources = []
    else:
        scope_org = organization_id if use_org else None
        emb = embed_query(question)
        sb = read_client(token)  # RLS-scoped to the caller when a token is present
        # semantic retrieval (pgvector)
        vec_rows = (
            sb.rpc(
                "match_chunks",
                {
                    "p_user_id": user_id,
                    "p_organization_id": scope_org,
                    "query_embedding": str(emb),
                    "match_count": RAG_TOP_K,
                },
            )
            .execute()
            .data
            or []
        )
        # keyword retrieval (FTS), fused with the vector hits so exact terms the
        # embedding misses still surface. Degrades to vector-only when the FTS
        # schema isn't applied (search_chunks returns []).
        kw_rows = search_chunks(user_id, question, RAG_TOP_K, scope_org, token=token)
        rows = reciprocal_rank_fusion(vec_rows, kw_rows, limit=RAG_TOP_K)
        context = "\n\n".join(
            f"[Source: {r['filename']}]\n{r['content']}" for r in rows
        )
        sources = sorted({r["filename"] for r in rows})
        user_msg = f"Document excerpts:\n\n{context}\n\nQuestion: {question}"

    # inject saved user facts alongside the document grounding
    system = SYSTEM + (f"\n\n{mem}" if mem else "")
    answer = complete(system, user_msg)
    return _record_answer(
        user_id,
        organization_id,
        {"answer": answer, "mode": stats["mode"], "sources": sources},
        use_org,
        persist,
    )
