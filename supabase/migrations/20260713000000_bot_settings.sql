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
    signal_strategy text not null default 'ema_cross',
    updated_at timestamptz not null default now()
);

-- Existing installs: add strategy + store-confidence columns without recreate.
alter table public.bot_settings
    add column if not exists signal_strategy text not null default 'ema_cross';
alter table public.bot_settings
    add column if not exists min_store_confidence integer not null default 0;

alter table public.bot_settings enable row level security;

insert into public.bot_settings (id) values (1)
    on conflict (id) do nothing;

-- Do not UPDATE symbols here — re-running must not wipe admin edits. New
-- installs get defaults from the column default / INSERT above.
