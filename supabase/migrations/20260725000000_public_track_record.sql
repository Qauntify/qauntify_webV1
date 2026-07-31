-- Public track record: let logged-out visitors read historical CLOSED trades
-- (non-actionable proof). Permissive RLS OR-combines with the 24h anon
-- preview, so open/live signals older than 24h stay hidden from anon.
--
-- NOTE: superseded by 20260726000000_shadow_signals.sql, which re-creates this
-- policy with a `shadow = false` filter.
drop policy if exists "anon closed-trade access" on public.signals;
create policy "anon closed-trade access"
    on public.signals for select
    to anon
    using (status in ('tp_hit', 'tp3_hit', 'sl_hit'));
