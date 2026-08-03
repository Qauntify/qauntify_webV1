-- Public product pages: guests can read all visible (non-shadow) signals.
-- Shadow rows stay hidden. Member policy unchanged.
drop policy if exists "anon preview access" on public.signals;
create policy "anon preview access"
    on public.signals for select
    to anon
    using (shadow = false);
