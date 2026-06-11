-- DocQA schema. Run in Supabase SQL editor.
-- Requires pgvector. Gemini text-embedding-004 -> 768 dims.

create extension if not exists vector;

-- one row per uploaded file
create table if not exists files (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references auth.users(id) on delete cascade,
    filename     text not null,
    file_type    text not null,                 -- 'txt' | 'csv' | 'xlsx'
    storage_path text not null,                  -- path in storage bucket
    char_count   integer not null default 0,
    indexed      boolean not null default false, -- embedded into chunks yet?
    upload_date  timestamptz not null default now()
);

-- one row per text chunk (RAG path)
create table if not exists document_chunks (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    file_id     uuid not null references files(id) on delete cascade,
    filename    text not null,
    sheet_name  text,
    chunk_index integer not null,
    content     text not null,
    embedding   vector(768),
    created_at  timestamptz not null default now()
);

create index if not exists idx_files_user on files(user_id);
create index if not exists idx_chunks_user on document_chunks(user_id);
create index if not exists idx_chunks_file on document_chunks(file_id);

-- approximate-nearest-neighbour index for similarity search
create index if not exists idx_chunks_embedding on document_chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ===== Row Level Security: a user touches only their own rows =====
alter table files enable row level security;
alter table document_chunks enable row level security;

drop policy if exists files_owner on files;
create policy files_owner on files
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists chunks_owner on document_chunks;
create policy chunks_owner on document_chunks
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ===== Vector search RPC: top-k chunks for a user =====
-- Called from backend. SECURITY DEFINER so it runs the ivfflat scan,
-- but we still pass user_id explicitly and filter on it.
create or replace function match_chunks(
    p_user_id     uuid,
    query_embedding vector(768),
    match_count   int default 15
)
returns table (
    content    text,
    filename   text,
    similarity float
)
language sql stable
as $$
    select
        c.content,
        c.filename,
        1 - (c.embedding <=> query_embedding) as similarity
    from document_chunks c
    where c.user_id = p_user_id
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
