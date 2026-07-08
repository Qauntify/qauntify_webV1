-- Qauntify signals table.
-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor → New query).

create table if not exists public.signals (
    id uuid primary key,
    symbol text not null,
    timeframe text not null,
    direction text not null check (direction in ('long', 'short')),
    entry double precision not null,
    stop_loss double precision not null,
    take_profit double precision not null,
    confidence integer not null check (confidence between 0 and 100),
    rationale text not null,
    indicators jsonb not null,
    news_headlines jsonb not null,
    created_at timestamptz not null
);

create index if not exists signals_created_at_idx
    on public.signals (created_at desc);

-- Outcome tracking: signals stay in the table forever; the engine flips
-- status to tp_hit/sl_hit when price reaches the target or the stop, or to
-- expired when a signal stays open past the engine's MAX_OPEN_DAYS window.
alter table public.signals
    add column if not exists status text not null default 'open'
        check (status in ('open', 'tp_hit', 'sl_hit'));
alter table public.signals
    add column if not exists closed_at timestamptz;

-- Existing installs: widen the status check to allow 'expired'.
alter table public.signals drop constraint if exists signals_status_check;
alter table public.signals add constraint signals_status_check
    check (status in ('open', 'tp_hit', 'sl_hit', 'expired'));

create index if not exists signals_status_idx
    on public.signals (status)
    where status = 'open';

-- Freemium gate, enforced at the database:
--   anon (logged out)        → only signals from the last 24 hours (preview)
--   authenticated (signed in) → full history
-- Writes only via the service-role key (which bypasses RLS).
alter table public.signals enable row level security;

drop policy if exists "public read access" on public.signals;

drop policy if exists "anon preview access" on public.signals;
create policy "anon preview access"
    on public.signals for select
    to anon
    using (created_at > now() - interval '24 hours');

drop policy if exists "member full access" on public.signals;
create policy "member full access"
    on public.signals for select
    to authenticated
    using (true);

-- Bot settings: one row, read by the engine at the start of each run and
-- edited from /admin. RLS is enabled with NO policies on purpose — only the
-- service-role key (engine + admin page) can read or write it.
create table if not exists public.bot_settings (
    id integer primary key check (id = 1),
    symbols jsonb not null default '["BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT"]',
    min_alert_confidence integer not null
        default 0 check (min_alert_confidence between 0 and 100),
    signal_strategy text not null default 'ema_cross'
        check (signal_strategy in ('ema_cross', 'ict_smc')),
    updated_at timestamptz not null default now()
);

-- Existing installs: add strategy column without recreating the table.
alter table public.bot_settings
    add column if not exists signal_strategy text not null default 'ema_cross';

alter table public.bot_settings enable row level security;

insert into public.bot_settings (id) values (1)
    on conflict (id) do nothing;

-- Keep existing installs aligned with the four live markets.
update public.bot_settings
set
    symbols = '["BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT"]'::jsonb,
    updated_at = now()
where id = 1;

-- AI event log: stores all SEA-LION responses (confirm/reject/no-setup explanations)
-- for audit + admin dashboard visibility. RLS enabled with no policies so only
-- the service-role key can read/write.
create table if not exists public.ai_events (
    id uuid primary key,
    symbol text not null,
    timeframe text not null,
    kind text not null check (kind in ('confirm', 'reject', 'no_setup')),
    direction text null check (direction in ('long', 'short')),
    entry double precision null,
    stop_loss double precision null,
    take_profit double precision null,
    confidence integer null check (confidence between 0 and 100),
    rationale text not null,
    indicators jsonb not null,
    news_headlines jsonb not null default '[]'::jsonb,
    created_at timestamptz not null
);

create index if not exists ai_events_created_at_idx
    on public.ai_events (created_at desc);

create index if not exists ai_events_symbol_created_at_idx
    on public.ai_events (symbol, created_at desc);

alter table public.ai_events enable row level security;

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
create or replace view public.engine_status as
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
