-- Free tools library: MT5 EAs, indicators, TradingView scripts, etc.
create table if not exists public.tools (
    id uuid primary key default gen_random_uuid(),
    title_km text not null,
    description_km text not null default '',
    category text not null default 'other'
        check (category in ('mt5_ea', 'mt5_indicator', 'tradingview', 'other')),
    file_url text,
    file_name text,
    mime_type text,
    file_size bigint,
    external_url text,
    sort_order int not null default 0,
    published boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists tools_published_sort_idx
    on public.tools (published, sort_order asc, created_at desc);

alter table public.tools enable row level security;

drop policy if exists "public read published tools" on public.tools;
create policy "public read published tools"
    on public.tools for select
    using (published = true);

-- Public bucket for downloadable tool files (service-role upload, public read).
insert into storage.buckets (id, name, public)
values ('tools', 'tools', true)
on conflict (id) do nothing;
