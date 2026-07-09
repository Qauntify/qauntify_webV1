from signals.strategies.ict_smc.detector import detect_setup as detect_ict_setup
from signals.models import Candle
from signals.strategies import detect_setup


def _candle(i, o, h, l, c):
    return Candle(open_time=i, open=o, high=h, low=l, close=c, volume=1.0)


def _bullish_ict_series():
    """Candles with liquidity sweep below swing low then CHoCH above swing high."""
    candles = []
    for i in range(10):
        candles.append(_candle(i, 95, 96, 92, 95))
    candles.append(_candle(10, 94, 95, 90, 94))
    for i in range(11, 20):
        candles.append(_candle(i, 95, 96, 91, 95))
    for i in range(20, 25):
        candles.append(_candle(i, 100, 105, 99, 102))
    candles.append(_candle(25, 104, 110, 103, 108))
    for i in range(26, 35):
        candles.append(_candle(i, 105, 109, 104, 106))
    candles.append(_candle(35, 93, 94, 88, 92))
    for i, close in enumerate([107, 111, 112], start=36):
        candles.append(_candle(i, close - 0.5, close + 0.5, close - 1.0, close))
    return candles


def test_detect_ict_setup_bullish():
    candles = _bullish_ict_series()
    atr14 = [2.0] * len(candles)
    setup = detect_ict_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["structure"] == "bullish_choch"
    assert setup.stop_loss < setup.entry < setup.take_profit


def test_detect_ict_setup_none_on_flat_market():
    candles = [_candle(i, 100, 100.5, 99.5, 100) for i in range(80)]
    atr14 = [1.0] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14) is None


def test_detect_ict_setup_bullish_shallow_sweep_is_rejected():
    # Same series as the passing bullish test, but the sweep wick barely
    # clears the prior swing low (depth 0.1 vs ATR 2.0) — noise, not a
    # genuine liquidity grab, so no setup should fire.
    candles = list(_bullish_ict_series())
    swept = candles[35]
    candles[35] = _candle(35, swept.open, swept.high, 89.9, swept.close)
    atr14 = [2.0] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14) is None


def test_strategy_router_uses_ema_by_default():
    n = 20
    candles = [
        Candle(open_time=i, open=100, high=101, low=99, close=100, volume=1.0)
        for i in range(n)
    ]
    ema9 = [99.0] * (n - 1) + [101.0]
    ema21 = [100.0] * n
    rsi14 = [55.0] * n
    macd_hist = [0.5] * n
    atr14 = [2.0] * n
    setup = detect_setup(
        "ema_cross", "BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14,
    )
    assert setup is not None
    assert setup.direction == "long"
    assert "ema9" in setup.indicators


def test_strategy_router_passes_adx_and_htf_trend_to_ema_cross():
    n = 20
    candles = [
        Candle(open_time=i, open=100, high=101, low=99, close=100, volume=1.0)
        for i in range(n)
    ]
    ema9 = [99.0] * (n - 1) + [101.0]
    ema21 = [100.0] * n
    rsi14 = [55.0] * n
    macd_hist = [0.5] * n
    atr14 = [2.0] * n
    adx14 = [15.0] * n  # below the trend-regime threshold -> blocks the setup

    setup = detect_setup(
        "ema_cross", "BTCUSDT", candles, ema9, ema21, rsi14, macd_hist,
        atr14, adx14=adx14,
    )
    assert setup is None

    setup = detect_setup(
        "ema_cross", "BTCUSDT", candles, ema9, ema21, rsi14, macd_hist,
        atr14, htf_trend="down",
    )
    assert setup is None


def test_strategy_router_dispatches_ict():
    candles = _bullish_ict_series()
    n = len(candles)
    none_series = [None] * n
    atr14 = [2.0] * n
    setup = detect_setup(
        "ict_smc", "BTCUSDT", candles, none_series, none_series,
        none_series, none_series, atr14,
    )
    assert setup is not None
    assert setup.indicators["strategy"] == "ict_smc"
