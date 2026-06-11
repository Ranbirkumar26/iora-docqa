"""Question answering. Auto-switches direct (full context) vs RAG (retrieval)."""
from app.core.corpus import corpus_stats, fetch_all_texts
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


def ask(user_id: str, question: str) -> dict:
    stats = corpus_stats(user_id)
    if stats["total_files"] == 0:
        return {"answer": "No documents uploaded yet.", "mode": "none", "sources": []}

    if stats["mode"] == "direct":
        context = fetch_all_texts(user_id)
        user_msg = f"Documents:\n\n{context}\n\nQuestion: {question}"
        sources = []
    else:
        emb = embed_query(question)
        sb = service_client()
        rows = (
            sb.rpc(
                "match_chunks",
                {
                    "p_user_id": user_id,
                    "query_embedding": str(emb),
                    "match_count": RAG_TOP_K,
                },
            )
            .execute()
            .data
            or []
        )
        context = "\n\n".join(
            f"[Source: {r['filename']}]\n{r['content']}" for r in rows
        )
        sources = sorted({r["filename"] for r in rows})
        user_msg = f"Document excerpts:\n\n{context}\n\nQuestion: {question}"

    answer = complete(SYSTEM, user_msg)
    return {"answer": answer, "mode": stats["mode"], "sources": sources}
