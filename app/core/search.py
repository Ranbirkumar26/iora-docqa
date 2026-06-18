"""Full-text (keyword) search over document chunks.

Postgres tsvector FTS via the `search_chunks` RPC, strictly user-scoped. Two
consumers:
- the standalone /api/search endpoint (ranked passages + highlighted snippets);
- hybrid retrieval in qa.py, where keyword hits are fused with pgvector hits so
  exact tokens (names, IDs, codes, dates) that embeddings miss still surface.
"""
import re

from app.db.client import read_client, transient_retry

FTS_TOP_K = 15
# RRF constant from Cormack et al. 2009. Large enough that no single list
# dominates, small enough that top ranks still carry most of the weight.
RRF_K = 60


def _clean_query(query: str | None) -> str:
    return re.sub(r"\s+", " ", query or "").strip()


def _missing_search_fn(exc: Exception) -> bool:
    """True when the FTS schema (RPC / tsvector column) is not applied yet.

    Lets /ask and /search degrade gracefully on deployments that have not
    re-run schema.sql, instead of 500-ing.
    """
    msg = str(exc).lower()
    return (
        "search_chunks" in msg
        or "content_tsv" in msg
        or "pgrst202" in msg  # postgrest: function not found in schema cache
        or "could not find the function" in msg
    )


@transient_retry()
def search_chunks(
    user_id: str,
    query: str,
    limit: int = FTS_TOP_K,
    organization_id: str | None = None,
    token: str | None = None,
) -> list[dict]:
    """Ranked keyword matches for a user.

    Returns [] for an empty query or when the FTS schema is not yet applied.
    """
    q = _clean_query(query)
    if not q:
        return []
    try:
        return (
            read_client(token)
            .rpc(
                "search_chunks",
                {
                    "p_user_id": user_id,
                    "p_organization_id": organization_id,
                    "query_text": q,
                    "match_count": limit,
                },
            )
            .execute()
            .data
            or []
        )
    except Exception as exc:
        if _missing_search_fn(exc):
            return []
        raise


def reciprocal_rank_fusion(
    *ranked_lists: list[dict],
    k: int = RRF_K,
    limit: int | None = None,
) -> list[dict]:
    """Merge ranked result lists by Reciprocal Rank Fusion.

    Each item contributes 1/(k + position) from every list it appears in; items
    are returned highest-fused-score first. RRF combines lists whose score scales
    are incomparable (cosine similarity vs ts_rank) using rank position only, so
    no score normalization is needed. De-dupes on (filename, content).
    """
    scores: dict[tuple, float] = {}
    chosen: dict[tuple, dict] = {}
    for ranked in ranked_lists:
        for position, item in enumerate(ranked):
            ident = (item.get("filename"), item.get("content"))
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + position + 1)
            chosen.setdefault(ident, item)
    fused = sorted(
        chosen.values(),
        key=lambda it: scores[(it.get("filename"), it.get("content"))],
        reverse=True,
    )
    return fused[:limit] if limit else fused


__all__ = ["search_chunks", "reciprocal_rank_fusion", "FTS_TOP_K"]
