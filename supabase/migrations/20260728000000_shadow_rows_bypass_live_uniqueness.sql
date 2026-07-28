-- ---------------------------------------------------------------------------
-- Shadow rows must not compete with live signals for the one-open slot.
--
-- 20260710000000 added a unique index on (symbol, timeframe) for open statuses
-- to stop overlapping cron runs publishing two live recommendations for the
-- same market. That index predates shadow rows and does not filter on the
-- `shadow` column added in 20260726000000.
--
-- The consequence is silent and biased. A shadow or paper row for BTCUSD@1h
-- collides with any OPEN live BTCUSD@1h signal, the insert fails on the unique
-- violation, and both callers swallow the error by design (_save_shadow and
-- _record_paper_sr_limit must never break a live scan). So shadows were
-- dropped exactly when a live signal happened to be open — not at random.
-- For the confirmation-gate A/B that is a real problem: it silently thins the
-- shadow arm in precisely the conditions where the delivered arm is active,
-- which is the comparison the experiment exists to make.
--
-- The original constraint's purpose is unaffected: it exists to prevent two
-- live RECOMMENDATIONS, and a shadow is by definition never delivered.
-- Shadows keep their own one-open rule, scoped per experiment, so a single
-- study still cannot stack duplicate rows on one market.
-- ---------------------------------------------------------------------------

-- Live signals: unchanged rule, now explicitly scoped to delivered rows.
drop index if exists signals_one_open_per_symbol_tf;
create unique index if not exists signals_one_open_per_symbol_tf
    on public.signals (symbol, timeframe)
    where shadow = false and status in ('open', 'tp1_hit', 'tp2_hit');

-- Shadows: at most one open row per market PER EXPERIMENT, so two unrelated
-- studies can observe the same market at once without blocking each other.
-- coalesce guards the NULL-experiment case, which Postgres would otherwise
-- treat as always-distinct and never deduplicate.
drop index if exists signals_one_open_shadow_per_experiment;
create unique index if not exists signals_one_open_shadow_per_experiment
    on public.signals (symbol, timeframe, coalesce(experiment, ''))
    where shadow = true and status in ('open', 'tp1_hit', 'tp2_hit');
