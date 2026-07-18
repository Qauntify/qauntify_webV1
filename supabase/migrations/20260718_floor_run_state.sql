-- Durable run state for the trading floor's Gold AI hunter.
-- Single source of truth for whether the hunter is enabled, whether a
-- cycle is currently executing, and the latest cycle/phase/message/signal
-- — replaces module-level in-memory state, which Vercel's serverless
-- model doesn't guarantee survives past a single response.
create table if not exists public.floor_run_state (
    id int primary key default 1,
    enabled boolean not null default false,
    in_progress boolean not null default false,
    run_id text,
    cycle int not null default 0,
    phase text not null default 'idle',
    last_message text not null default '',
    last_signal jsonb,
    updated_at timestamptz not null default now(),
    constraint floor_run_state_singleton check (id = 1)
);

insert into public.floor_run_state (id) values (1)
    on conflict (id) do nothing;

alter table public.floor_run_state enable row level security;

drop policy if exists "members read floor run state" on public.floor_run_state;
create policy "members read floor run state"
    on public.floor_run_state for select
    to authenticated
    using (true);
