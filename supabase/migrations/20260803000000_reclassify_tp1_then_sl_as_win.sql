-- Freeze TP-then-SL trades at the highest target banked (tp1_hit / tp2_hit)
-- with closed_at set, instead of over-labeling them as full tp_hit.
--
-- Open vs closed distinction for tp1_hit/tp2_hit is closed_at IS NULL vs set.
-- Unique "one open signal" indexes must therefore ignore closed rows.

-- 1) Unique indexes: only unfinished rows occupy the open slot.
drop index if exists signals_one_open_per_symbol_tf;
create unique index if not exists signals_one_open_per_symbol_tf
    on public.signals (symbol, timeframe)
    where shadow = false
      and status in ('open', 'tp1_hit', 'tp2_hit')
      and closed_at is null;

drop index if exists signals_one_open_shadow_per_experiment;
create unique index if not exists signals_one_open_shadow_per_experiment
    on public.signals (symbol, timeframe, coalesce(experiment, ''))
    where shadow = true
      and status in ('open', 'tp1_hit', 'tp2_hit')
      and closed_at is null;

drop index if exists signals_status_idx;
create index if not exists signals_status_idx
    on public.signals (status)
    where status in ('open', 'tp1_hit', 'tp2_hit')
      and closed_at is null;

-- 2) RLS: closed tp1_hit / tp2_hit are public closed-trade outcomes.
drop policy if exists "anon closed-trade access" on public.signals;
create policy "anon closed-trade access"
    on public.signals for select
    to anon
    using (
        shadow = false
        and (
            status in ('tp_hit', 'tp3_hit', 'sl_hit')
            or (status in ('tp1_hit', 'tp2_hit') and closed_at is not null)
        )
    );

-- 3) Stats: closed tp1/tp2 count as partial wins; pure SL is untouched stop.
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
        count(*) filter (where status in ('tp_hit', 'tp3_hit'))::int as tp_hits,
        count(*) filter (
            where (status in ('tp1_hit', 'tp2_hit') and closed_at is not null)
               or (status = 'sl_hit' and tp1_hit_at is not null)
        )::int as partial_wins,
        count(*) filter (
            where status = 'sl_hit' and tp1_hit_at is null
        )::int as sl_hits
    from public.signals
    where shadow = false
      and (p_timeframe is null or timeframe = p_timeframe);
$$;

grant execute on function public.get_signal_stats(text) to anon, authenticated;

-- 4) Reclassify wrongly labeled full wins and any remaining hybrid SL rows.
-- True legacy tp_hit rows stamp tp3_hit_at on close; our hybrids do not.
update public.signals
set status = case
        when tp2_hit_at is not null then 'tp2_hit'
        else 'tp1_hit'
    end,
    closed_at = coalesce(closed_at, tp2_hit_at, tp1_hit_at, created_at)
where status = 'tp_hit'
  and tp1_hit_at is not null
  and tp3_hit_at is null;

update public.signals
set status = case
        when tp2_hit_at is not null then 'tp2_hit'
        else 'tp1_hit'
    end,
    closed_at = coalesce(closed_at, tp2_hit_at, tp1_hit_at, created_at)
where status = 'sl_hit'
  and tp1_hit_at is not null;
