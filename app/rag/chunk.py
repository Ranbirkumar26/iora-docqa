"""Text chunking for the RAG path. Char-based sliding window with overlap."""
from app.config import CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS


def chunk_text(
    text: str,
    size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Split text into overlapping chunks.

    Overlap keeps context across chunk boundaries so a fact split mid-sentence
    still appears whole in at least one chunk.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks = []
    step = size - overlap
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += step
    return chunks
