"""Structured path: safety + SQL execution (no API key — pure DuckDB/regex)."""
import pandas as pd

from app.core.structured import _is_safe, looks_quantitative, run_sql


def test_looks_quantitative():
    assert looks_quantitative("which region had the most revenue?")
    assert looks_quantitative("what is the average NPS score?")
    assert looks_quantitative("how many units sold?")
    assert not looks_quantitative("summarize the customer interview")
    assert not looks_quantitative("what did Meera say about safety?")


def test_is_safe_accepts_select():
    assert _is_safe("SELECT region, sum(rev) FROM t GROUP BY region")
    assert _is_safe("WITH x AS (SELECT 1) SELECT * FROM x")


def test_is_safe_rejects_dangerous():
    assert not _is_safe("DROP TABLE t")
    assert not _is_safe("SELECT * FROM t; DELETE FROM t")  # multi-statement
    assert not _is_safe("INSERT INTO t VALUES (1)")
    assert not _is_safe("SELECT * FROM read_csv('/etc/passwd')")  # file access
    assert not _is_safe("ATTACH 'x.db'")


def test_run_sql_computes_exact():
    # A = 10 + 30 = 40, B = 50  -> B is the top region
    df = pd.DataFrame({"region": ["A", "B", "A"], "rev": [10, 50, 30]})
    tables = [("sales", df, "sales.csv")]
    out = run_sql(
        tables,
        "SELECT region, sum(rev) AS total FROM sales GROUP BY region ORDER BY total DESC",
    )
    assert list(out.iloc[0]) == ["B", 50]
    assert list(out.iloc[1]) == ["A", 40]


def test_run_sql_external_access_blocked():
    import pytest

    df = pd.DataFrame({"a": [1]})
    with pytest.raises(Exception):
        # external file access is disabled on the connection
        run_sql([("t", df, "t.csv")], "SELECT * FROM read_csv_auto('/etc/hosts')")
