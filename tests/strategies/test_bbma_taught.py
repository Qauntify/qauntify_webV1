"""Rule tests for taught MTF BBMA (H4 Mid+EMA50 bias + H1 entries)."""
from signals.models import Candle
from signals.strategies.bbma import taught
from signals.strategies.bbma.taught import (
    detect_extreme_mhv,
    detect_reentry,
    detect_setup,
    htf_bias_mid_ema50,
)
from signals.strategies.bbma.stack import MIN_CANDLES

N = 61
ATR = 5.0
ARM = 55

BASE = {
    "upper": 120.0, "mid": 100.0, "lower": 80.0,
    "ma5h": 104.0, "ma5l": 96.0,
    "ma10h": 103.0, "ma10l": 97.0,
    "ema50": 99.0,
}


def _c(open_, high, low, close, i=0):
    return Candle(open_time=i * 3_600_000, open=open_, high=high, low=low,
                  close=close, volume=1.0)


def _flat_stack(n=N):
    return {key: [value] * n for key, value in BASE.items()}


def _flat_candles(n=N):
    return [_c(100.0, 100.5, 99.5, 100.0, i) for i in range(n)]


def _patch_h1(monkeypatch, stack):
    monkeypatch.setattr(taught, "bbma_stack", lambda _c: stack)


def _h4_up():
    # close 110 > mid 100 and > ema50 99
    candles = [_c(100, 101, 99, 100, i) for i in range(MIN_CANDLES)]
    candles[-1] = _c(105, 111, 104, 110, MIN_CANDLES - 1)
    stack = {
        "upper": [120.0] * MIN_CANDLES,
        "mid": [100.0] * MIN_CANDLES,
        "lower": [80.0] * MIN_CANDLES,
        "ma5h": [104.0] * MIN_CANDLES,
        "ma5l": [96.0] * MIN_CANDLES,
        "ma10h": [103.0] * MIN_CANDLES,
        "ma10l": [97.0] * MIN_CANDLES,
        "ema50": [99.0] * MIN_CANDLES,
    }
    return candles, stack


def test_htf_bias_requires_mid_and_ema50(monkeypatch):
    candles, stack = _h4_up()
    monkeypatch.setattr(taught, "bbma_stack", lambda _c: stack)
    assert htf_bias_mid_ema50(candles) == "up"
    candles[-1] = _c(100, 101, 99, 100.5, MIN_CANDLES - 1)  # above mid, below ema → None
    stack["ema50"][-1] = 101.0
    assert htf_bias_mid_ema50(candles) is None


def test_reentry_long_requires_up_bias(monkeypatch):
    stack = _flat_stack()
    stack["upper"][ARM] = 99.0  # CSM
    candles = _flat_candles()
    candles[-2] = _c(100.0, 101.0, 95.0, 101.0, N - 2)
    candles[-1] = _c(101.0, 103.5, 102.0, 103.0, N - 1)
    _patch_h1(monkeypatch, stack)

    assert detect_reentry("XAUUSD", candles, [ATR] * N, None) is None
    assert detect_reentry("XAUUSD", candles, [ATR] * N, "down") is None
    setup = detect_reentry("XAUUSD", candles, [ATR] * N, "up")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["doctrine"] == "taught_mtf"
    assert setup.indicators["source"] == "taught"
    assert setup.indicators["htf_bias"] == "up"


def test_extreme_mhv_short_blocked_by_up_bias(monkeypatch):
    stack = _flat_stack()
    stack["ma5h"][-4] = 125.0  # escape above upper
    stack["ma5h"][-1] = 118.0
    # MHV bar: wick to upper, close inside
    candles = _flat_candles()
    candles[-3] = _c(118.0, 121.0, 115.0, 116.0, N - 3)  # high >= upper 120, close < upper
    # Confirm near the band so stop stays within MAX_STOP_ATR
    candles[-1] = _c(119.0, 119.5, 116.0, 117.0, N - 1)
    _patch_h1(monkeypatch, stack)

    assert detect_extreme_mhv("XAUUSD", candles, [ATR] * N, "up") is None
    setup = detect_extreme_mhv("XAUUSD", candles, [ATR] * N, None)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.indicators["strategy"] == "bbma_extreme"


def test_detect_setup_prefers_reentry(monkeypatch):
    h1_stack = _flat_stack()
    h1_stack["upper"][ARM] = 99.0
    h1 = _flat_candles()
    h1[-2] = _c(100.0, 101.0, 95.0, 101.0, N - 2)
    h1[-1] = _c(101.0, 103.5, 102.0, 103.0, N - 1)

    h4, h4_stack = _h4_up()

    def _stack(c):
        return h4_stack if len(c) == MIN_CANDLES else h1_stack

    monkeypatch.setattr(taught, "bbma_stack", _stack)
    setup = detect_setup("XAUUSD", h1, [ATR] * N, h4)
    assert setup is not None
    assert setup.indicators["strategy"] == "bbma_reentry"
