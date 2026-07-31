-- ---------------------------------------------------------------------------
-- Shadow signals (LLM confirmation-gate A/B)
--
-- The gate rejects ~87% of the setups the rules engine finds, and nothing has
-- ever measured whether the discarded ones were worse. A rejected setup never
-- became a signal, so its outcome was never observable.
--
-- A shadow signal IS a rejected setup, stored with full levels and polled by
-- the outcome tracker so its result can be compared against delivered trades.
-- It is NOT a recommendation and must never reach a user.
--
-- RLS policies OR-combine, so every policy on signals is re-created below with
-- the shadow filter. Leaving any single one unfiltered would expose shadows
-- regardless of the others.
-- ---------------------------------------------------------------------------

alter table public.signals
    add column if not exists shadow boolean not null default false;

-- Partial index: every user-facing read filters shadow = false.
create index if not exists signals_visible_idx
    on public.signals (created_at desc)
    where shadow = false;

drop policy if exists "anon preview access" on public.signals;
create policy "anon preview access"
    on public.signals for select
    to anon
    using (shadow = false and created_at > now() - interval '24 hours');

drop policy if exists "anon closed-trade access" on public.signals;
create policy "anon closed-trade access"
    on public.signals for select
    to anon
    using (shadow = false and status in ('tp_hit', 'tp3_hit', 'sl_hit'));

drop policy if exists "member full access" on public.signals;
create policy "member full access"
    on public.signals for select
    to authenticated
    using (shadow = false);
