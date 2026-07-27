-- Which experiment a shadow row belongs to. `shadow` is the containment flag
-- (never deliver, already covered by the RLS policies); `experiment` says WHICH
-- study, so results never get pooled across unrelated trials.
--   'gate_ab'  — LLM confirmation-gate A/B (rejected setups)
--   'sr_limit' — limit-entry S/R paper trial at 1h
-- NULL for ordinary delivered signals.
alter table public.signals
    add column if not exists experiment text;

create index if not exists signals_experiment_idx
    on public.signals (experiment)
    where experiment is not null;
