-- Allow the swing session to be switched to orb_rvol.
--
-- Only the SWING session reads bot_settings.signal_strategy; the scalp
-- sessions pin their own strategy in TRADING_SESSIONS and ignore the toggle.
-- So this set must stay identical to:
--
--   * signals.models.ADMIN_SELECTABLE_STRATEGIES
--   * SIGNAL_STRATEGIES in web/src/lib/supabase/admin.ts (the dropdown)
--
-- tests/core/test_strategy_choices.py pins all three together.
--
-- orb_rvol is NOT assigned to a live TRADING_SESSIONS slot by this
-- migration or the work that introduced it — it is admin-selectable only so
-- it can be tried manually, pending the long-history verdict in
-- docs/orb-rvol-backtest-results.md. See
-- docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.
--
-- Idempotent: re-creating the constraint is safe.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone',
                               'bbma_reentry', 'bbma_extreme', 'orb_rvol'));
