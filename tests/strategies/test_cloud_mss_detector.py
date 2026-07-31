"""Rule tests for the cloud + market-structure-shift detector.

The cloud is built from a 1h Chandelier Exit and a 15m LWMA200. Rather than
hand-fitting 1h candles that put the Chandelier band at a chosen price, these
tests monkeypatch `_cloud` — the seam that returns (trend, low, high) — so they
exercise the SEQUENCE rules. Chandelier arithmetic is covered in
tests/core/test_indicators.py.
"""
from signals.models import Candle
from signals.strategies.cloud_mss import detector as mod
from signals.strategies.cloud_mss.detector import (
    MAX_BARS_SINCE_TOUCH,
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    detect_setup,
)

N = MIN_CANDLES + 40
ATR = 5.0
CLOUD_LOW = 105.0
CLOUD_HIGH = 107.0
H1 = [Candle(i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(60)]


def _c(open_, high, low, close, i):
    return Candle(open_time=i * 900_000, open=open_, high=high, low=low,
                  close=close, volume=1.0)


def _patch_cloud(monkeypatch, trend):
    monkeypatch.setattr(mod, "_cloud",
                        lambda _h1, _ma: (trend, CLOUD_LOW, CLOUD_HIGH))


def _sell_series():
    """Price just below an overhead cloud, a rally that wicks into it and
    closes back below, then a close under the pre-touch swing low.

    Geometry is deliberately realistic: the cloud sits well under 1 ATR above
    price. An earlier version parked it 5-7 ATR away, which describes a market
    that does not occur — and could only pass by disabling the risk guard.
    """
    candles = [_c(100.0, 100.6, 99.4, 100.0, i) for i in range(N)]
    candles[N - 12] = _c(99.6, 99.8, 99.0, 99.6, N - 12)     # swing low 99.0
    candles[N - 8] = _c(101.0, 102.0, 100.8, 101.5, N - 8)   # swing high 102.0
    candles[N - 3] = _c(102.0, 106.0, 101.0, 101.5, N - 3)   # wick into cloud
    candles[N - 2] = _c(101.5, 101.8, 99.8, 100.0, N - 2)
    candles[N - 1] = _c(100.0, 100.5, 98.0, 98.5, N - 1)     # CHoCH below 99.0
    return candles


def _buy_series():
    """Mirror: price just above a cloud below it, a dip that wicks in and
    closes back above, then a close over the pre-touch swing high."""
    candles = [_c(110.0, 110.6, 109.4, 110.0, i) for i in range(N)]
    candles[N - 12] = _c(111.0, 112.0, 110.8, 111.5, N - 12)  # swing high 112.0
    candles[N - 8] = _c(109.6, 109.8, 109.0, 109.6, N - 8)    # swing low 109.0
    candles[N - 3] = _c(109.0, 109.5, 106.0, 108.0, N - 3)    # wick into cloud
    candles[N - 2] = _c(108.0, 110.5, 107.8, 110.0, N - 2)
    candles[N - 1] = _c(110.0, 113.5, 109.8, 113.0, N - 1)    # close > 112.0
    return candles


def test_sell_fires_on_a_rejection_then_choch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    setup = detect_setup("BTCUSD", _sell_series(), [ATR] * N, h1_candles=H1)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 98.5


def test_sell_stop_sits_past_the_far_edge_of_the_cloud(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    setup = detect_setup("BTCUSD", _sell_series(), [ATR] * N, h1_candles=H1)
    assert setup.stop_loss == CLOUD_HIGH + STOP_ATR_BUFFER * ATR


def test_targets_are_one_two_and_three_r(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    setup = detect_setup("BTCUSD", _sell_series(), [ATR] * N, h1_candles=H1)
    risk = setup.stop_loss - setup.entry
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp1 - (setup.entry - risk)) < 1e-9
    assert abs(tp2 - (setup.entry - 2 * risk)) < 1e-9
    assert abs(tp3 - (setup.entry - 3 * risk)) < 1e-9


def test_no_setup_when_the_ce_trend_disagrees_with_the_cloud_side(monkeypatch):
    """An overhead cloud is only a sell zone while the 1h Chandelier is
    bearish."""
    _patch_cloud(monkeypatch, 1)
    assert detect_setup("BTCUSD", _sell_series(), [ATR] * N,
                        h1_candles=H1) is None


def test_no_setup_when_price_sits_inside_the_cloud(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 1] = _c(100.0, 106.5, 98.0, 106.0, N - 1)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_when_the_touch_bar_closes_inside_the_cloud(monkeypatch):
    """Closing inside means the cloud has not rejected price yet."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(102.0, 106.5, 101.0, 106.0, N - 3)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_without_a_touch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(102.0, 104.0, 101.0, 101.5, N - 3)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_without_a_choch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 1] = _c(100.0, 100.5, 99.2, 99.5, N - 1)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_a_breakout_through_the_cloud_voids_the_setup(monkeypatch):
    """A close above the pre-touch swing high between the touch and the break
    means the pullback resolved as continuation. Dead, not pending — and it
    must stay dead even though the final bar closes below the swing low."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 2] = _c(101.5, 102.8, 101.2, 102.5, N - 2)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_choch_must_be_the_first_break_not_a_later_one(monkeypatch):
    """If an earlier bar already broke the swing low, that bar was the CHoCH
    and fired then. Re-firing would open a second trade on one setup."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 2] = _c(101.5, 101.8, 98.2, 98.6, N - 2)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_touch_older_than_the_limit_is_ignored(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(102.0, 104.0, 101.0, 101.5, N - 3)
    far = N - 2 - MAX_BARS_SINCE_TOUCH - 1
    candles[far] = _c(102.0, 106.0, 101.0, 101.5, far)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_when_the_stop_exceeds_the_atr_cap(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    assert detect_setup("BTCUSD", _sell_series(), [0.2] * N,
                        h1_candles=H1) is None


def test_indicators_tag_the_strategy_and_carry_the_cloud(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    setup = detect_setup("BTCUSD", _sell_series(), [ATR] * N, h1_candles=H1)
    assert setup.indicators["strategy"] == "cloud_mss"
    assert setup.indicators["cloud_low"] == CLOUD_LOW
    assert setup.indicators["cloud_high"] == CLOUD_HIGH
    assert setup.indicators["side"] == "premium"


def test_buy_fires_on_the_mirror_setup(monkeypatch):
    _patch_cloud(monkeypatch, 1)
    setup = detect_setup("BTCUSD", _buy_series(), [ATR] * N, h1_candles=H1)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 113.0
    assert setup.stop_loss == CLOUD_LOW - STOP_ATR_BUFFER * ATR
    assert setup.indicators["side"] == "discount"


def test_no_setup_without_h1_candles(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    assert detect_setup("BTCUSD", _sell_series(), [ATR] * N,
                        h1_candles=None) is None
    assert detect_setup("BTCUSD", _sell_series(), [ATR] * N,
                        h1_candles=[]) is None


def test_no_setup_below_the_minimum_candle_count(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    short = _sell_series()[-(MIN_CANDLES - 1):]
    assert detect_setup("BTCUSD", short, [ATR] * len(short),
                        h1_candles=H1) is None


def test_no_setup_without_an_atr(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    assert detect_setup("BTCUSD", _sell_series(), [None] * N,
                        h1_candles=H1) is None
