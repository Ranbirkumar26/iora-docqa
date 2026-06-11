"""Embeddings. Provider switch via EMBED_PROVIDER env (gemini | voyage)."""
from functools import lru_cache

from app.config import (
    EMBED_DIM,
    EMBED_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_EMBED_MODEL,
    VOYAGE_API_KEY,
    VOYAGE_MODEL,
)

_BATCH = 100

# ---------------- Gemini (default, free) ----------------
_gemini_client = None


def _gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _gemini_embed(texts: list[str], task_type: str) -> list[list[float]]:
    from google.genai import types

    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        batch = texts[i : i + _BATCH]
        r = _gemini().models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBED_DIM,
            ),
        )
        out.extend(e.values for e in r.embeddings)
    return out


# ---------------- Voyage (optional) ----------------
_voyage_client = None


def _voyage():
    global _voyage_client
    if _voyage_client is None:
        import voyageai

        _voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _voyage_client


def _voyage_embed(texts: list[str], input_type: str) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 128):
        batch = texts[i : i + 128]
        res = _voyage().embed(batch, model=VOYAGE_MODEL, input_type=input_type)
        out.extend(res.embeddings)
    return out


# ---------------- public API ----------------
def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if EMBED_PROVIDER == "voyage":
        return _voyage_embed(texts, "document")
    return _gemini_embed(texts, "RETRIEVAL_DOCUMENT")


@lru_cache(maxsize=512)
def embed_query(text: str) -> list[float]:
    """Embed a search query. Cached: identical repeat questions skip the API call."""
    if EMBED_PROVIDER == "voyage":
        return _voyage_embed([text], "query")[0]
    return _gemini_embed([text], "RETRIEVAL_QUERY")[0]
