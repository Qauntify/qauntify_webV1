"""Tests for orb_rvol's session-anchor, opening-range, and RVOL arithmetic.

A synthetic candle series is built on 15m boundaries anchored to a known UTC
timestamp (2024-01-01 00:00 UTC, a Monday — day-of-week plays no role in the
anchor math, which is pure time-of-day modulo arithmetic) so anchors land
deterministically.
"""
from datetime import datetime, timezone

from signals.models import Candle
from signals.strategies.orb_rvol.windows import (
    MIN_RVOL_SAMPLES,
    OR_BARS,
    RVOL_LOOKBACK,
    TRADE_WINDOW_BARS,
    current_anchor,
    opening_range,
    opening_range_volume,
    relative_volume,
)

DAY0 = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _bar(minutes, open_=100.0, high=100.5, low=99.5, close=100.0, volume=10.0):
    return Candle(open_time=DAY0 + minutes * 60_000, open=open_, high=high,
                 low=low, close=close, volume=volume)


def _or_bars(day, hour, minute, volume=10.0):
    """The OR_BARS opening-range bars for one day's anchor at hour:minute UTC."""
    start = day * 24 * 60 + hour * 60 + minute
    return [_bar(start + i * 15, volume=volume) for i in range(OR_BARS)]


def test_current_anchor_at_asia_open():
    candles = [_bar(0)]
    name, idx = current_anchor(candles)
    assert name == "Asia"
    assert idx == 0


def test_current_anchor_at_london_open():
    candles = [_bar(m) for m in range(0, 7 * 60 + 15, 15)]
    name, idx = current_anchor(candles)
    assert name == "London"
    assert candles[idx].open_time == DAY0 + 7 * 60 * 60_000


def test_current_anchor_at_ny_open():
    candles = [_bar(m) for m in range(0, 13 * 60 + 30 + 15, 15)]
    name, idx = current_anchor(candles)
    assert name == "NY"
    assert candles[idx].open_time == DAY0 + (13 * 60 + 30) * 60_000


def test_current_anchor_none_between_asia_window_end_and_london_open():
    # Asia's window ends 04:30 (00:00 + 30min OR + 4h trade window). 05:00 is
    # past it but before London opens at 07:00 — no anchor covers it.
    candles = [_bar(5 * 60)]
    name, idx = current_anchor(candles)
    assert name is None
    assert idx is None


def test_current_anchor_none_between_ny_window_end_and_midnight():
    # NY window ends 18:00 (13:30 + 30min OR + 4h). Nothing is anchored again
    # until the next day's Asia open at 00:00.
    candles = [_bar(19 * 60)]
    name, idx = current_anchor(candles)
    assert name is None
    assert idx is None


def test_opening_range_high_low_and_bullish_direction():
    candles = [
        _bar(0, open_=100.0, high=101.0, low=99.5, close=100.5),
        _bar(15, open_=100.5, high=102.0, low=100.0, close=101.5),
    ]
    rng = opening_range(candles, 0)
    assert rng == (102.0, 99.5, "bullish")  # last close 101.5 > first open 100.0


def test_opening_range_bearish_direction():
    candles = [
        _bar(0, open_=100.0, high=100.5, low=99.0, close=99.5),
        _bar(15, open_=99.5, high=99.8, low=98.0, close=98.5),
    ]
    _, _, direction = opening_range(candles, 0)
    assert direction == "bearish"  # last close 98.5 < first open 100.0


def test_opening_range_doji_when_last_close_equals_first_open():
    candles = [
        _bar(0, open_=100.0, close=100.5),
        _bar(15, open_=100.5, close=100.0),  # last close == first open
    ]
    _, _, direction = opening_range(candles, 0)
    assert direction is None


def test_opening_range_none_when_incomplete():
    candles = [_bar(0)]  # only 1 bar; OR_BARS is 2
    assert opening_range(candles, 0) is None


def test_opening_range_volume_sums_the_or_bars():
    candles = [_bar(0, volume=10.0), _bar(15, volume=15.0)]
    assert opening_range_volume(candles, 0) == 25.0


def test_relative_volume_averages_only_same_anchor_priors():
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        candles += _or_bars(day, 0, 0, volume=10.0)  # OR volume 20.0 each
    today = MIN_RVOL_SAMPLES + 1
    candles += _or_bars(today, 0, 0, volume=100.0)  # OR volume 200.0
    anchor_index = len(candles) - OR_BARS
    rvol = relative_volume(candles, "Asia", anchor_index)
    assert rvol == 200.0 / 20.0


def test_relative_volume_ignores_neighbouring_sessions():
    """Interleaving London/NY opens between the Asia priors must not pollute
    Asia's RVOL average."""
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        candles += _or_bars(day, 0, 0, volume=10.0)     # Asia, OR vol 20.0
        candles += _or_bars(day, 7, 0, volume=999.0)    # London, ignored
        candles += _or_bars(day, 13, 30, volume=999.0)  # NY, ignored
    today = MIN_RVOL_SAMPLES + 1
    candles += _or_bars(today, 0, 0, volume=100.0)
    anchor_index = len(candles) - OR_BARS
    rvol = relative_volume(candles, "Asia", anchor_index)
    assert rvol == 200.0 / 20.0


def test_relative_volume_none_below_min_samples():
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES):  # one short of MIN_RVOL_SAMPLES
        candles += _or_bars(day, 0, 0, volume=10.0)
    today = MIN_RVOL_SAMPLES
    candles += _or_bars(today, 0, 0, volume=100.0)
    anchor_index = len(candles) - OR_BARS
    assert relative_volume(candles, "Asia", anchor_index) is None


def test_relative_volume_excludes_zero_volume_priors_from_the_mean():
    volumes = [10.0, 0.0, 10.0, 10.0]
    candles = []
    for day, vol in enumerate(volumes, start=1):
        candles += _or_bars(day, 0, 0, volume=vol)
    today = len(volumes) + 1
    candles += _or_bars(today, 0, 0, volume=60.0)  # OR volume 120.0
    anchor_index = len(candles) - OR_BARS
    rvol = relative_volume(candles, "Asia", anchor_index)
    # The zero-volume prior is dropped; remaining priors are 20.0 each -> mean 20.0.
    assert rvol == 120.0 / 20.0


def test_relative_volume_none_when_current_or_volume_is_zero():
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        candles += _or_bars(day, 0, 0, volume=10.0)
    today = MIN_RVOL_SAMPLES + 1
    candles += _or_bars(today, 0, 0, volume=0.0)
    anchor_index = len(candles) - OR_BARS
    assert relative_volume(candles, "Asia", anchor_index) is None


def test_relative_volume_only_averages_the_lookback_window():
    """More than RVOL_LOOKBACK priors exist; only the most recent
    RVOL_LOOKBACK are averaged, not every prior ever seen."""
    candles = []
    # RVOL_LOOKBACK old, quiet priors (volume 1.0 -> OR volume 2.0 each)...
    for day in range(1, RVOL_LOOKBACK + 1):
        candles += _or_bars(day, 0, 0, volume=1.0)
    # ...then RVOL_LOOKBACK recent, louder priors (volume 10.0 -> OR volume 20.0).
    for day in range(RVOL_LOOKBACK + 1, 2 * RVOL_LOOKBACK + 1):
        candles += _or_bars(day, 0, 0, volume=10.0)
    today = 2 * RVOL_LOOKBACK + 1
    candles += _or_bars(today, 0, 0, volume=200.0)  # OR volume 400.0
    anchor_index = len(candles) - OR_BARS
    rvol = relative_volume(candles, "Asia", anchor_index)
    # If the old quiet priors leaked in, the mean would be lower than 20.0.
    assert rvol == 400.0 / 20.0
