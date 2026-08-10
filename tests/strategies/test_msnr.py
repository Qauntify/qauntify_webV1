"""MSNR detector — body zones, rejection, and RBS/SBR break-retest."""
from signals.models import Candle, TRADING_SESSIONS
from signals.strategies.msnr.detector import detect_setup


def _c(i, o, h, l, c):
    return Candle(open_time=i * 3_600_000, open=o, high=h, low=l, close=c, volume=1.0)


def _atr(candles, value=4.0):
    return [value] * len(candles)


def _pad(rows, n=45, filler=(105.0, 106.0, 104.0, 105.0)):
    rows = list(rows)
    while len(rows) < n:
        rows.insert(0, filler)
    return rows


def _reflect(candles, axis=220.0):
    """Mirror OHLC so support↔resistance and long↔short."""
    return [
        Candle(
            open_time=c.open_time,
            open=axis - c.open,
            high=axis - c.low,
            low=axis - c.high,
            close=axis - c.close,
            volume=c.volume,
        )
        for c in candles
    ]


def _rejection_long_series():
    """Pivot support body ~100, then bullish rejection wick into the zone."""
    rows = _pad([
        (105, 106, 104, 105),
        (104, 105, 103, 104),
        (103, 104, 102, 103),
        (102, 103, 101, 102),
        (101, 101.2, 99.8, 100.1),   # pivot low body
        (100.1, 102, 100.05, 101.5),
        (101.5, 103, 101.2, 102.5),
        (102.5, 104, 102.2, 103.5),
        (103.5, 105, 103.2, 104.5),
        (104.5, 106, 104.2, 105.5),
        (105.5, 107, 105.2, 106.5),
        (106.5, 108, 106.2, 107.5),
        (107.5, 108, 105.5, 106),
        (106, 106.5, 104.5, 105),
        (105, 105.5, 103.5, 104),
        (104, 104.5, 102.5, 103),
        (103, 104.5, 99.9, 103.5),   # rejection
    ], n=45)
    return [_c(i, *row) for i, row in enumerate(rows)]


def _rbs_long_series():
    """Resistance body ~110 broken, then retested as support."""
    rows = _pad([
        (100, 101, 99.5, 100.5),
        (100.5, 102, 100, 101.5),
        (101.5, 103, 101, 102.5),
        (102.5, 104, 102, 103.5),
        (103.5, 106, 103, 105.5),
        (105.5, 108, 105, 107.5),
        (107.5, 109.5, 107, 109),
        (109.5, 110.4, 109.2, 110.0),  # resistance pivot
        (108.8, 109.0, 107.5, 108.0),
        (108.0, 108.5, 106.5, 107.0),
        (107.0, 108.0, 106.0, 106.5),
        (106.5, 108.5, 106.2, 108.0),
        (108.0, 111.5, 107.8, 111.2),  # break up
        (111.2, 113.0, 111.0, 112.5),
        (112.5, 113.0, 111.5, 111.8),
        (111.8, 112.0, 110.8, 111.0),
        (111.0, 112.2, 109.6, 111.4),  # RBS retest
    ], n=50, filler=(100.0, 101.0, 99.0, 100.0))
    return [_c(i, *row) for i, row in enumerate(rows)]


def test_long_rejection_at_fresh_support():
    candles = _rejection_long_series()
    setup = detect_setup("XAUUSD", candles, _atr(candles), htf_trend="up")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["strategy"] == "msnr"
    assert setup.indicators["entry_mode"] == "rejection"
    assert setup.indicators["side"] == "support"
    assert setup.stop_loss < setup.entry


def test_short_rejection_blocked_when_htf_up():
    candles = _reflect(_rejection_long_series())
    assert detect_setup("XAUUSD", candles, _atr(candles), htf_trend="up") is None


def test_rbs_long_break_and_retest():
    candles = _rbs_long_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles, 2.5), htf_trend="up")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["entry_mode"] == "rbs"
    assert setup.indicators["side"] == "rbs"
    assert "break_time" in setup.indicators
    assert "retest_time" in setup.indicators


def test_sbr_short_break_and_retest():
    candles = _reflect(_rbs_long_series())
    setup = detect_setup("ETHUSD", candles, _atr(candles, 2.5), htf_trend="down")
    assert setup is not None
    assert setup.direction == "short"
    assert setup.indicators["entry_mode"] == "sbr"
    assert setup.indicators["side"] == "sbr"


def test_router_dispatches_msnr():
    from signals.strategies import router
    from signals.strategies.msnr import detect_setup as msnr_detect

    candles = _rejection_long_series()
    atr = _atr(candles)
    ema = [None] * len(candles)
    out = router.detect_setup(
        "msnr", "XAUUSD", candles, ema, ema, ema, ema, atr, htf_trend="up",
    )
    direct = msnr_detect("XAUUSD", candles, atr, htf_trend="up")
    assert out is not None and direct is not None
    assert out.direction == direct.direction
    assert out.indicators["strategy"] == "msnr"


def test_swing_session_pins_msnr():
    swing = next(s for s in TRADING_SESSIONS if s.name == "swing")
    assert swing.timeframe == "1h"
    assert swing.strategy == "msnr"
    assert swing.confluence_timeframe == "4h"
