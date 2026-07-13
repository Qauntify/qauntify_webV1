from signals.strategies.ict_smc.detector import detect_setup as detect_ict_setup
from signals.models import Candle
from signals.strategies import detect_setup


def _candle(i, o, h, l, c):
    return Candle(open_time=i, open=o, high=h, low=l, close=c, volume=1.0)


def _bullish_ict_series():
    """Fresh sweep + CHoCH with clear pivots and stop risk inside ATR cap.

    Layout (indices in the returned list):
      0-11  flat warmup
      12    swing low pivot (~98)
      13-14 rise
      15    swing high pivot (~102)
      16-17 pullback
      18    liquidity sweep below swing low, close back above
      19-20 CHoCH closes above swing high (fresh vs latest entry)
    """
    candles = []
    for i in range(16):
        candles.append(_candle(i, 100, 100.8, 99.2, 100))
    # Swing low pivot at 16 (lower than neighbors on both sides).
    candles.append(_candle(16, 99.5, 100.0, 98.0, 99.0))
    candles.append(_candle(17, 99.0, 100.5, 98.8, 100.0))
    candles.append(_candle(18, 100.0, 101.0, 99.5, 100.5))
    # Swing high pivot at 19.
    candles.append(_candle(19, 100.5, 102.0, 100.2, 101.5))
    candles.append(_candle(20, 101.5, 101.8, 100.5, 101.0))
    candles.append(_candle(21, 101.0, 101.2, 100.0, 100.2))
    # Sweep: wick below 98, close back above.
    candles.append(_candle(22, 100.0, 100.5, 96.8, 99.2))
    # CHoCH within last 3 bars.
    candles.append(_candle(23, 99.5, 102.5, 99.0, 102.2))
    candles.append(_candle(24, 102.0, 102.8, 101.5, 102.4))
    return candles


def test_detect_ict_setup_bullish():
    candles = _bullish_ict_series()
    atr14 = [4.0] * len(candles)
    setup = detect_ict_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["structure"] == "bullish_choch"
    assert setup.stop_loss < setup.entry < setup.take_profit
    assert abs(setup.entry - setup.stop_loss) / 4.0 <= 2.0


def test_detect_ict_setup_none_on_flat_market():
    candles = [_candle(i, 100, 100.5, 99.5, 100) for i in range(80)]
    atr14 = [1.0] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14) is None


def test_detect_ict_setup_bullish_shallow_sweep_is_rejected():
    candles = list(_bullish_ict_series())
    candles[22] = _candle(22, 100.0, 100.5, 97.8, 99.2)
    atr14 = [4.0] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14) is None


def test_detect_ict_setup_rejects_oversized_stop():
    candles = _bullish_ict_series()
    atr14 = [0.2] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14) is None


def test_detect_ict_setup_honors_htf_and_adx():
    candles = _bullish_ict_series()
    atr14 = [4.0] * len(candles)
    adx14 = [15.0] * len(candles)
    assert detect_ict_setup("BTCUSDT", candles, atr14, adx14=adx14) is None
    assert detect_ict_setup(
        "BTCUSDT", candles, atr14, htf_trend="down",
    ) is None


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
    adx14 = [15.0] * n

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
    atr14 = [4.0] * n
    setup = detect_setup(
        "ict_smc", "BTCUSDT", candles, none_series, none_series,
        none_series, none_series, atr14,
    )
    assert setup is not None
    assert setup.indicators["strategy"] == "ict_smc"


def test_strategy_router_passes_htf_to_ict():
    candles = _bullish_ict_series()
    n = len(candles)
    none_series = [None] * n
    atr14 = [4.0] * n
    setup = detect_setup(
        "ict_smc", "BTCUSDT", candles, none_series, none_series,
        none_series, none_series, atr14, htf_trend="down",
    )
    assert setup is None
