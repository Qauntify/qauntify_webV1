"""Dispatch setup detection to the strategy selected in bot_settings."""
from signals.models import DEFAULT_SIGNAL_STRATEGY
from signals.strategies.ema_cross import detect_setup as detect_ema_setup
from signals.strategies.ict_smc import detect_setup as detect_ict_setup


def detect_setup(strategy, symbol, candles, ema9, ema21, rsi14, macd_hist,
                 atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup for the active strategy, else None.

    `adx14`/`htf_trend` are ema_cross-only regime/confluence filters (see
    signals.strategies.ema_cross.detector); ict_smc ignores both."""
    if strategy == "ict_smc":
        return detect_ict_setup(symbol, candles, atr14)
    if strategy != "ema_cross":
        print(f"Unknown signal_strategy {strategy!r}, using {DEFAULT_SIGNAL_STRATEGY}")
    return detect_ema_setup(
        symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
        adx14=adx14, htf_trend=htf_trend,
    )
