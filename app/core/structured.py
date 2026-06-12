"""Structured-data query path.

For quantitative questions over tabular files (csv/xlsx), the LLM writes a
DuckDB SQL SELECT; DuckDB executes it on the real DataFrame. The number comes
from the query (exact, repeatable) — the LLM only phrases the verified result.
This fixes LLM-eyeballing-a-big-table inconsistency for aggregations.
"""
import io
import re

import duckdb
import pandas as pd

from app.config import STORAGE_BUCKET
from app.db.client import service_client
from app.llm.provider import complete

TABULAR = ("csv", "xlsx")

# question intent gate — only attempt SQL when it looks quantitative
_QUANT = re.compile(
    r"\b(how many|how much|count|number of|total|sum|average|avg|mean|median|"
    r"max(imum)?|min(imum)?|most|least|highest|lowest|top|bottom|per\b|by\b|"
    r"rate|percent|%|compare|trend|more than|less than|greater|fewer|rank)\b",
    re.I,
)

# block anything that is not a read-only query / touches the filesystem
_FORBIDDEN = re.compile(
    r"\b(attach|copy|install|load|pragma|create|insert|update|delete|drop|alter|"
    r"read_csv|read_parquet|read_json|read_text|glob|sniff_csv)\b",
    re.I,
)


def looks_quantitative(question: str) -> bool:
    return bool(_QUANT.search(question))


def _safe_name(s: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s or "t"


def _uniq(base: str, used: set) -> str:
    name, i = base, 1
    while name in used:
        i += 1
        name = f"{base}_{i}"
    used.add(name)
    return name


def _scope_column(use_org: bool) -> str:
    return "organization_id" if use_org else "user_id"


def load_tables(scope_id: str, use_org: bool = True):
    """Load the user's csv/xlsx files into DuckDB-ready DataFrames.

    Returns list of (table_name, DataFrame, source_filename).
    """
    sb = service_client()
    files = (
        sb.table("files")
        .select("filename, file_type, storage_path")
        .eq(_scope_column(use_org), scope_id)
        .in_("file_type", list(TABULAR))
        .execute()
        .data
        or []
    )
    tables, used = [], set()
    for f in files:
        raw = sb.storage.from_(STORAGE_BUCKET).download(f["storage_path"])
        base = _safe_name(f["filename"].rsplit(".", 1)[0])
        if f["file_type"] == "csv":
            try:
                df = pd.read_csv(io.BytesIO(raw))
            except Exception:
                continue
            tables.append((_uniq(base, used), df, f["filename"]))
        else:  # xlsx
            try:
                xl = pd.ExcelFile(io.BytesIO(raw))
            except Exception:
                continue
            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                if df.empty:
                    continue
                nm = _uniq(f"{base}_{_safe_name(sheet)}", used)
                tables.append((nm, df, f["filename"]))
    return tables


def schema_text(tables) -> str:
    parts = []
    for name, df, _ in tables:
        cols = ", ".join(f'"{c}" ({df[c].dtype})' for c in df.columns)
        sample = df.head(3).to_dict("records")
        parts.append(f"Table {name}\n  columns: {cols}\n  sample: {sample}")
    return "\n".join(parts)


_SQL_SYS = (
    "You translate a question into a SINGLE DuckDB SQL SELECT over the given tables.\n"
    "Rules:\n"
    "- Use only the listed table and column names.\n"
    "- Quote column names that contain spaces or special characters in double quotes.\n"
    "- Return ONLY the SQL — no markdown fences, no explanation.\n"
    "- If the question cannot be answered from these tables with SQL (free text, "
    "opinions, or data not present), return exactly: NONE"
)


def generate_sql(question: str, schema: str) -> str:
    # temperature=0 -> deterministic SQL so the structured path engages reliably
    out = complete(
        _SQL_SYS,
        f"Tables:\n{schema}\n\nQuestion: {question}\n\nSQL:",
        max_tokens=400,
        temperature=0,
    )
    out = out.strip()
    out = re.sub(r"^```sql\b|^```|```$", "", out, flags=re.I | re.M).strip()
    return out


def _is_safe(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if ";" in s:  # single statement only
        return False
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        return False
    if _FORBIDDEN.search(s):
        return False
    return True


def run_sql(tables, sql: str) -> pd.DataFrame:
    con = duckdb.connect(":memory:")
    con.execute("SET enable_external_access=false;")  # no file/network access
    for name, df, _ in tables:
        con.register(name, df)
    return con.execute(sql).fetchdf().head(100)


_ANSWER_SYS = (
    "You are a data analyst. Given a question and the EXACT result of a SQL query "
    "over the user's data, answer in one or two clear sentences. The result is "
    "authoritative — do not recompute or second-guess the numbers. Cite the figures."
)


def answer_structured(scope_id: str, question: str, use_org: bool = True):
    """Try to answer via SQL. Returns dict or None (falls back to text path)."""
    tables = load_tables(scope_id, use_org)
    if not tables:
        return None

    sql = generate_sql(question, schema_text(tables))
    if not sql or sql.upper().startswith("NONE") or not _is_safe(sql):
        return None

    try:
        res = run_sql(tables, sql)
    except Exception:
        return None
    if res.empty:
        return None

    result_str = res.to_string(index=False)[:4000]
    answer = complete(
        _ANSWER_SYS,
        f"Question: {question}\n\nSQL:\n{sql}\n\nResult:\n{result_str}",
        temperature=0,
    )
    return {
        "answer": answer,
        "mode": "structured",
        "sources": sorted({fn for _, _, fn in tables}),
        "sql": sql,
    }
