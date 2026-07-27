-- ---------------------------------------------------------------------------
-- This file no longer defines the schema. See supabase/migrations/.
--
-- It used to be a single idempotent file whose documented usage was "run this
-- in the SQL Editor" — including on an existing database. That was fine at
-- first and stopped being fine once it contained data-mutating repairs: a
-- backfill of the TP ladder, and a statement that expires every duplicate open
-- signal. Re-running the file replayed those against production rows, and
-- nothing recorded which parts had already been applied.
--
-- The contents are now split into ordered, individually-scoped migrations in
-- supabase/migrations/, applied with the Supabase CLI:
--
--     supabase db push
--
-- Every migration is idempotent, so pushing against the existing database is a
-- no-op. See supabase/migrations/README.md.
--
-- This file intentionally raises if executed, so pasting it into the SQL
-- Editor out of habit fails loudly instead of silently rewriting data.
-- ---------------------------------------------------------------------------
do $$
begin
    raise exception
        'supabase/schema.sql is no longer runnable. Use `supabase db push` '
        '(see supabase/migrations/README.md).';
end
$$;
