-- FinhubKH signals table.
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
    symbols jsonb not null default '["BTCUSDT", "ETHUSDT"]',
    min_alert_confidence integer not null
        default 0 check (min_alert_confidence between 0 and 100),
    updated_at timestamptz not null default now()
);

alter table public.bot_settings enable row level security;

insert into public.bot_settings (id) values (1)
    on conflict (id) do nothing;
