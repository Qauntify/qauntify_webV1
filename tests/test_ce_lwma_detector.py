"""Unit tests for the CE + LWMA scalp detector."""
from signals.models import Candle
from signals.strategies.ce_lwma.detector import detect_setup


def _candle(i, o, h, l, c):
    return Candle(open_time=i * 60_000, open=o, high=h, low=l, close=c, volume=1.0)


def test_detect_setup_needs_enough_history():
    m15 = [_candle(i, 100, 101, 99, 100) for i in range(50)]
    h1 = [_candle(i, 100, 101, 99, 100) for i in range(30)]
    assert detect_setup("BTCUSDT", m15, h1) is None


def test_detect_setup_long_on_bullish_flip_in_discount(monkeypatch):
    # Build enough M15 bars for LWMA200; force CE flip + zone via stubs.
    m15 = [_candle(i, 100, 101, 99, 100.0) for i in range(220)]
    h1 = [_candle(i, 100, 101, 99, 100.0) for i in range(60)]

    n = len(h1)
    long_stop = [None] * n
    short_stop = [None] * n
    direction = [None] * n
    long_stop[-2] = long_stop[-1] = 90.0
    short_stop[-2] = short_stop[-1] = 110.0
    direction[-2] = -1
    direction[-1] = 1

    monkeypatch.setattr(
        "signals.strategies.ce_lwma.detector.chandelier_exit",
        lambda *a, **k: (long_stop, short_stop, direction),
    )
    monkeypatch.setattr(
        "signals.strategies.ce_lwma.detector.lwma",
        lambda values, period: [None] * (len(values) - 1) + [95.0],
    )

    setup = detect_setup("BTCUSDT", m15, h1)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.stop_loss == 90.0
    assert setup.take_profit_2 is not None
    assert setup.take_profit_3 is not None
    assert setup.indicators["strategy"] == "ce_lwma"
    assert setup.indicators["zone"] == "discount"


def test_detect_setup_rejects_bullish_flip_in_premium(monkeypatch):
    m15 = [_candle(i, 100, 101, 99, 100.0) for i in range(220)]
    h1 = [_candle(i, 100, 101, 99, 100.0) for i in range(60)]
    n = len(h1)
    long_stop = [None] * n
    short_stop = [None] * n
    direction = [None] * n
    long_stop[-2] = long_stop[-1] = 105.0  # CE above MA → premium
    short_stop[-2] = short_stop[-1] = 120.0
    direction[-2] = -1
    direction[-1] = 1
    monkeypatch.setattr(
        "signals.strategies.ce_lwma.detector.chandelier_exit",
        lambda *a, **k: (long_stop, short_stop, direction),
    )
    monkeypatch.setattr(
        "signals.strategies.ce_lwma.detector.lwma",
        lambda values, period: [None] * (len(values) - 1) + [100.0],
    )
    assert detect_setup("BTCUSDT", m15, h1) is None
