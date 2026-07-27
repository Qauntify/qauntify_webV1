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

drop index if exists signals_status_idx;
create index if not exists signals_status_idx
    on public.signals (status)
    where status in ('open', 'tp1_hit', 'tp2_hit');
