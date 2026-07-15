-- Trading Floor (independent of signals confirm engine)
create table if not exists public.floor_briefs (
    id uuid primary key default gen_random_uuid(),
    desk text not null check (desk in ('macro', 'technical', 'news', 'pm')),
    tone text not null check (tone in ('bullish', 'neutral', 'cautious')),
    body text not null,
    run_id text not null,
    created_at timestamptz not null default now()
);

create index if not exists floor_briefs_desk_created_at_idx
    on public.floor_briefs (desk, created_at desc);

create index if not exists floor_briefs_run_id_idx
    on public.floor_briefs (run_id);

alter table public.floor_briefs enable row level security;

drop policy if exists "members read floor briefs" on public.floor_briefs;
create policy "members read floor briefs"
    on public.floor_briefs for select
    to authenticated
    using (true);

create table if not exists public.floor_chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists floor_chat_messages_user_created_at_idx
    on public.floor_chat_messages (user_id, created_at desc);

alter table public.floor_chat_messages enable row level security;

drop policy if exists "members read own floor chat" on public.floor_chat_messages;
create policy "members read own floor chat"
    on public.floor_chat_messages for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "members insert own floor chat" on public.floor_chat_messages;
create policy "members insert own floor chat"
    on public.floor_chat_messages for insert
    to authenticated
    with check (auth.uid() = user_id);
