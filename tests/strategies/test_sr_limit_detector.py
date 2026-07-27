"""Unit tests for the limit-entry S/R detector (sr_limit)."""
from signals.models import Candle
from signals.strategies.sr_limit.detector import detect_setup
from signals.strategies.sr_zone.detector import ATR_STOP_BUFFER

ATR = 2.0


def _c(i, o, h, l, c):
    return Candle(open_time=i * 60_000, open=o, high=h, low=l, close=c,
                  volume=1.0)


def _series(fill_bar):
    """Two swing lows clustered at ~100 (a 2-touch support zone), a drift back
    up, then `fill_bar` as the latest candle."""
    rows = [
        (105, 106, 104, 105),
        (104, 105, 103, 104),
        (103, 104, 102, 103),
        (102, 103, 101, 102),
        (101, 102, 100.0, 100.5),   # pivot low #1 @ 100.0
        (100.5, 102, 101, 101.5),
        (101.5, 103, 102, 102.5),
        (102.5, 104, 103, 103.5),
        (103.5, 105, 104, 104.5),
        (104.5, 105, 103, 103.5),
        (103.5, 104, 102, 102.5),
        (102.5, 103, 101, 101.5),
        (101.5, 102, 100.2, 101),   # pivot low #2 @ 100.2 -> clusters
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
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
        (101.5, 102, 101, 101.5),
    ]
    rows.append(fill_bar)
    return [_c(i, *r) for i, r in enumerate(rows)]


def _atr(candles, value=ATR):
    return [value] * len(candles)


def test_fills_at_the_zone_edge_not_the_close():
    """The whole point: entry is the resting level, not wherever the bar closed."""
    # Opens above the zone, trades down into it, closes well above.
    candles = _series((101.5, 102.0, 99.8, 101.8))
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "long"
    zone_high = setup.indicators["zone_high"]
    assert setup.entry == zone_high            # filled AT the level
    assert setup.entry < candles[-1].close     # strictly better than market
    assert setup.stop_loss == setup.indicators["zone_low"] - ATR_STOP_BUFFER * ATR


def test_no_fill_when_price_never_reaches_the_level():
    """A resting order that price never traded into simply does not fill.

    The bar's low stays above the zone's upper edge, so nothing is triggered.
    """
    candles = _series((101.8, 102.2, 101.5, 102.0))
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is None


def test_level_at_or_above_the_open_is_not_a_fresh_fill():
    """A resting BID must sit below the market when the bar opens.

    If the level were at or above the open, a continuously-traded market would
    already have filled that order on an earlier bar — counting it again here
    would invent a fill that never happened.
    """
    candles = _series((99.0, 101.0, 98.5, 100.5))  # opens below the zone
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_needs_no_confirmation_close():
    """Unlike sr_zone, a bearish close is fine — the limit already filled."""
    candles = _series((101.5, 102.0, 99.8, 100.0))  # closes DOWN
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "long"


def test_targets_are_the_standard_ladder():
    candles = _series((101.5, 102.0, 99.8, 101.8))
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    risk = setup.entry - setup.stop_loss
    assert abs(setup.take_profit_1 - (setup.entry + risk)) < 1e-9
    assert abs(setup.take_profit_2 - (setup.entry + 2 * risk)) < 1e-9
    assert abs(setup.take_profit_3 - (setup.entry + 3 * risk)) < 1e-9


def test_htf_downtrend_blocks_the_long():
    candles = _series((101.5, 102.0, 99.8, 101.8))
    assert detect_setup("BTCUSD", candles, _atr(candles),
                        htf_trend="down") is None


def test_insufficient_history_is_rejected():
    candles = _series((101.5, 102.0, 99.8, 101.8))[-10:]
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_missing_atr_is_rejected():
    candles = _series((101.5, 102.0, 99.8, 101.8))
    atr = _atr(candles)
    atr[-1] = None
    assert detect_setup("BTCUSD", candles, atr) is None


def test_the_level_comes_from_earlier_price_action():
    """The level must be one the order could have been resting at.

    Note the real guarantee here is structural rather than from the
    `window[:-1]` slice: a pivot requires PIVOT_RIGHT confirming bars after it,
    so the filling bar can never become a level however the window is sliced.
    Mutating the slice away is genuinely inert — verified. This test pins the
    property that matters (the level pre-existed the fill) so a future change to
    the pivot rules cannot silently introduce hindsight.
    """
    candles = _series((101.5, 102.0, 99.8, 101.8))
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    zone_low = setup.indicators["zone_low"]
    assert any(abs(c.low - zone_low) < 1e-9 for c in candles[:-1])
    assert setup.indicators["zone_high"] < candles[-1].open
