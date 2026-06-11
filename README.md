# iORA DocQA

**Live: https://docqa-production.up.railway.app**

Upload txt/csv/xlsx files, ask questions and get summaries grounded in your documents.
Files persist per user and accumulate into one queryable corpus across sessions.
Responsive web app: works on desktop and mobile browsers, light/dark theme.

## How it answers

Three query paths, picked automatically per question:

- **Direct** (corpus < ~150k tokens): all text stuffed into the model context. Max accuracy.
- **RAG** (larger corpus): chunk -> embed (Gemini) -> pgvector search -> answer from top passages.
- **Structured** (quantitative questions over csv/xlsx): the model writes SQL, DuckDB executes
  it on the real table, the model phrases the exact result. No LLM arithmetic.

Answers cite source filenames; the structured path also exposes the SQL it ran.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 + React 19 + Tailwind v4, static export, light/dark theme |
| Backend | FastAPI (serves the SPA at `/` and the API under `/api`) |
| Auth, storage, DB | Supabase (Postgres + pgvector + Storage + Auth, RLS) |
| LLM + embeddings | Gemini `gemini-2.5-flash-lite` + `gemini-embedding-001` (768d) |
| Tabular queries | DuckDB (SELECT-only, external access disabled) |
| Hosting | Railway, single Docker container |

## Setup

1. Copy `.env.template` to `.env` and fill: `GEMINI_API_KEY`, `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`.
2. Apply `app/db/schema.sql` in the Supabase SQL editor; create a private storage
   bucket named `user-documents`.
3. Backend deps: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`
4. Frontend deps: `cd web && npm install`

## Run locally

```bash
# build the SPA once (FastAPI serves web/out)
cd web && npm run build && cd ..

# serve app + API on :8000
.venv/bin/uvicorn app.api.main:app --reload
# open http://localhost:8000
```

Frontend development with hot reload (proxies /api to :8000):

```bash
cd web && npm run dev   # http://localhost:3000
```

A legacy Streamlit UI remains in `frontend/app.py` for quick local poking:
`.venv/bin/streamlit run frontend/app.py`.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## Deploy

Single container: Streamlit-free, FastAPI serves SPA + API on `$PORT`.

- **Railway** (current): `railway up` from the repo root (project already linked).
  Set the 4 env vars as service variables.
- **Render**: push to GitHub, New -> Blueprint (reads `render.yaml`), set the 4 secrets.
- **Local Docker**:
  ```bash
  docker build -t docqa .
  docker run --env-file .env -p 8600:8000 docqa   # http://localhost:8600
  ```

## Layout

```
app/
  config.py          settings, provider switches, thresholds
  parsers/parse.py   txt/csv/xlsx -> text
  rag/chunk.py       structure-aware chunking (rows for csv, per-sheet for xlsx)
  rag/embed.py       Gemini/Voyage embeddings (cached query embeds)
  llm/               gemini.py, claude.py, provider.py (env-switchable)
  core/
    ingest.py        upload pipeline: parse -> store -> hash dedup -> chunk -> embed
    corpus.py        corpus stats + mode detection + full-text fetch
    qa.py            ask(): direct / rag / structured routing
    structured.py    DuckDB SQL path for quantitative questions
    summarize.py     per-file + overall summaries (map-reduce in RAG mode)
  db/                supabase clients, schema.sql
  api/main.py        FastAPI: /api routes + static SPA mount
web/                 Next.js app (components, theme tokens, iORA branding)
frontend/app.py      legacy Streamlit UI (local dev only)
tests/               parser, chunking, structured-SQL safety tests
```

## Notes

- Same filename re-uploaded with new content replaces the old version; identical
  content is skipped (sha256 dedup).
- Gemini free tier: 20 requests/min; the API returns a clean 429 when exceeded.
- Railway free tier sleeps when idle; first request after a pause cold-starts.
