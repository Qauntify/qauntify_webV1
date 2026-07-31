-- Freemium gate, enforced at the database:
--   anon (logged out)         → only signals from the last 24 hours (preview)
--   authenticated (signed in) → full history
-- Writes only via the service-role key (which bypasses RLS).
--
-- NOTE: these policies are superseded by 20260726000000_shadow_signals.sql,
-- which re-creates each one with a `shadow = false` filter. RLS policies
-- OR-combine, so every policy on the table has to carry that filter — leaving
-- any single one unfiltered would expose shadow rows regardless of the others.
alter table public.signals enable row level security;

drop policy if exists "public read access" on public.signals;

drop policy if exists "anon preview access" on public.signals;
create policy "anon preview access"
    on public.signals for select
    to anon
    using (created_at > now() - interval '24 hours');

drop policy if exists "member full access" on public.signals;
create policy "member full access"
    on public.signals for select
    to authenticated
    using (true);
