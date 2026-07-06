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

-- Public dashboard reads with the anon key; writes only via the
-- service-role key (which bypasses RLS).
alter table public.signals enable row level security;

drop policy if exists "public read access" on public.signals;
create policy "public read access"
    on public.signals for select
    to anon
    using (true);
