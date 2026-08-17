"""orb_rvol must be dispatchable through the shared router."""
from signals.models import SIGNAL_STRATEGIES
from signals.strategies import detect_setup
from signals.strategies.orb_rvol.detector import MIN_CANDLES


def _candles(n):
    from signals.models import Candle
    return [Candle(i * 900_000, 100.0, 100.2, 99.8, 100.0, 10.0)
            for i in range(n)]


def test_key_is_registered():
    assert "orb_rvol" in SIGNAL_STRATEGIES


def test_router_dispatches_without_error():
    n = MIN_CANDLES
    candles = _candles(n)
    result = detect_setup(
        "orb_rvol", "BTCUSD", candles,
        [None] * n, [None] * n, [None] * n, [None] * n, [2.0] * n,
        adx14=None, htf_trend=None, h1_candles=None,
    )
    # This synthetic series has no real session anchors aligned to it in a
    # way that would produce a setup — the point of this test is that
    # dispatch itself does not raise, not that a setup fires.
    assert result is None
