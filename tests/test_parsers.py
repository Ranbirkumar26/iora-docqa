"""Parser tests. Pure Python, no API keys needed."""
import io

import pandas as pd
import pytest

from app.parsers.parse import parse_file, parse_txt, parse_csv, parse_xlsx


def test_txt():
    assert parse_txt(b"hello world") == "hello world"


def test_txt_bad_bytes_no_crash():
    # invalid utf-8 should not raise
    out = parse_txt(b"\xff\xfe abc")
    assert "abc" in out


def test_csv_rows_and_headers():
    csv = b"name,age\nAlice,30\nBob,25"
    out = parse_csv(csv)
    assert "name: Alice | age: 30" in out
    assert "name: Bob | age: 25" in out


def test_csv_empty():
    assert parse_csv(b"") == ""


def test_xlsx_multi_sheet():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"x": [1], "y": [2]}).to_excel(w, sheet_name="S1", index=False)
        pd.DataFrame({"a": ["foo"]}).to_excel(w, sheet_name="S2", index=False)
    out = parse_xlsx(buf.getvalue())
    assert "[Sheet: S1]" in out
    assert "[Sheet: S2]" in out
    assert "x: 1 | y: 2" in out
    assert "a: foo" in out


def test_dispatch_by_extension():
    assert parse_file("notes.txt", b"hi") == "hi"


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        parse_file("doc.pdf", b"%PDF")
