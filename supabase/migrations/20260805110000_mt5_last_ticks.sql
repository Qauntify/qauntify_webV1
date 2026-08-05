-- Last MT5 broker tick per app symbol (e.g. XAUUSD).
-- Written by /api/mt5/tick on every EA push; read by the signals engine so
-- gold entries require a fresh broker mid (bid/ask aware).
create table if not exists public.mt5_last_ticks (
    symbol text primary key,
    price double precision not null check (price > 0),
    bid double precision,
    ask double precision,
    mid double precision,
    tick_time timestamptz not null,
    updated_at timestamptz not null default now()
);

alter table public.mt5_last_ticks add column if not exists bid double precision;
alter table public.mt5_last_ticks add column if not exists ask double precision;
alter table public.mt5_last_ticks add column if not exists mid double precision;

alter table public.mt5_last_ticks enable row level security;
-- No anon/authenticated policies: service role only (engine + tick webhook).
