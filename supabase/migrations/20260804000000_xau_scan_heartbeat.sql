-- XAU scalper heartbeat: one row per scan, written at the end of each run.
-- Mirrors engine_runs/engine_status (20260722000100) but for signals/xau_scan.py.
-- Used by the /admin XAU Scalper tile and the /api/cron/xau-watchdog route to
-- detect a dead scalper loop and restart it via repository_dispatch.
create table if not exists public.xau_scan_runs (
    id uuid primary key,
    run_id text not null,
    signal_found boolean not null default false,
    finished_at timestamptz not null
);

create index if not exists xau_scan_runs_finished_at_idx
    on public.xau_scan_runs (finished_at desc);

alter table public.xau_scan_runs enable row level security;

-- Derived scalper status (computed using DB time, so the UI stays pure).
-- security_invoker=on: run as the querying role so RLS still applies
-- (service role only; anon/authenticated see nothing).
-- 3-minute threshold vs engine_status's 15: the scalper heartbeats every
-- ~60s, so 3 minutes is ~3x its normal cadence before it's flagged stale.
drop view if exists public.xau_scan_status;
create view public.xau_scan_status
with (security_invoker = on)
as
select
    r.id,
    r.run_id,
    r.signal_found,
    r.finished_at,
    (r.finished_at > now() - interval '3 minutes') as is_healthy,
    floor(extract(epoch from (now() - r.finished_at)) / 60)::int as age_minutes
from public.xau_scan_runs r
order by r.finished_at desc
limit 1;
