"""Unit tests for the Support/Resistance bounce detector (sr_zone)."""
from signals.models import Candle, TP1_R, TP2_R, TP3_R
from signals.strategies.sr_zone.detector import detect_setup


def _c(i, o, h, l, c):
    return Candle(open_time=i, open=o, high=h, low=l, close=c, volume=1.0)


def _reflect(candles, axis=205.0):
    """Mirror a series around `axis` so support becomes resistance.

    A pivot low at price p becomes a pivot high at axis-p, a bullish
    confirmation bar becomes a bearish one, etc. Lets the resistance
    tests reuse the support fixture's exact structure.
    """
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


def _support_bounce_series():
    """Two swing lows clustered at ~100 (a 2-touch support zone), then a
    final bar that wicks into the zone and closes back above it (bullish
    rejection = confirmed bounce)."""
    rows = [
        (105, 106, 104, 105),
        (104, 105, 103, 104),
        (103, 104, 102, 103),
        (102, 103, 101, 102),
        (101, 102, 100, 100.5),   # 4: pivot low #1 @ 100
        (100.5, 102, 101, 101.5),
        (101.5, 103, 102, 102.5),
        (102.5, 104, 103, 103.5),
        (103.5, 105, 104, 104.5),
        (104.5, 105, 103, 103.5),
        (103.5, 104, 102, 102.5),
        (102.5, 103, 101, 101.5),
        (101.5, 102, 100.5, 101),  # 12: pivot low #2 @ 100.5 -> clusters
        (101, 102, 101, 101.5),
        (101.5, 103, 102, 102.5),
        (102.5, 104, 103, 103.5),
        (103.5, 105, 104, 104.5),
        (104.5, 106, 105, 105.5),
        (105.5, 106, 104, 104.5),
        (104.5, 105, 103, 103.5),
        (103.5, 105, 104, 104.5),
        (104.5, 106, 105, 105.5),
        (105.5, 106, 104, 104.5),
        (104.5, 105, 103, 103.5),
        (103.5, 105, 104, 104.5),
        (104.5, 106, 105, 105.5),
        (105.5, 106, 104, 104.5),
        (104.5, 105, 103, 103.5),
        (103.5, 104, 102, 102.5),
        (102.5, 103, 101.5, 102),
        (102, 103, 101, 101.5),
        (101, 103.5, 100.2, 103),  # 31: confirmation bounce (last closed bar)
    ]
    return [_c(i, *row) for i, row in enumerate(rows)]


def test_support_bounce_is_long():
    candles = _support_bounce_series()
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "long"
    ind = setup.indicators
    assert ind["strategy"] == "sr_zone"
    assert ind["side"] == "support"
    assert ind["touches"] == 2
    assert ind["zone_low"] == 100
    assert ind["zone_high"] == 100.5
    # Entry is the confirmation close; stop sits below the zone.
    assert setup.entry == 103
    assert setup.stop_loss < 100
    risk = setup.entry - setup.stop_loss
    assert abs(setup.take_profit - (setup.entry + TP1_R * risk)) < 1e-9
    assert abs(setup.take_profit_2 - (setup.entry + TP2_R * risk)) < 1e-9
    assert abs(setup.take_profit_3 - (setup.entry + TP3_R * risk)) < 1e-9


def test_resistance_rejection_is_short():
    candles = _reflect(_support_bounce_series())
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    assert setup.direction == "short"
    ind = setup.indicators
    assert ind["side"] == "resistance"
    assert ind["touches"] == 2
    assert setup.stop_loss > setup.entry


def test_touch_without_rejection_close_is_none():
    """Price wicks the zone but closes back inside it -> not a bounce."""
    candles = _support_bounce_series()
    candles[-1] = _c(31, 100.4, 100.8, 100.2, 100.3)  # closes below zone high
    atr14 = [4.0] * len(candles)
    assert detect_setup("BTCUSDT", candles, atr14) is None


def _single_touch_series():
    """One clean swing low at 100 (a single touch), plus a bounce bar. Flat
    equal-low stretches never form pivots, so no 2-touch zone can build."""
    rows = [(105, 106, 104, 105)] * 8            # 0-7: flat, no pivots
    rows += [
        (104, 105, 102, 103),                    # 8
        (103, 104, 100, 101),                    # 9: sole pivot low @100
        (101, 103, 102, 102.5),                  # 10
        (102.5, 104, 103, 103.5),                # 11
    ]
    rows += [(105, 106, 104, 105)] * 16          # 12-27: flat, no pivots
    rows += [
        (104, 105, 103, 103.5),                  # 28
        (103.5, 104, 102, 102.5),                # 29
        (102.5, 103, 101, 101.5),                # 30
        (101, 103.5, 100.2, 103),                # 31: bounce, but level is 1-touch
    ]
    return [_c(i, *row) for i, row in enumerate(rows)]


def test_single_touch_level_is_none():
    """A level tested only once is below MIN_TOUCHES -> no zone, no trade."""
    candles = _single_touch_series()
    atr14 = [4.0] * len(candles)
    assert detect_setup("BTCUSDT", candles, atr14) is None


def test_strong_trend_adx_ceiling_blocks_bounce():
    """ADX at/above the ceiling marks a strong trend -> skip mean-reversion."""
    candles = _support_bounce_series()
    atr14 = [4.0] * len(candles)
    n = len(candles)
    assert detect_setup("BTCUSDT", candles, atr14, adx14=[40.0] * n) is None
    # A ranging ADX still allows the bounce.
    setup = detect_setup("BTCUSDT", candles, atr14, adx14=[18.0] * n)
    assert setup is not None
    assert setup.indicators["adx"] == 18.0


def test_htf_trend_filters_against_direction():
    candles = _support_bounce_series()
    atr14 = [4.0] * len(candles)
    # HTF up agrees with a long bounce.
    up = detect_setup("BTCUSDT", candles, atr14, htf_trend="up")
    assert up is not None and up.direction == "long"
    assert up.indicators["htf_trend"] == "up"
    # HTF down opposes the long -> filtered out.
    assert detect_setup("BTCUSDT", candles, atr14, htf_trend="down") is None


def test_router_dispatches_sr_zone():
    from signals.strategies import detect_setup as route
    candles = _support_bounce_series()
    n = len(candles)
    setup = route(
        "sr_zone", "BTCUSDT", candles,
        [100] * n, [100] * n, [55] * n, [0.1] * n, [4.0] * n,
        adx14=[18.0] * n, htf_trend="up",
    )
    assert setup is not None
    assert setup.indicators["strategy"] == "sr_zone"
    assert setup.direction == "long"
