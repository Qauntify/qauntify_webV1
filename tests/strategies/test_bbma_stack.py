"""The BBMA stack must stay aligned to its candles — every detector indexes
these series positionally against bars."""
from signals.models import Candle
from signals.strategies.bbma.stack import (
    MAX_STOP_ATR,
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

KEYS = {"upper", "mid", "lower", "ma5h", "ma5l", "ma10h", "ma10l", "ema50"}


def _candles(n):
    return [
        Candle(open_time=i * 3_600_000, open=100.0 + i, high=101.0 + i,
               low=99.0 + i, close=100.5 + i, volume=1.0)
        for i in range(n)
    ]


def test_stack_has_every_expected_series():
    assert set(bbma_stack(_candles(80))) == KEYS


def test_every_series_is_aligned_to_the_candles():
    candles = _candles(80)
    stack = bbma_stack(candles)
    for key, series in stack.items():
        assert len(series) == len(candles), key


def test_ma5_is_applied_to_highs_and_lows_not_closes():
    """BBMA's MA5 High/Low read the bar's extremes. Reading closes instead
    would silently collapse the MA5 pair into one line."""
    stack = bbma_stack(_candles(80))
    assert stack["ma5h"][-1] > stack["ma5l"][-1]


def test_fast_ma_leads_slow_ma_in_an_uptrend():
    stack = bbma_stack(_candles(80))
    assert stack["ma5h"][-1] > stack["ma10h"][-1]


def test_stack_is_not_ready_during_warm_up():
    stack = bbma_stack(_candles(30))  # below the EMA50 warm-up
    assert stack_ready(stack) is False


def test_stack_is_ready_once_every_series_has_warmed_up():
    stack = bbma_stack(_candles(MIN_CANDLES))
    assert stack_ready(stack) is True


def test_risk_ok_accepts_a_stop_within_the_atr_cap():
    assert risk_ok(100.0, 98.0, 2.0) is True      # 1.0 ATR


def test_risk_ok_rejects_a_stop_beyond_the_atr_cap():
    assert risk_ok(100.0, 90.0, 2.0) is False     # 5.0 ATR > MAX_STOP_ATR


def test_risk_ok_rejects_a_non_positive_atr():
    assert risk_ok(100.0, 98.0, 0.0) is False


def test_stop_buffer_and_cap_are_the_documented_values():
    assert STOP_ATR_BUFFER == 0.5
    assert MAX_STOP_ATR == 2.5
