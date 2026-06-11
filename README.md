# DocQA

Upload txt/csv/xlsx files, ask questions and get summaries grounded in your documents.
Files persist per user and accumulate into one queryable corpus across sessions.

## How it works

- **Small corpus** (< ~150k tokens) → all text stuffed into Claude's context. Max accuracy.
- **Large corpus** (≥ 150k tokens) → RAG: chunk → embed (Voyage) → pgvector search → answer.
- Auto-switches based on total corpus size. No user action.

## Stack

FastAPI · Streamlit · Supabase (auth + storage + Postgres + pgvector) · Voyage embeddings · Claude

## Setup

1. Fill `.env` (copy from `.env.template`). Needs `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
   `SUPABASE_SERVICE_KEY` (URL + anon key already filled).
2. Schema + storage bucket already provisioned in Supabase.
3. Install: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`

## Run

```bash
# terminal 1 — API
.venv/bin/uvicorn app.api.main:app --reload

# terminal 2 — UI
.venv/bin/streamlit run frontend/app.py
```

Open the Streamlit URL → Sign up → Log in → upload files → ask / summarize.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## Layout

```
app/
  config.py          settings + thresholds
  parsers/parse.py   txt/csv/xlsx -> text
  rag/chunk.py       overlap chunking
  rag/embed.py       Voyage embeddings
  llm/claude.py      Claude wrapper
  db/client.py       Supabase clients
  db/schema.sql      tables + pgvector + RLS + match_chunks RPC
  core/corpus.py     size/mode stats + full-text fetch
  core/ingest.py     upload pipeline
  core/qa.py         direct + RAG question answering
  core/summarize.py  direct + RAG summarization
  api/main.py        FastAPI endpoints
frontend/app.py      Streamlit UI
```

## Notes / future work

- Indexing is inline on upload. For very large batches, move to a background worker.
- PDF/Word/image support not included (v1 scope).
