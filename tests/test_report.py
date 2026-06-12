"""Report analysis helpers. Pure Python, no API keys."""
import pandas as pd

from app.core.report import _table_stats


def test_table_stats_summarizes_numeric_and_categorical_columns():
    df = pd.DataFrame(
        {
            "region": ["North", "South", "North"],
            "revenue": [100, 250, 150],
            "score": [4.0, 3.0, 5.0],
        }
    )

    out = _table_stats([("sales", df, "sales.csv")])

    assert "sales.csv" in out
    assert "Rows: 3" in out
    assert "revenue: avg 166.67" in out
    assert "score: avg 4" in out
    assert "region: North (2), South (1)" in out


def test_table_stats_handles_no_tables():
    assert _table_stats([]) == "No tabular files found."
