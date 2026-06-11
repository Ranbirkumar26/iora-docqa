"""Voyage AI embeddings. Batched to respect API limits."""
import voyageai

from app.config import VOYAGE_API_KEY, VOYAGE_MODEL

_BATCH = 128  # Voyage max texts per request

_client = None


def _voyage():
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunk texts for storage. Batched."""
    if not texts:
        return []
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        batch = texts[i : i + _BATCH]
        res = _voyage().embed(batch, model=VOYAGE_MODEL, input_type="document")
        out.extend(res.embeddings)
    return out


def embed_query(text: str) -> list[float]:
    """Embed a single search query. input_type='query' improves retrieval."""
    res = _voyage().embed([text], model=VOYAGE_MODEL, input_type="query")
    return res.embeddings[0]
