-- AI War Room: a stored 3-agent debate transcript per confirmed signal, read
-- by the public /war-room showcase page. Does not gate real signals.
create table if not exists public.agent_debates (
    id uuid primary key,
    signal_id uuid null,
    symbol text not null,
    timeframe text not null,
    direction text not null check (direction in ('long', 'short')),
    transcript jsonb not null,
    manager_verdict text not null,
    manager_confidence integer not null default 0
        check (manager_confidence between 0 and 100),
    created_at timestamptz not null
);

create index if not exists agent_debates_created_at_idx
    on public.agent_debates (created_at desc);

alter table public.agent_debates enable row level security;
drop policy if exists "public read debates" on public.agent_debates;
create policy "public read debates"
    on public.agent_debates for select
    using (true);
