-- Server-side aggregation for the landing/dashboard/admin stats tiles —
-- avoids pulling every matching row into Node just to count/average them.
--
-- security invoker (not definer) is essential: it makes this function run as
-- the calling role, so the RLS policies still apply per caller — anon still
-- only sees the 24h preview, authenticated still sees full history. A definer
-- function here would silently bypass that gate.
--
-- The `shadow = false` filter is repeated inside the body even though the
-- policies already hide shadows, because the web app calls this RPC
-- server-side where the service-role key bypasses RLS entirely and would
-- otherwise count shadows into the public stat tiles.
--
-- DROP first: CREATE OR REPLACE cannot change OUT / return row shape.
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
        -- Full wins: reached final target.
        count(*) filter (where status in ('tp_hit', 'tp3_hit'))::int as tp_hits,
        -- Partial wins: stopped out after banking at least TP1.
        count(*) filter (
            where status = 'sl_hit' and tp1_hit_at is not null
        )::int as partial_wins,
        -- Pure losses: stopped with no TP banked.
        count(*) filter (
            where status = 'sl_hit' and tp1_hit_at is null
        )::int as sl_hits
    from public.signals
    where shadow = false
      and (p_timeframe is null or timeframe = p_timeframe);
$$;

grant execute on function public.get_signal_stats(text) to anon, authenticated;
