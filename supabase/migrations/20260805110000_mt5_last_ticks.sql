-- Last MT5 broker tick per app symbol (e.g. XAUUSD).
-- Written by /api/mt5/tick on every EA push; read by the signals engine so
-- gold entries can snap to the broker bid instead of only Kraken PAXG.
create table if not exists public.mt5_last_ticks (
    symbol text primary key,
    price double precision not null check (price > 0),
    tick_time timestamptz not null,
    updated_at timestamptz not null default now()
);

alter table public.mt5_last_ticks enable row level security;
-- No anon/authenticated policies: service role only (engine + tick webhook).
