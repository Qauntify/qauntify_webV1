"""Rule tests for the BBMA Re-entry detector.

As with the Extreme tests, the stack is monkeypatched so these exercise the
RULES rather than Bollinger arithmetic already covered elsewhere.
"""
import random

from signals.indicators import atr
from signals.models import Candle
from signals.strategies.bbma import reentry
from signals.strategies.bbma.reentry import MOMENTUM_LOOKBACK, detect_setup
from signals.strategies.bbma.stack import MIN_CANDLES

N = 60
ATR = 5.0

BASE = {
    "upper": 110.0, "mid": 100.0, "lower": 90.0,
    "ma5h": 104.0, "ma5l": 96.0,
    "ma10h": 103.0, "ma10l": 97.0,
    "ema50": 99.0,
}


def _c(open_, high, low, close, i=0):
    return Candle(open_time=i * 3_600_000, open=open_, high=high, low=low,
                  close=close, volume=1.0)


def _flat_stack(n=N):
    return {key: [value] * n for key, value in BASE.items()}


def _flat_candles(n=N):
    return [_c(100.0, 100.5, 99.5, 100.0, i) for i in range(n)]


def _patch(monkeypatch, stack):
    monkeypatch.setattr(reentry, "bbma_stack", lambda _candles: stack)


# --- long -------------------------------------------------------------------

def _long_stack():
    stack = _flat_stack()
    # Momentum leg: bar N-5's close (100.0) sits above a lowered upper band.
    stack["upper"][N - 5] = 99.0
    # Mid BB rising across the lookback — the "vertical band" test.
    stack["mid"][N - MOMENTUM_LOOKBACK] = 98.0
    return stack


def _long_candles():
    candles = _flat_candles()
    # Pullback bar: dips into MA5-Low (96) but closes above MA10-High (103).
    candles[-1] = _c(100.0, 104.0, 95.0, 103.5, N - 1)
    return candles


def test_long_fires_on_a_pullback_that_holds_the_ma_zone(monkeypatch):
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 103.5


def test_long_stop_sits_below_the_pullback_low(monkeypatch):
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    # min(bar low 95.0, ma10l 97.0) - STOP_ATR_BUFFER (0.5) * ATR (5.0)
    assert setup.stop_loss == 92.5


def test_long_uses_the_standard_ladder(monkeypatch):
    """Re-entry is a continuation trade, so it gets the engine's 1/2/3R —
    unlike Extreme's scalp ladder."""
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    risk = setup.entry - setup.stop_loss          # 11.0
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp1 - (103.5 + 1.0 * risk)) < 1e-9
    assert abs(tp2 - (103.5 + 2.0 * risk)) < 1e-9
    assert abs(tp3 - (103.5 + 3.0 * risk)) < 1e-9


def test_no_setup_without_a_prior_close_outside_the_band(monkeypatch):
    stack = _long_stack()
    stack["upper"][N - 5] = 110.0                 # remove the momentum leg
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_no_setup_when_the_band_is_flat(monkeypatch):
    stack = _long_stack()
    stack["mid"][N - MOMENTUM_LOOKBACK] = 100.0   # mid no longer rising
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_no_setup_when_the_close_breaks_the_mid_band(monkeypatch):
    stack = _long_stack()
    stack["ma10h"][-1] = 99.0                     # isolate the Mid BB rule
    _patch(monkeypatch, stack)
    candles = _flat_candles()
    candles[-1] = _c(100.0, 104.0, 95.0, 99.5, N - 1)   # 99.5 < mid 100.0
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_close_is_below_ma10_high(monkeypatch):
    _patch(monkeypatch, _long_stack())
    candles = _flat_candles()
    candles[-1] = _c(100.0, 104.0, 95.0, 101.0, N - 1)  # 101.0 < ma10h 103.0
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_price_never_pulled_back_into_ma5(monkeypatch):
    _patch(monkeypatch, _long_stack())
    candles = _flat_candles()
    candles[-1] = _c(100.0, 104.0, 98.0, 103.5, N - 1)  # low 98.0 > ma5l 96.0
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_price_is_below_the_ema50(monkeypatch):
    stack = _long_stack()
    stack["ema50"][-1] = 105.0                    # close 103.5 now below it
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_opposing_htf_trend_vetoes_a_long(monkeypatch):
    """Unlike Extreme, Re-entry trades WITH the trend, so the HTF gate applies."""
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N, htf_trend="down")
    assert setup is None


def test_aligned_htf_trend_allows_a_long(monkeypatch):
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N, htf_trend="up")
    assert setup is not None


def test_momentum_leg_excludes_the_current_bar(monkeypatch):
    """The current bar is the pullback. A bar closing outside the band IS the
    momentum candle, not a re-entry into one."""
    stack = _long_stack()
    stack["upper"][N - 5] = 110.0        # no leg among the earlier bars
    stack["upper"][-1] = 99.0            # only the current bar closes outside
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_no_setup_when_the_stop_exceeds_the_atr_cap(monkeypatch):
    _patch(monkeypatch, _long_stack())
    # Risk is 11.0 plus buffer; at ATR 1.0 that is far beyond MAX_STOP_ATR.
    assert detect_setup("BTCUSD", _long_candles(), [1.0] * N) is None


def test_indicators_tag_the_strategy(monkeypatch):
    _patch(monkeypatch, _long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup.indicators["strategy"] == "bbma_reentry"


# --- short ------------------------------------------------------------------

def _short_stack():
    stack = _flat_stack()
    stack["lower"][N - 5] = 101.0                 # bar N-5 closed below it
    stack["mid"][N - MOMENTUM_LOOKBACK] = 102.0   # mid falling
    return stack


def _short_candles():
    candles = _flat_candles()
    # Pullback up into MA5-High (104), closing back below MA10-Low (97).
    candles[-1] = _c(100.0, 105.0, 96.0, 96.5, N - 1)
    return candles


def test_short_fires_on_the_mirror_setup(monkeypatch):
    _patch(monkeypatch, _short_stack())
    setup = detect_setup("BTCUSD", _short_candles(), [ATR] * N)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 96.5
    # max(bar high 105.0, ma10h 103.0) + 0.5 * 5.0
    assert setup.stop_loss == 107.5


def test_opposing_htf_trend_vetoes_a_short(monkeypatch):
    _patch(monkeypatch, _short_stack())
    assert detect_setup("BTCUSD", _short_candles(), [ATR] * N,
                        htf_trend="up") is None


# --- guards -----------------------------------------------------------------

def test_no_setup_below_the_minimum_candle_count(monkeypatch):
    n = MIN_CANDLES - 1
    _patch(monkeypatch, _flat_stack(n))
    assert detect_setup("BTCUSD", _flat_candles(n), [ATR] * n) is None


def test_no_setup_without_an_atr(monkeypatch):
    _patch(monkeypatch, _long_stack())
    assert detect_setup("BTCUSD", _long_candles(), [None] * N) is None


# --- integration against the real stack -------------------------------------

def _walk(n, seed, drift=0.25, vol=1.2):
    rng = random.Random(seed)
    price = 100.0
    out = []
    for i in range(n):
        price = max(1.0, price + drift + rng.gauss(0, vol))
        open_ = price - rng.gauss(0, vol / 3)
        high = max(price, open_) + abs(rng.gauss(0, vol / 2))
        low = min(price, open_) - abs(rng.gauss(0, vol / 2))
        out.append(Candle(i * 3_600_000, open_, high, low, price, 1.0))
    return out


def test_rules_are_satisfiable_against_the_real_stack():
    candles = _walk(900, seed=11)
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr14 = atr(highs, lows, closes, 14)

    setups = []
    for end in range(MIN_CANDLES, len(candles) + 1):
        setup = detect_setup("BTCUSD", candles[:end], atr14[:end])
        if setup is not None:
            setups.append(setup)

    assert setups, "no Re-entry fired across 900 bars — the rules never combine"
    for setup in setups:
        if setup.direction == "long":
            assert setup.stop_loss < setup.entry
        else:
            assert setup.stop_loss > setup.entry
        tp1, _, tp3 = setup.resolved_take_profits()
        risk = abs(setup.entry - setup.stop_loss)
        assert abs(abs(tp1 - setup.entry) - 1.0 * risk) < 1e-6
        assert abs(abs(tp3 - setup.entry) - 3.0 * risk) < 1e-6
