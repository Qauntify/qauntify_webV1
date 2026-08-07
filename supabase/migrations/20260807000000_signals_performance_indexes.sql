-- Performance pass: indexes for query shapes that were doing full/growing
-- scans, plus removal of one RLS policy left fully redundant by a later
-- migration.

-- 1) Dedup lookups (signals/storage.py:latest_signal, latest_signals_since)
-- run on every engine scan cycle, filtering symbol[+timeframe]+shadow=false,
-- ordered by created_at desc. No index covered this — cost grew with total
-- table size, not just open-row count.
create index if not exists signals_symbol_tf_created_idx
    on public.signals (symbol, timeframe, created_at desc)
    where shadow = false;

-- 2) Closed-signal reads (track-record page, CSV export, calibration/gate
-- reports) filter on terminal statuses and sort by closed_at with no limit.
-- Partial on "is not null" matches every one of those call sites exactly
-- (they all exclude still-open rows) and serves both asc/desc, nulls-last.
create index if not exists signals_closed_at_idx
    on public.signals (closed_at desc)
    where closed_at is not null;

-- 3) get_signal_stats(p_timeframe) aggregates over shadow=false rows,
-- optionally narrowed by timeframe. signals_visible_idx already covers the
-- "all timeframes" case; this adds the per-timeframe narrowing path.
create index if not exists signals_visible_timeframe_idx
    on public.signals (timeframe)
    where shadow = false;

-- 4) agent_debates had no index at all on signal_id, looked up on every
-- signal detail / War Room render. The table grows one row per confirmed
-- signal forever.
create index if not exists agent_debates_signal_id_idx
    on public.agent_debates (signal_id);

-- 5) "anon closed-trade access" (20260803000000) is now fully subsumed by
-- "anon preview access" (20260803120000, shadow=false with no other
-- condition) -- every row the closed-trade policy could ever match is
-- already visible under the broader one. RLS policies OR-combine, so this
-- was pure redundant per-row evaluation with zero effect on visible rows.
-- Not recreated: the broader policy already grants the same (and more)
-- access.
drop policy if exists "anon closed-trade access" on public.signals;
