"""Both BBMA keys must be dispatchable, and must NOT leak into the admin
dropdown — they have no session and no migration entry."""
from signals.models import (
    ADMIN_SELECTABLE_STRATEGIES,
    Candle,
    SIGNAL_STRATEGIES,
    TRADING_SESSIONS,
)
from signals.strategies import detect_setup
from signals.strategies.bbma import detect_extreme, detect_reentry
from signals.strategies.bbma.stack import MIN_CANDLES


def _flat_candles(n):
    """Flat bars — no setup should fire, so both paths return None and the
    assertion is about the router reaching the right detector, not about the
    rules. Defined here rather than imported from another test module:
    tests/strategies has no __init__.py and nothing else in this suite imports
    across test files.
    """
    return [
        Candle(open_time=i * 3_600_000, open=100.0, high=100.5, low=99.5,
               close=100.0, volume=1.0)
        for i in range(n)
    ]


def _dispatch(strategy, candles, atr14):
    """Call the router the way backtest.py does."""
    return detect_setup(
        strategy, "BTCUSD", candles,
        [None] * len(candles), [None] * len(candles), [None] * len(candles),
        [None] * len(candles), atr14,
        adx14=None, htf_trend=None, h1_candles=None,
    )


def test_both_keys_are_registered():
    assert "bbma_extreme" in SIGNAL_STRATEGIES
    assert "bbma_reentry" in SIGNAL_STRATEGIES


def test_both_keys_are_admin_selectable():
    """Promoted 2026-07-28 at the operator's direction. Selecting either sets
    the SWING session's strategy, so these deliver to Telegram.

    tests/core/test_strategy_choices.py is what guarantees the three sources
    agree — Python, the bot_settings CHECK constraint and the admin dropdown.
    A key present here but missing from the constraint would be accepted by
    Python and rejected by the database on write.
    """
    assert "bbma_extreme" in ADMIN_SELECTABLE_STRATEGIES
    assert "bbma_reentry" in ADMIN_SELECTABLE_STRATEGIES


def test_neither_key_is_pinned_to_a_live_session():
    pinned = {s.strategy for s in TRADING_SESSIONS if s.strategy}
    assert "bbma_extreme" not in pinned
    assert "bbma_reentry" not in pinned


def test_router_reaches_the_extreme_detector():
    candles = _flat_candles(MIN_CANDLES)
    atr14 = [2.0] * MIN_CANDLES
    assert _dispatch("bbma_extreme", candles, atr14) == detect_extreme(
        "BTCUSD", candles, atr14)


def test_router_reaches_the_reentry_detector():
    candles = _flat_candles(MIN_CANDLES)
    atr14 = [2.0] * MIN_CANDLES
    assert _dispatch("bbma_reentry", candles, atr14) == detect_reentry(
        "BTCUSD", candles, atr14)


def test_unknown_strategy_still_falls_back_to_ema_cross(capsys):
    """The BBMA branches must not swallow the router's existing fallback."""
    candles = _flat_candles(MIN_CANDLES)
    _dispatch("nonsense_strategy", candles, [2.0] * MIN_CANDLES)
    assert "Unknown signal_strategy" in capsys.readouterr().out
