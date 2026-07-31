-- Core signals table.
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
