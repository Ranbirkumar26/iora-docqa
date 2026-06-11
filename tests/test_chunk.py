"""Chunking tests. Pure Python, no API keys."""
from app.rag.chunk import chunk_text, chunk_by_lines, chunk_xlsx, chunk_for_type


def test_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_single_chunk():
    assert chunk_text("hello", size=100, overlap=10) == ["hello"]


def test_splits_long_text():
    text = "a" * 1000
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_overlap_present():
    text = "0123456789" * 30  # 300 chars
    chunks = chunk_text(text, size=100, overlap=20)
    assert chunks[0][-20:] == chunks[1][:20]


def test_covers_whole_text():
    text = "x" * 500 + "END"
    chunks = chunk_text(text, size=100, overlap=10)
    assert chunks[-1].endswith("END")


def test_overlap_ge_size_raises():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("abc", size=100, overlap=100)


# ---- adaptive chunking ----
def test_chunk_by_lines_never_splits_a_line():
    rows = "\n".join(f"name: person{i} | age: {i}" for i in range(200))
    chunks = chunk_by_lines(rows, size=300)
    assert len(chunks) > 1
    # every line in every chunk is a complete original row
    for c in chunks:
        for ln in c.split("\n"):
            assert ln.startswith("name: person")
            assert "age:" in ln


def test_chunk_xlsx_tags_every_chunk_with_sheet():
    text = "[Sheet: A]\n" + "\n".join(f"x: {i}" for i in range(100))
    text += "\n[Sheet: B]\n" + "\n".join(f"y: {i}" for i in range(100))
    chunks = chunk_xlsx(text, size=200)
    assert all(c.startswith("[Sheet:") for c in chunks)
    assert any(c.startswith("[Sheet: A]") for c in chunks)
    assert any(c.startswith("[Sheet: B]") for c in chunks)


def test_chunk_for_type_dispatch():
    assert chunk_for_type("", "csv") == []
    assert chunk_for_type("a: 1\nb: 2", "csv")  # nonempty
    txt = "word " * 1000
    assert len(chunk_for_type(txt, "txt", size=300, overlap=50)) > 1
