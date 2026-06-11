"""Question answering. Auto-switches direct (full context) vs RAG (retrieval)."""
from app.core.corpus import corpus_stats, fetch_all_texts
from app.db.client import service_client
from app.llm import claude
from app.rag.embed import embed_query

SYSTEM = (
    "You are a document assistant. Answer the question strictly using the "
    "provided documents. If the answer is not present in them, reply exactly: "
    "'This information is not found in the uploaded documents.' "
    "Always cite the source filename(s) you used."
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

    answer = claude.complete(SYSTEM, user_msg)
    return {"answer": answer, "mode": stats["mode"], "sources": sources}
