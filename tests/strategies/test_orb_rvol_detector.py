"""Rule tests for the orb_rvol entry/stop/target rules.

Builds a full scenario per test: MIN_RVOL_SAMPLES quiet prior same-anchor
opens (so relative_volume can compute), enough padding to clear MIN_CANDLES,
then today's opening range and (usually) a breakout bar.
"""
from datetime import datetime, timezone

from signals.models import Candle
from signals.strategies.orb_rvol.detector import (
    ATR_STOP_BUFFER,
    MAX_STOP_ATR,
    MIN_CANDLES,
    detect_setup,
)
from signals.strategies.orb_rvol.windows import MIN_RVOL_SAMPLES, OR_BARS

DAY0 = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
ATR = 1.0


def _bar(minutes, open_=100.0, high=100.2, low=99.8, close=100.0, volume=10.0):
    return Candle(open_time=DAY0 + minutes * 60_000, open=open_, high=high,
                 low=low, close=close, volume=volume)


def _padding(n):
    """Filler bars whose minute-offset never lands on a 15-min-multiple
    anchor boundary. -1_000_000 minutes % 15 == 5 in Python's non-negative
    modulo, and every anchor (0 / 420 / 810) is a multiple of 15, so stepping
    by 15 from there can never coincide with a real anchor no matter how many
    padding bars are added."""
    return [_bar(-1_000_000 + i * 15) for i in range(n)]


def _asia_scenario(*, rvol_multiplier=10.0, breakout=True, extra_after=0,
                   bullish=True):
    """MIN_RVOL_SAMPLES quiet prior Asia opens, then today's Asia OR (bullish
    unless `bullish=False`) at `rvol_multiplier`x the prior volume, then
    (optionally) a breakout bar, then `extra_after` further non-breakout bars."""
    prior_volume = 10.0
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        start = day * 24 * 60
        candles.append(_bar(start, volume=prior_volume))
        candles.append(_bar(start + 15, volume=prior_volume))
    today = (MIN_RVOL_SAMPLES + 1) * 24 * 60
    or_volume = prior_volume * rvol_multiplier
    if bullish:
        candles.append(_bar(today, open_=100.0, high=100.5, low=99.5,
                            close=100.2, volume=or_volume))
        candles.append(_bar(today + 15, open_=100.2, high=101.0, low=100.0,
                            close=100.8, volume=or_volume))  # close 100.8 > open 100.0
        or_high, or_low = 101.0, 99.5
        breakout_bar = _bar(today + 30, open_=100.8, high=102.0, low=100.7,
                            close=101.5, volume=or_volume)
    else:
        candles.append(_bar(today, open_=100.0, high=100.5, low=99.0,
                            close=99.6, volume=or_volume))
        # low=99.0 (not 98.5) keeps this OR the same 1.5-wide mirror of the
        # bullish scenario's OR (101.0-99.5=1.5); 98.5 would widen it to 2.0
        # and, combined with a 98.0 breakout close below, push the short's
        # risk to 2.75 ATR — over MAX_STOP_ATR (2.5).
        candles.append(_bar(today + 15, open_=99.6, high=99.9, low=99.0,
                            close=99.0, volume=or_volume))  # close 99.0 < open 100.0
        or_high, or_low = 100.5, 99.0
        # close=98.5 (not 98.0) is the true mirror of the bullish scenario's
        # breakout close of 101.5: both sit ATR_STOP_BUFFER + OR width + a 0.5
        # breakout depth from their far OR edge, so risk is 2.25 ATR either
        # direction (under MAX_STOP_ATR, and still < or_low so it breaks out).
        breakout_bar = _bar(today + 30, open_=99.0, high=99.1, low=97.5,
                            close=98.5, volume=or_volume)
    if breakout:
        candles.append(breakout_bar)
    for i in range(extra_after):
        candles.append(_bar(today + 45 + i * 15, volume=or_volume))
    pad = _padding(max(0, MIN_CANDLES - len(candles)))
    return pad + candles, or_high, or_low


def _atr14(candles):
    return [ATR] * len(candles)


def test_bullish_or_high_rvol_first_close_above_high_fires_long():
    candles, or_high, or_low = _asia_scenario()
    setup = detect_setup("BTCUSD", candles, _atr14(candles))
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 101.5
    assert setup.stop_loss == or_low - ATR_STOP_BUFFER * ATR
    risk = setup.entry - setup.stop_loss
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp1 - (setup.entry + 2.0 * risk)) < 1e-9
    assert abs(tp2 - (setup.entry + 4.0 * risk)) < 1e-9
    assert abs(tp3 - (setup.entry + 6.0 * risk)) < 1e-9
    assert setup.indicators["strategy"] == "orb_rvol"
    assert setup.indicators["session"] == "Asia"
    assert setup.indicators["or_direction"] == "bullish"


def test_bearish_or_mirror_fires_short():
    candles, or_high, or_low = _asia_scenario(bullish=False)
    setup = detect_setup("BTCUSD", candles, _atr14(candles))
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 98.5
    assert setup.stop_loss == or_high + ATR_STOP_BUFFER * ATR


def test_rvol_below_minimum_returns_none():
    """The headline gate: an opening range at or below its own anchor's
    typical volume must not trade even with a clean breakout."""
    candles, _, _ = _asia_scenario(rvol_multiplier=0.5)
    assert detect_setup("BTCUSD", candles, _atr14(candles)) is None


def test_bullish_or_but_price_breaks_down_returns_none():
    """Direction lock: a bullish opening range only permits longs, so a
    breakdown through or_low must not fire a short."""
    prior_volume = 10.0
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        start = day * 24 * 60
        candles.append(_bar(start, volume=prior_volume))
        candles.append(_bar(start + 15, volume=prior_volume))
    today = (MIN_RVOL_SAMPLES + 1) * 24 * 60
    or_volume = prior_volume * 10.0
    candles.append(_bar(today, open_=100.0, high=100.5, low=99.5, close=100.2,
                        volume=or_volume))
    candles.append(_bar(today + 15, open_=100.2, high=101.0, low=100.0,
                        close=100.8, volume=or_volume))  # bullish OR
    # Price instead breaks DOWN through or_low (99.5) — must not fire a short.
    candles.append(_bar(today + 30, open_=100.0, high=100.1, low=99.0,
                        close=99.3, volume=or_volume))
    pad = _padding(max(0, MIN_CANDLES - len(candles)))
    candles = pad + candles
    assert detect_setup("BTCUSD", candles, _atr14(candles)) is None


def test_doji_opening_range_returns_none():
    prior_volume = 10.0
    candles = []
    for day in range(1, MIN_RVOL_SAMPLES + 1):
        start = day * 24 * 60
        candles.append(_bar(start, volume=prior_volume))
        candles.append(_bar(start + 15, volume=prior_volume))
    today = (MIN_RVOL_SAMPLES + 1) * 24 * 60
    or_volume = prior_volume * 10.0
    candles.append(_bar(today, open_=100.0, high=100.5, low=99.5, close=100.5,
                        volume=or_volume))
    candles.append(_bar(today + 15, open_=100.5, high=101.0, low=99.8,
                        close=100.0, volume=or_volume))  # last close == first open
    candles.append(_bar(today + 30, open_=100.0, high=102.0, low=99.0,
                        close=101.5, volume=or_volume))
    pad = _padding(max(0, MIN_CANDLES - len(candles)))
    candles = pad + candles
    assert detect_setup("BTCUSD", candles, _atr14(candles)) is None


def test_a_later_bar_in_the_same_window_does_not_refire():
    """One trade per anchor: once the window's first breakout bar is no
    longer the LAST bar (a later bar has since closed), the detector must
    not fire again."""
    candles, _, _ = _asia_scenario(extra_after=1)
    assert detect_setup("BTCUSD", candles, _atr14(candles)) is None


def test_no_breakout_yet_returns_none():
    candles, _, _ = _asia_scenario(breakout=False)
    assert detect_setup("BTCUSD", candles, _atr14(candles)) is None


def test_stop_wider_than_max_stop_atr_returns_none():
    """A tiny ATR relative to the opening range's width blows the stop cap."""
    candles, _, _ = _asia_scenario()
    tiny_atr = [0.01] * len(candles)
    assert detect_setup("BTCUSD", candles, tiny_atr) is None


def test_below_min_candles_returns_none():
    candles, _, _ = _asia_scenario()
    short = candles[-(MIN_CANDLES - 1):]
    assert detect_setup("BTCUSD", short, _atr14(short)) is None


def test_no_setup_without_an_atr():
    candles, _, _ = _asia_scenario()
    atr14 = _atr14(candles)
    atr14[-1] = None
    assert detect_setup("BTCUSD", candles, atr14) is None
