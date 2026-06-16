"""Generated-output helpers. Pure Python, no API keys."""
from app.core.outputs import build_extraction_artifact


def test_extraction_artifact_turns_field_rows_into_workbook():
    markdown, workbook, row_count = build_extraction_artifact(
        "waitlist.csv",
        "name: Alice | email: alice@example.com | segment: beta\n"
        "name: Bob | email: bob@example.com | segment: founder",
    )

    assert row_count == 2
    assert "Alice" in markdown
    assert "segment" in markdown
    assert workbook.startswith(b"PK")


def test_extraction_artifact_falls_back_to_entities():
    markdown, workbook, row_count = build_extraction_artifact(
        "notes.txt",
        "Please contact ranbir@example.com or visit https://example.com.",
    )

    assert row_count == 2
    assert "email" in markdown
    assert "url" in markdown
    assert workbook.startswith(b"PK")
