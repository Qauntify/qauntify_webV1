"""Dispatch setup detection to the strategy selected for the session."""
from signals.models import DEFAULT_SIGNAL_STRATEGY
from signals.strategies.ce_lwma import detect_setup as detect_ce_setup
from signals.strategies.ema_cross import detect_setup as detect_ema_setup
from signals.strategies.ict_fvg import detect_setup as detect_ict_fvg_setup
from signals.strategies.ict_smc import detect_setup as detect_ict_setup


def detect_setup(strategy, symbol, candles, ema9, ema21, rsi14, macd_hist,
                 atr14, adx14=None, htf_trend=None, h1_candles=None):
    """Return a CandidateSetup for the active strategy, else None.

    `ce_lwma` needs `h1_candles` (closed H1 bars) in addition to the
    session's M15 `candles`. Other strategies ignore `h1_candles`.
    """
    if strategy == "ce_lwma":
        if not h1_candles:
            return None
        return detect_ce_setup(symbol, candles, h1_candles)
    if strategy == "ict_fvg":
        return detect_ict_fvg_setup(
            symbol, candles, atr14, htf_trend=htf_trend,
        )
    if strategy == "ict_smc":
        return detect_ict_setup(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
    if strategy != "ema_cross":
        print(f"Unknown signal_strategy {strategy!r}, using {DEFAULT_SIGNAL_STRATEGY}")
    return detect_ema_setup(
        symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
        adx14=adx14, htf_trend=htf_trend,
    )
