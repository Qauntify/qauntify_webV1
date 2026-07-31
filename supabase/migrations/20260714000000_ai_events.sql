-- AI event log: stores all SEA-LION responses (confirm/reject/no-setup
-- explanations) for audit + admin dashboard visibility. RLS enabled with no
-- policies so only the service-role key can read/write.
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
