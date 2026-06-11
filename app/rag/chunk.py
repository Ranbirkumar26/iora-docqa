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


def chunk_by_lines(text: str, size: int = CHUNK_SIZE_CHARS, overlap_lines: int = 1) -> list[str]:
    """Pack whole lines into chunks up to `size` chars — never splits a line.

    For tabular data (csv rows) this keeps each record intact, so a row never
    straddles a chunk boundary and loses its column context.
    """
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for ln in lines:
        cur.append(ln)
        cur_len += len(ln) + 1
        if cur_len >= size:
            chunks.append("\n".join(cur))
            cur = cur[-overlap_lines:] if overlap_lines else []
            cur_len = sum(len(x) + 1 for x in cur)
    if cur and (not chunks or "\n".join(cur) != chunks[-1]):
        chunks.append("\n".join(cur))
    return chunks


def chunk_xlsx(text: str, size: int = CHUNK_SIZE_CHARS) -> list[str]:
    """Chunk per sheet; prefix each chunk with its [Sheet: ...] marker.

    Keeps sheet attribution on every chunk and never mixes rows across sheets.
    """
    sheets: list[tuple[str, list[str]]] = []
    marker = None
    body: list[str] = []
    for ln in text.split("\n"):
        if ln.startswith("[Sheet:"):
            if marker is not None:
                sheets.append((marker, body))
            marker, body = ln, []
        elif ln.strip():
            body.append(ln)
    if marker is not None:
        sheets.append((marker, body))

    chunks: list[str] = []
    for mk, rows in sheets:
        for c in chunk_by_lines("\n".join(rows), size):
            chunks.append(f"{mk}\n{c}")
    return chunks


def chunk_for_type(
    text: str,
    file_type: str,
    size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Dispatch chunking by file type. csv/xlsx are structure-aware; txt slides."""
    if not text.strip():
        return []
    if file_type == "csv":
        return chunk_by_lines(text, size)
    if file_type == "xlsx":
        return chunk_xlsx(text, size)
    return chunk_text(text, size, overlap)
