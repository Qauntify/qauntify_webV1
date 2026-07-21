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
    take_profit_1 double precision,
    take_profit_2 double precision,
    take_profit_3 double precision,
    confidence integer not null check (confidence between 0 and 100),
    rationale text not null,
    indicators jsonb not null,
    news_headlines jsonb not null,
    created_at timestamptz not null
);

create index if not exists signals_created_at_idx
    on public.signals (created_at desc);

-- Outcome tracking: signals stay in the table forever; the engine flips
-- status through the TP ladder (tp1→tp2→tp3) or to sl_hit/expired.
alter table public.signals
    add column if not exists status text not null default 'open';
alter table public.signals
    add column if not exists closed_at timestamptz;

alter table public.signals drop constraint if exists signals_status_check;
alter table public.signals add constraint signals_status_check
    check (status in (
        'open', 'tp1_hit', 'tp2_hit', 'tp3_hit', 'tp_hit', 'sl_hit', 'expired'
    ));

-- Multi-level take profits (TP1=1R, TP2=2R, TP3=3R). Legacy `take_profit`
-- remains as TP1 for older readers; new writers also fill take_profit_1/2/3.
alter table public.signals add column if not exists take_profit_1 double precision;
alter table public.signals add column if not exists take_profit_2 double precision;
alter table public.signals add column if not exists take_profit_3 double precision;
alter table public.signals add column if not exists tp1_hit_at timestamptz;
alter table public.signals add column if not exists tp2_hit_at timestamptz;
alter table public.signals add column if not exists tp3_hit_at timestamptz;

-- Only copy legacy take_profit into TP1. Never clone the same price into
-- TP2/TP3 — that made one candle hit mark all three levels at once.
update public.signals
set take_profit_1 = coalesce(take_profit_1, take_profit)
where take_profit_1 is null;

-- Repair rows previously backfilled with TP2=TP3=TP1.
update public.signals
set take_profit_2 = null, take_profit_3 = null
where take_profit_1 is not null
  and take_profit_2 is not distinct from take_profit_1
  and take_profit_3 is not distinct from take_profit_1;

drop index if exists signals_status_idx;
create index if not exists signals_status_idx
    on public.signals (status)
    where status in ('open', 'tp1_hit', 'tp2_hit');

-- Before the unique open-index: keep the newest live row per symbol+timeframe
-- and expire older duplicates (from overlapping cron runs).
with ranked as (
    select
        id,
        row_number() over (
            partition by symbol, timeframe
            order by created_at desc, id desc
        ) as rn
    from public.signals
    where status in ('open', 'tp1_hit', 'tp2_hit')
)
update public.signals s
set
    status = 'expired',
    closed_at = coalesce(s.closed_at, now())
from ranked r
where s.id = r.id
  and r.rn > 1;

-- At most one live trade per symbol+timeframe (blocks concurrent engine races).
drop index if exists signals_one_open_per_symbol_tf;
create unique index if not exists signals_one_open_per_symbol_tf
    on public.signals (symbol, timeframe)
    where status in ('open', 'tp1_hit', 'tp2_hit');

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

-- Server-side aggregation for the landing/dashboard/admin stats tiles —
-- avoids pulling every matching row into Node just to count/average them.
-- security invoker (not definer) is essential: it makes this function run
-- as the calling role, so the RLS policies above still apply per caller —
-- anon still only sees the 24h preview, authenticated still sees full
-- history. A definer function here would silently bypass that gate.
-- DROP first: CREATE OR REPLACE cannot change OUT / return row shape.
drop function if exists public.get_signal_stats(text);
create or replace function public.get_signal_stats(p_timeframe text default null)
returns table (
    total int,
    avg_confidence int,
    longs int,
    shorts int,
    tp_hits int,
    partial_wins int,
    sl_hits int
)
language sql
stable
security invoker
as $$
    select
        count(*)::int as total,
        coalesce(round(avg(confidence)), 0)::int as avg_confidence,
        count(*) filter (where direction = 'long')::int as longs,
        count(*) filter (where direction = 'short')::int as shorts,
        -- Full wins: reached final target.
        count(*) filter (where status in ('tp_hit', 'tp3_hit'))::int as tp_hits,
        -- Partial wins: stopped out after banking at least TP1.
        count(*) filter (
            where status = 'sl_hit' and tp1_hit_at is not null
        )::int as partial_wins,
        -- Pure losses: stopped with no TP banked.
        count(*) filter (
            where status = 'sl_hit' and tp1_hit_at is null
        )::int as sl_hits
    from public.signals
    where p_timeframe is null or timeframe = p_timeframe;
$$;

grant execute on function public.get_signal_stats(text) to anon, authenticated;

-- Bot settings: one row, read by the engine at the start of each run and
-- edited from /admin. RLS is enabled with NO policies on purpose — only the
-- service-role key (engine + admin page) can read or write it.
create table if not exists public.bot_settings (
    id integer primary key check (id = 1),
    symbols jsonb not null default '["BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT"]',
    min_alert_confidence integer not null
        default 0 check (min_alert_confidence between 0 and 100),
    min_store_confidence integer not null
        default 0 check (min_store_confidence between 0 and 100),
    signal_strategy text not null default 'ema_cross'
        check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone')),
    updated_at timestamptz not null default now()
);

-- Existing installs: add strategy + store-confidence columns without recreate.
alter table public.bot_settings
    add column if not exists signal_strategy text not null default 'ema_cross';
-- Refresh the allowed-strategy check so admin-selectable strategies added after
-- the original install (e.g. sr_zone) are accepted. Idempotent.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone'));
alter table public.bot_settings
    add column if not exists min_store_confidence integer not null default 0;

alter table public.bot_settings enable row level security;

insert into public.bot_settings (id) values (1)
    on conflict (id) do nothing;

-- Do not UPDATE symbols here — re-running schema.sql must not wipe admin
-- edits. New installs get defaults from the column default / INSERT above.

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
