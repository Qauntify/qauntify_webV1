-- Annotated setup charts: PNG URL + structured annotation/candle data.
alter table public.signals add column if not exists chart_url text;
alter table public.signals add column if not exists chart_data jsonb;

-- Public bucket for rendered signal charts. Objects are uploaded with the
-- service key (bypasses RLS) and read via the public object path.
insert into storage.buckets (id, name, public)
values ('signal-charts', 'signal-charts', true)
on conflict (id) do nothing;

-- Outcome charts: PNG of how a closed trade played out (TP3 win / SL loss).
alter table public.signals add column if not exists outcome_chart_url text;
