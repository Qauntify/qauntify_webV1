# Database migrations

Ordered, individually-scoped SQL applied with the Supabase CLI:

```bash
supabase db push
```

They replace the old single `supabase/schema.sql`, which was documented as
"re-run this in the SQL Editor". That worked until the file grew data-mutating
repairs — a TP-ladder backfill, and a statement that expires duplicate open
signals — at which point every re-run replayed them against production rows
with no record of what had already been applied.

## Rules

- **One concern per migration.** Name it after what it does.
- **Idempotent.** `create table if not exists`, `add column if not exists`,
  `drop policy if exists` before `create policy`. Pushing against a database
  that already has everything must be a no-op.
- **Never edit an applied migration.** Write a new one. The two files marked
  `ONE-TIME DATA REPAIR` are the reason this rule exists.
- **New data repairs go in their own migration**, marked as such, never
  appended to an existing file.

## Order matters for RLS

Policies OR-combine, so a row is visible if *any* policy allows it. The
`shadow = false` filter therefore has to appear on **every** policy on
`public.signals`, not just the newest one — see
`20260726000000_shadow_signals.sql`, which re-creates all three earlier
policies with the filter. Adding a policy without it would expose shadow rows
regardless of what the others say. `scripts/verify_shadow_rls.py` checks this
against the live database, in both directions.

## Applied history

| Migration | What it adds |
| --- | --- |
| `20260705000000_signals_table` | `signals` table + created_at index |
| `20260709000000_outcome_tracking_and_tp_ladder` | status/closed_at, TP1–3 columns and hit timestamps |
| `20260709000100_repair_tp_ladder_backfill` | **one-time data repair** |
| `20260710000000_one_open_signal_per_symbol_timeframe` | **one-time data repair** + unique open index |
| `20260712000000_freemium_rls` | anon 24h preview, authenticated full history |
| `20260713000000_bot_settings` | single-row engine settings |
| `20260714000000_ai_events` | LLM decision audit log |
| `20260722000000_agent_debates` | War Room transcripts |
| `20260722000100_engine_runs_and_lock` | heartbeat, `engine_status` view, run lock |
| `20260723000000_playbook_rag` | pgvector playbook chunks + match function |
| `20260724000000_signal_charts` | chart URLs/data + public storage bucket |
| `20260725000000_public_track_record` | anon access to closed trades |
| `20260726000000_shadow_signals` | `shadow` column, all policies re-created with the filter |
| `20260726000100_experiment_column` | `experiment` label for shadow rows |
| `20260726000200_signal_stats_function` | `get_signal_stats` RPC (security invoker) |
| `20260727000000_align_bot_settings_strategy_check` | strategy constraint matched to the app |
