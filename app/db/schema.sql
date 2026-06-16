-- DocQA schema. Run in Supabase SQL editor.
-- Requires pgvector. Gemini gemini-embedding-001 -> 768 dims.

create extension if not exists vector;

-- ===== Organisations: multi-tenant workspace boundary =====
create table if not exists organizations (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    created_by  uuid references auth.users(id) on delete set null,
    created_at  timestamptz not null default now()
);

create table if not exists organization_members (
    organization_id uuid not null references organizations(id) on delete cascade,
    user_id         uuid not null references auth.users(id) on delete cascade,
    role            text not null default 'user'
                    check (role in ('user', 'author', 'admin')),
    created_at      timestamptz not null default now(),
    primary key (organization_id, user_id)
);

-- Normalize older role names into the current access modes:
-- user = own workspace, author = organisation-wide read-only, admin = full access.
alter table organization_members drop constraint if exists organization_members_role_check;
update organization_members set role = 'admin' where role in ('owner', 'admin');
update organization_members set role = 'user' where role in ('member', 'user') or role is null;
alter table organization_members alter column role set default 'user';
alter table organization_members
    add constraint organization_members_role_check
    check (role in ('user', 'author', 'admin'));

-- one row per uploaded file
create table if not exists files (
    id           uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    user_id      uuid not null references auth.users(id) on delete cascade,
    filename     text not null,
    file_type    text not null,                 -- 'txt' | 'csv' | 'xlsx' | 'pdf' | 'docx'
    storage_path text not null,                  -- path in storage bucket
    char_count   integer not null default 0,
    parsed_text  text,                            -- extracted text (direct mode reads this)
    content_hash text,                            -- sha256 of raw bytes (dedup / re-index)
    indexed      boolean not null default false, -- embedded into chunks yet?
    upload_date  timestamptz not null default now()
);

alter table files
    add column if not exists organization_id uuid references organizations(id) on delete cascade;

-- one row per text chunk (RAG path)
create table if not exists document_chunks (
    id          uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    user_id     uuid not null references auth.users(id) on delete cascade,
    file_id     uuid not null references files(id) on delete cascade,
    filename    text not null,
    sheet_name  text,
    chunk_index integer not null,
    content     text not null,
    embedding   vector(768),
    created_at  timestamptz not null default now()
);

alter table document_chunks
    add column if not exists organization_id uuid references organizations(id) on delete cascade;

-- saved generated reports: organisation knowledge repository
create table if not exists reports (
    id                    uuid primary key default gen_random_uuid(),
    organization_id       uuid not null references organizations(id) on delete cascade,
    user_id               uuid references auth.users(id) on delete set null,
    title                 text not null default 'Corpus report',
    report                text not null,
    structured_analysis   text,
    qualitative_analysis  text,
    sources               jsonb not null default '[]'::jsonb,
    mode                  text not null default 'direct',
    created_at            timestamptz not null default now()
);

-- durable ask/answer transcript per user/session scope
create table if not exists conversation_messages (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    user_id          uuid not null references auth.users(id) on delete cascade,
    role             text not null check (role in ('user', 'assistant', 'system')),
    content          text not null,
    mode             text,
    sources          jsonb not null default '[]'::jsonb,
    metadata         jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now()
);

-- generated artifacts: summaries, reports, transcripts, extractions, exports
create table if not exists generated_outputs (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    user_id          uuid not null references auth.users(id) on delete cascade,
    file_id          uuid references files(id) on delete set null,
    kind             text not null,
    title            text not null,
    content          text not null,
    format           text not null default 'markdown',
    sources          jsonb not null default '[]'::jsonb,
    metadata         jsonb not null default '{}'::jsonb,
    storage_path     text,
    created_at       timestamptz not null default now()
);

-- sync job records now; future background workers can update these rows async
create table if not exists processing_jobs (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    user_id          uuid references auth.users(id) on delete set null,
    kind             text not null,
    status           text not null default 'queued'
                     check (status in ('queued', 'running', 'completed', 'failed')),
    detail           text,
    metadata         jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

-- per-user memory facts
create table if not exists memories (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    content     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_files_user on files(user_id);
create index if not exists idx_org_members_user_role on organization_members(user_id, role);
create index if not exists idx_files_user_hash on files(user_id, content_hash);
create index if not exists idx_files_org on files(organization_id);
create index if not exists idx_files_org_hash on files(organization_id, content_hash);
create index if not exists idx_chunks_user on document_chunks(user_id);
create index if not exists idx_chunks_org on document_chunks(organization_id);
create index if not exists idx_chunks_file on document_chunks(file_id);
create index if not exists idx_reports_org_created on reports(organization_id, created_at desc);
create index if not exists idx_jobs_org_created on processing_jobs(organization_id, created_at desc);
create index if not exists idx_conversation_org_created on conversation_messages(organization_id, created_at desc);
create index if not exists idx_conversation_user_created on conversation_messages(user_id, created_at desc);
create index if not exists idx_outputs_org_kind_created on generated_outputs(organization_id, kind, created_at desc);
create index if not exists idx_outputs_user_kind_created on generated_outputs(user_id, kind, created_at desc);
create index if not exists idx_outputs_file_kind on generated_outputs(file_id, kind);

-- Backfill existing users/rows when this schema is applied to an older project.
insert into organizations (name, created_by)
select
    coalesce(nullif(split_part(u.email, '@', 1), ''), 'Personal') || '''s workspace',
    u.id
from auth.users u
where not exists (
    select 1 from organization_members om where om.user_id = u.id
);

insert into organization_members (organization_id, user_id, role)
select o.id, o.created_by, 'admin'
from organizations o
where o.created_by is not null
  and not exists (
      select 1 from organization_members om
      where om.organization_id = o.id and om.user_id = o.created_by
  );

update files f
set organization_id = om.organization_id
from organization_members om
where f.organization_id is null and f.user_id = om.user_id;

update document_chunks c
set organization_id = f.organization_id
from files f
where c.organization_id is null and c.file_id = f.id;

update conversation_messages cm
set organization_id = om.organization_id
from organization_members om
where cm.organization_id is null and cm.user_id = om.user_id;

update generated_outputs go
set organization_id = om.organization_id
from organization_members om
where go.organization_id is null and go.user_id = om.user_id;

-- approximate-nearest-neighbour index for similarity search
create index if not exists idx_chunks_embedding on document_chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ===== Row Level Security: role-aware org access =====
alter table organizations enable row level security;
alter table organization_members enable row level security;
alter table files enable row level security;
alter table document_chunks enable row level security;
alter table reports enable row level security;
alter table conversation_messages enable row level security;
alter table generated_outputs enable row level security;
alter table processing_jobs enable row level security;
alter table memories enable row level security;

drop policy if exists orgs_member_select on organizations;
create policy orgs_member_select on organizations
    for select
    using (
        id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
        )
    );

drop policy if exists org_members_same_org on organization_members;
create policy org_members_same_org on organization_members
    for select
    to authenticated
    using (user_id = (select auth.uid()));

drop policy if exists files_owner on files;
drop policy if exists files_select_role on files;
drop policy if exists files_insert_role on files;
drop policy if exists files_update_role on files;
drop policy if exists files_delete_role on files;
create policy files_select_role on files
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy files_insert_role on files
    for insert
    to authenticated
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy files_update_role on files
    for update
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy files_delete_role on files
    for delete
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists chunks_owner on document_chunks;
drop policy if exists chunks_select_role on document_chunks;
drop policy if exists chunks_insert_role on document_chunks;
drop policy if exists chunks_update_role on document_chunks;
drop policy if exists chunks_delete_role on document_chunks;
create policy chunks_select_role on document_chunks
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy chunks_insert_role on document_chunks
    for insert
    to authenticated
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy chunks_update_role on document_chunks
    for update
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy chunks_delete_role on document_chunks
    for delete
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists reports_member on reports;
drop policy if exists reports_select_role on reports;
drop policy if exists reports_insert_admin on reports;
drop policy if exists reports_update_admin on reports;
drop policy if exists reports_delete_admin on reports;
create policy reports_select_role on reports
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy reports_insert_admin on reports
    for insert
    to authenticated
    with check (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy reports_update_admin on reports
    for update
    to authenticated
    using (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy reports_delete_admin on reports
    for delete
    to authenticated
    using (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists conversation_owner on conversation_messages;
drop policy if exists conversation_select_role on conversation_messages;
drop policy if exists conversation_insert_role on conversation_messages;
drop policy if exists conversation_update_role on conversation_messages;
drop policy if exists conversation_delete_role on conversation_messages;
create policy conversation_select_role on conversation_messages
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy conversation_insert_role on conversation_messages
    for insert
    to authenticated
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy conversation_update_role on conversation_messages
    for update
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy conversation_delete_role on conversation_messages
    for delete
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists outputs_owner on generated_outputs;
drop policy if exists outputs_select_role on generated_outputs;
drop policy if exists outputs_insert_role on generated_outputs;
drop policy if exists outputs_update_role on generated_outputs;
drop policy if exists outputs_delete_role on generated_outputs;
create policy outputs_select_role on generated_outputs
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy outputs_insert_role on generated_outputs
    for insert
    to authenticated
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy outputs_update_role on generated_outputs
    for update
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy outputs_delete_role on generated_outputs
    for delete
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists jobs_member on processing_jobs;
drop policy if exists jobs_select_role on processing_jobs;
drop policy if exists jobs_insert_admin on processing_jobs;
drop policy if exists jobs_update_admin on processing_jobs;
drop policy if exists jobs_delete_admin on processing_jobs;
create policy jobs_select_role on processing_jobs
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role in ('author', 'admin')
        )
    );
create policy jobs_insert_admin on processing_jobs
    for insert
    to authenticated
    with check (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy jobs_update_admin on processing_jobs
    for update
    to authenticated
    using (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    )
    with check (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );
create policy jobs_delete_admin on processing_jobs
    for delete
    to authenticated
    using (
        organization_id in (
            select organization_id from organization_members
            where user_id = (select auth.uid())
              and role = 'admin'
        )
    );

drop policy if exists memories_owner on memories;
create policy memories_owner on memories
    for all
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

-- ===== Vector search RPC: top-k chunks for a user =====
-- Called from backend. Filters by organisation_id first, with user_id fallback
-- for legacy rows not yet backfilled with organisation_id.
create or replace function match_chunks(
    p_organization_id uuid,
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
    where c.organization_id = p_organization_id
       or (c.organization_id is null and c.user_id = p_user_id)
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
