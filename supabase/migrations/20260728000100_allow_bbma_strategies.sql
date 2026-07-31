-- Allow the swing session to be switched to either BBMA strategy.
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
-- WHAT THE MEASUREMENT SAYS, recorded here because this constraint is what
-- makes delivery possible. Over 8.87 years of SHA256-verified Binance history
-- on BTC and ETH, scored under the corrected fixed-stop R model
-- (docs/r-model-correction.md):
--
--   bbma_reentry   -0.137R per trade   t = -9.63    -656R
--   bbma_extreme   -0.153R per trade   t = -10.60   -738R
--
-- Both are significantly negative. Selecting either for the swing session
-- sends those trades to Telegram. This is enabled at the operator's explicit
-- direction; the constraint is not the place to litigate it, but it is the
-- place a future reader will look for the number.
--
-- Idempotent: re-creating the constraint is safe.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone',
                               'bbma_reentry', 'bbma_extreme'));
