-- Engine run heartbeat: one row per run, written at the end of each scan.
-- Used by /admin to show if the engine is alive.
create table if not exists public.engine_runs (
    id uuid primary key,
    run_id text not null,
    timeframe text not null,
    stored_count integer not null default 0 check (stored_count >= 0),
    outcomes jsonb not null default '[]'::jsonb,
    finished_at timestamptz not null
);

create index if not exists engine_runs_finished_at_idx
    on public.engine_runs (finished_at desc);

alter table public.engine_runs enable row level security;

-- Derived engine status (computed using DB time, so the UI stays pure).
-- security_invoker=on: run as the querying role so engine_runs RLS still
-- applies (service role only; anon/authenticated see nothing). Without this,
-- Postgres defaults to SECURITY DEFINER and Supabase Security Advisor errors.
drop view if exists public.engine_status;
create view public.engine_status
with (security_invoker = on)
as
select
    r.id,
    r.run_id,
    r.timeframe,
    r.stored_count,
    r.finished_at,
    (r.finished_at > now() - interval '15 minutes') as is_healthy,
    floor(extract(epoch from (now() - r.finished_at)) / 60)::int as age_minutes
from public.engine_runs r
order by r.finished_at desc
limit 1;

-- Single-row lock so overlapping cron/GitHub triggers cannot run together.
-- A holder older than 12 minutes is considered stale and can be stolen.
create table if not exists public.engine_lock (
    id integer primary key check (id = 1),
    holder text,
    acquired_at timestamptz
);

alter table public.engine_lock enable row level security;

insert into public.engine_lock (id, holder, acquired_at)
values (1, null, null)
on conflict (id) do nothing;
