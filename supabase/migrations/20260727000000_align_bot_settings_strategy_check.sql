-- Keep the allowed-strategy constraint in step with the application.
--
-- The engine implements five strategies, but only the SWING session reads
-- bot_settings.signal_strategy — the scalp sessions pin their own strategy in
-- TRADING_SESSIONS and ignore the toggle. So the admin-selectable set is the
-- three below, and it must match:
--
--   * signals.models.ADMIN_SELECTABLE_STRATEGIES
--   * SIGNAL_STRATEGIES in web/src/lib/supabase/admin.ts (the dropdown)
--
-- tests/core/test_strategy_choices.py pins all three together. Previously
-- Python validated against all five while this constraint allowed three, so a
-- value Python accepted would be rejected on write.
--
-- Idempotent: re-creating the constraint is safe.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone'));
