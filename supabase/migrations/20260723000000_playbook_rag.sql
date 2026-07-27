-- Hybrid RAG playbook: strategy rule chunks with SEA-LION embeddings (1024-d).
-- Local keyword fallback still works if vector/rpc is missing.
create extension if not exists vector;

create table if not exists public.playbook_chunks (
    id uuid primary key,
    strategy text not null,
    title text not null,
    body text not null,
    embedding vector(1024),
    updated_at timestamptz not null default now()
);

create index if not exists playbook_chunks_strategy_idx
    on public.playbook_chunks (strategy);

alter table public.playbook_chunks enable row level security;

create or replace function public.match_playbook_chunks(
    query_embedding vector(1024),
    match_strategy text,
    match_count integer default 2
)
returns table (
    id uuid,
    strategy text,
    title text,
    body text,
    similarity double precision
)
language sql
stable
as $$
    select
        c.id,
        c.strategy,
        c.title,
        c.body,
        (1 - (c.embedding <=> query_embedding))::double precision as similarity
    from public.playbook_chunks c
    where c.strategy = match_strategy
      and c.embedding is not null
    order by c.embedding <=> query_embedding
    limit greatest(match_count, 1);
$$;
