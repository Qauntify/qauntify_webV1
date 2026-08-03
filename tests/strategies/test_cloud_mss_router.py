"""cloud_mss must be dispatchable and must receive the 1h candles it needs."""
from signals.models import SIGNAL_STRATEGIES, Candle
from signals.strategies import detect_setup
from signals.strategies.cloud_mss.detector import MIN_CANDLES

H1 = [Candle(i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(60)]


def _candles(n):
    return [Candle(i * 900_000, 100.0, 100.5, 99.5, 100.0, 1.0)
            for i in range(n)]


def _dispatch(candles, h1_candles):
    n = len(candles)
    return detect_setup(
        "cloud_mss", "BTCUSD", candles,
        [None] * n, [None] * n, [None] * n, [None] * n, [2.0] * n,
        adx14=None, htf_trend=None, h1_candles=h1_candles,
    )


def test_key_is_registered():
    assert "cloud_mss" in SIGNAL_STRATEGIES


def test_router_dispatches_without_error():
    assert _dispatch(_candles(MIN_CANDLES), H1) is None


def test_router_returns_none_when_h1_is_missing():
    """The router must pass h1_candles through. If it dropped them the
    detector would return None for the wrong reason and the failure would be
    invisible — a session that silently never produces a signal."""
    assert _dispatch(_candles(MIN_CANDLES), None) is None
