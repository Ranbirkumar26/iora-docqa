"""Chunking tests. Pure Python, no API keys."""
from app.rag.chunk import chunk_text


def test_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_single_chunk():
    assert chunk_text("hello", size=100, overlap=10) == ["hello"]


def test_splits_long_text():
    text = "a" * 1000
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    # every chunk within size
    assert all(len(c) <= 300 for c in chunks)


def test_overlap_present():
    text = "0123456789" * 30  # 300 chars
    chunks = chunk_text(text, size=100, overlap=20)
    # tail of chunk0 reappears at head of chunk1
    assert chunks[0][-20:] == chunks[1][:20]


def test_covers_whole_text():
    text = "x" * 500 + "END"
    chunks = chunk_text(text, size=100, overlap=10)
    assert chunks[-1].endswith("END")


def test_overlap_ge_size_raises():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("abc", size=100, overlap=100)
