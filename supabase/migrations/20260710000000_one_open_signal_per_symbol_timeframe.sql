-- At most one live trade per symbol+timeframe (blocks concurrent engine races).

-- ONE-TIME DATA REPAIR (already applied): keep the newest live row per
-- symbol+timeframe and expire older duplicates left by overlapping cron runs,
-- so the unique index below can be created. Safe to replay — after the first
-- run there are no duplicates to expire — but it should not be replayed.
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

drop index if exists signals_one_open_per_symbol_tf;
create unique index if not exists signals_one_open_per_symbol_tf
    on public.signals (symbol, timeframe)
    where status in ('open', 'tp1_hit', 'tp2_hit');
