"""Unit tests for ICT 5m FVG super-scalp detector."""
from signals.models import Candle, SUPER_SCALP_TP1_R, SUPER_SCALP_TP2_R, SUPER_SCALP_TP3_R
from signals.strategies.ict_fvg.detector import (
    detect_setup,
    find_bullish_fvg,
)


def _c(i, o, h, l, c):
    return Candle(open_time=i, open=o, high=h, low=l, close=c, volume=1.0)


def _bullish_ict_fvg_series():
    """Sweep + CHoCH + bullish FVG + fresh retest on the last bars."""
    candles = []
    for i in range(16):
        candles.append(_c(i, 100, 100.8, 99.2, 100))
    # Swing low pivot.
    candles.append(_c(16, 99.5, 100.0, 98.0, 99.0))
    candles.append(_c(17, 99.0, 100.5, 98.8, 100.0))
    candles.append(_c(18, 100.0, 101.0, 99.5, 100.5))
    # Swing high pivot.
    candles.append(_c(19, 100.5, 102.0, 100.2, 101.5))
    candles.append(_c(20, 101.5, 101.8, 100.5, 101.0))
    candles.append(_c(21, 101.0, 101.2, 100.0, 100.2))
    # Sweep below 98.
    candles.append(_c(22, 100.0, 100.5, 96.8, 99.2))
    # Displacement / CHoCH above swing high — leaves bullish FVG vs bar 22.
    # Bar 22 high=100.5; bar 24 low must be > 100.5 for FVG at index 24.
    candles.append(_c(23, 99.5, 103.5, 99.0, 103.0))  # big impulse
    candles.append(_c(24, 103.0, 104.0, 101.0, 103.5))  # FVG vs high of 22 if 22.high < 24.low
    # 22.high=100.5, 24.low=101.0 -> FVG [100.5, 101.0] at i=24
    # Retest into FVG then bounce (fresh).
    candles.append(_c(25, 103.0, 103.2, 100.6, 101.8))
    return candles


def test_find_bullish_fvg():
    candles = [
        _c(0, 100, 100.5, 99.5, 100),
        _c(1, 100, 102, 100, 101.5),
        _c(2, 101.5, 103, 101.2, 102.5),  # gap vs 0.high 100.5 < 101.2
    ]
    fvg = find_bullish_fvg(candles, 0, 2)
    assert fvg is not None
    i, bottom, top = fvg
    assert i == 2
    assert bottom == 100.5
    assert top == 101.2


def test_detect_ict_fvg_bullish():
    candles = _bullish_ict_fvg_series()
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["strategy"] == "ict_fvg"
    assert "fvg_bottom" in setup.indicators
    risk = setup.entry - setup.stop_loss
    assert abs(setup.take_profit - (setup.entry + SUPER_SCALP_TP1_R * risk)) < 1e-9
    assert abs(setup.take_profit_2 - (setup.entry + SUPER_SCALP_TP2_R * risk)) < 1e-9
    assert abs(setup.take_profit_3 - (setup.entry + SUPER_SCALP_TP3_R * risk)) < 1e-9


def test_detect_ict_fvg_allows_htf_against():
    """HTF is a soft preference — against-trend still eligible."""
    candles = _bullish_ict_fvg_series()
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14, htf_trend="down")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["htf_trend"] == "down"


def test_detect_ict_fvg_none_without_retest():
    candles = _bullish_ict_fvg_series()[:-1]  # drop retest bar
    atr14 = [4.0] * len(candles)
    assert detect_setup("BTCUSDT", candles, atr14) is None


def test_detect_ict_fvg_accepts_older_retest():
    """Retest may be up to 5 bars before the latest close (was 2)."""
    candles = _bullish_ict_fvg_series()
    # Pad three closed bars after the retest so last_i - retest_i == 4.
    base = len(candles)
    for i in range(3):
        candles.append(_c(base + i, 101.8, 102.2, 101.4, 101.9))
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "long"


def test_router_dispatches_ict_fvg():
    from signals.strategies import detect_setup as route
    candles = _bullish_ict_fvg_series()
    n = len(candles)
    setup = route(
        "ict_fvg", "BTCUSDT", candles,
        [100] * n, [100] * n, [55] * n, [0.1] * n, [4.0] * n,
        htf_trend="up",
    )
    assert setup is not None
    assert setup.indicators["strategy"] == "ict_fvg"
