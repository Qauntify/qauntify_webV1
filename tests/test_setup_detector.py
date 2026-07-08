from signals.models import Candle
from signals.strategies.ema_cross import (
    crossed_above_within,
    crossed_below_within,
    detect_setup,
)


def _candles(prices, low_offset=1.0, high_offset=1.0):
    return [
        Candle(open_time=i, open=p, high=p + high_offset,
               low=p - low_offset, close=p, volume=1.0)
        for i, p in enumerate(prices)
    ]


def _flat(value, n):
    return [value] * n


def test_crossed_above_within_detects_recent_cross():
    fast = [1.0, 1.0, 1.0, 2.0, 3.0]
    slow = [2.0, 2.0, 2.0, 2.0, 2.0]  # fast crosses above at index 3
    assert crossed_above_within(fast, slow, lookback=3) is True


def test_crossed_above_within_ignores_old_cross():
    fast = [1.0, 3.0, 3.0, 3.0, 3.0, 3.0]  # crossed at index 1, too old
    slow = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
    assert crossed_above_within(fast, slow, lookback=3) is False


def test_crossed_above_within_handles_none_padding():
    fast = [None, None, 1.0, 2.5]
    slow = [None, None, 2.0, 2.0]
    assert crossed_above_within(fast, slow, lookback=3) is True


def test_crossed_below_within_detects_recent_cross():
    fast = [3.0, 3.0, 3.0, 3.0, 1.0]
    slow = [2.0, 2.0, 2.0, 2.0, 2.0]
    assert crossed_below_within(fast, slow, lookback=3) is True


def test_detect_setup_long():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]   # crosses above ema21 on last bar
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    setup = detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 100.0
    # swing low = 99.0 (price 100 - low_offset 1), stop = 99 - 0.5*2 = 98
    assert setup.stop_loss == 98.0
    # risk = 2.0 → TP = 100 + 2*2 = 104
    assert setup.take_profit == 104.0
    assert setup.indicators["rsi"] == 55.0


def test_detect_setup_long_blocked_by_overbought_rsi():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]
    ema21 = _flat(100.0, n)
    rsi14 = _flat(75.0, n)  # >= 70 blocks the long
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_long_blocked_by_negative_macd():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(-0.5, n)  # negative momentum blocks the long
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_short():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(101.0, n - 1) + [99.0]   # crosses below ema21 on last bar
    ema21 = _flat(100.0, n)
    rsi14 = _flat(45.0, n)
    macd_hist = _flat(-0.5, n)
    atr14 = _flat(2.0, n)
    setup = detect_setup("ETHUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 100.0
    # swing high = 101.0, stop = 101 + 0.5*2 = 102, risk = 2 → TP = 96
    assert setup.stop_loss == 102.0
    assert setup.take_profit == 96.0


def test_detect_setup_short_blocked_by_oversold_rsi():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(101.0, n - 1) + [99.0]   # crosses below ema21 on last bar
    ema21 = _flat(100.0, n)
    rsi14 = _flat(25.0, n)  # <= 30 blocks the short
    macd_hist = _flat(-0.5, n)
    atr14 = _flat(2.0, n)
    assert detect_setup("ETHUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_short_blocked_by_positive_macd():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(101.0, n - 1) + [99.0]
    ema21 = _flat(100.0, n)
    rsi14 = _flat(45.0, n)
    macd_hist = _flat(0.5, n)  # positive momentum blocks the short
    atr14 = _flat(2.0, n)
    assert detect_setup("ETHUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_no_cross_returns_none():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n)   # always below, never crosses
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_warmup_none_returns_none():
    n = 5
    candles = _candles([100.0] * n)
    none_series = [None] * n
    assert detect_setup("BTCUSDT", candles, none_series, none_series,
                        none_series, none_series, none_series) is None
