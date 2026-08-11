"""Rule tests for the BBMA Extreme detector.

The stack is monkeypatched with a hand-built flat stack on purpose: these tests
are about the RULES, and hand-fitting a candle series that makes a real LWMA
cross a real Bollinger band tests arithmetic already covered by
tests/core/test_indicators.py and tests/strategies/test_bbma_stack.py.
"""
import random

from signals.analysis.indicators import atr
from signals.models import Candle
from signals.strategies.bbma import extreme
from signals.strategies.bbma.extreme import EXTREME_LOOKBACK, detect_setup
from signals.strategies.bbma.stack import MIN_CANDLES

N = 60
ATR = 2.0

# A stack where nothing has escaped: MA5/MA10 sit inside a 90..110 band.
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
    monkeypatch.setattr(extreme, "bbma_stack", lambda _candles: stack)


# --- short (sell extreme) ---------------------------------------------------

def _short_case(monkeypatch, **stack_edits):
    stack = _flat_stack()
    stack["ma5h"][-3] = 112.0            # MA5-High escaped above the band
    for key, (index, value) in stack_edits.items():
        stack[key][index] = value
    candles = _flat_candles()
    # Rejection bar: pokes above MA5-High (104), closes back below it, bearish,
    # and finishes inside the band.
    candles[-1] = _c(105.0, 105.5, 101.0, 102.0, N - 1)
    _patch(monkeypatch, stack)
    return candles


def test_short_fires_on_a_rejection_after_the_ma_escaped(monkeypatch):
    candles = _short_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 102.0


def test_short_stop_sits_beyond_the_escape_window_high(monkeypatch):
    candles = _short_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    # Highest high across the last EXTREME_LOOKBACK bars is the rejection
    # bar's 105.5, plus STOP_ATR_BUFFER (0.5) * ATR (2.0).
    assert setup.stop_loss == 106.5


def test_short_target_is_the_opposite_ma_pair(monkeypatch):
    """Manual p24 'TP MANDATORY': a sell takes profit on the opposite (Low)
    MA5/MA10 — the nearer of the two is the first level reached going down."""
    candles = _short_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup.take_profit == max(BASE["ma5l"], BASE["ma10l"])


def test_short_later_targets_extend_one_and_two_r_beyond_the_first(monkeypatch):
    candles = _short_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    risk = setup.stop_loss - setup.entry
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp2 - (tp1 - risk)) < 1e-9
    assert abs(tp3 - (tp1 - 2 * risk)) < 1e-9


def test_mandatory_target_may_sit_inside_one_r(monkeypatch):
    """Extreme stops beyond the whole spike but targets a nearby MA, so its
    first target is often sub-1R. Applying Re-entry's 1R floor here removed
    EVERY Extreme setup — the manual calls for taking profit early, not for 1R.

    MA10-Low is lifted to 100 so the target sits 2.0 below the 102 entry
    against a 4.5 risk: 0.44R, well inside the stop.
    """
    candles = _short_case(monkeypatch, ma10l=(-1, 100.0))
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup is not None
    risk = setup.stop_loss - setup.entry
    assert 0 < (setup.entry - setup.take_profit) < risk


def test_target_on_the_wrong_side_of_entry_is_rejected(monkeypatch):
    """A "target" above a short's entry is not a target."""
    candles = _short_case(monkeypatch, ma10l=(-1, 103.0))
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_ma_never_escaped_the_band(monkeypatch):
    stack = _flat_stack()                 # ma5h stays at 104, inside 110
    candles = _flat_candles()
    candles[-1] = _c(105.0, 105.5, 101.0, 102.0, N - 1)
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_bar_closes_outside_the_band(monkeypatch):
    """A close outside the band is momentum, not exhaustion. This is BBMA's own
    invalidation, and it is why the detector needs no bandwidth threshold."""
    candles = _short_case(monkeypatch, upper=(-1, 101.0))
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_bar_closes_beyond_ma5_instead_of_rejecting(monkeypatch):
    stack = _flat_stack()
    stack["ma5h"][-3] = 112.0
    candles = _flat_candles()
    candles[-1] = _c(106.0, 107.0, 104.5, 105.0, N - 1)   # close 105 > ma5h 104
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_bar_never_reached_ma5(monkeypatch):
    stack = _flat_stack()
    stack["ma5h"][-3] = 112.0
    candles = _flat_candles()
    candles[-1] = _c(103.0, 103.5, 101.0, 102.0, N - 1)   # high 103.5 < ma5h 104
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_on_a_bullish_bar(monkeypatch):
    stack = _flat_stack()
    stack["ma5h"][-3] = 112.0
    candles = _flat_candles()
    candles[-1] = _c(101.0, 105.5, 100.5, 102.0, N - 1)   # close > open
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_no_setup_when_the_stop_exceeds_the_atr_cap(monkeypatch):
    candles = _short_case(monkeypatch)
    # Risk is 4.5; at ATR 0.5 that is 9 ATRs, far beyond MAX_STOP_ATR.
    assert detect_setup("BTCUSD", candles, [0.5] * N) is None


def test_escape_older_than_the_lookback_is_ignored(monkeypatch):
    stack = _flat_stack()
    stack["ma5h"][N - EXTREME_LOOKBACK - 1] = 112.0   # one bar too old
    candles = _flat_candles()
    candles[-1] = _c(105.0, 105.5, 101.0, 102.0, N - 1)
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


# --- long (buy extreme) -----------------------------------------------------

def _long_case(monkeypatch):
    stack = _flat_stack()
    stack["ma5l"][-3] = 88.0             # MA5-Low escaped below the band
    candles = _flat_candles()
    candles[-1] = _c(95.0, 99.0, 94.5, 98.0, N - 1)
    _patch(monkeypatch, stack)
    return candles


def test_long_fires_on_the_mirror_setup(monkeypatch):
    candles = _long_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 98.0
    assert setup.stop_loss == 93.5       # 94.5 low - 0.5 * 2.0


def test_long_is_not_suppressed_by_an_opposing_htf_trend(monkeypatch):
    """Extreme is counter-trend by construction. htf_trend is recorded for the
    backtest to analyse, never gated on — pin that so it is not 'fixed' later.
    """
    candles = _long_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N, htf_trend="down")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["htf_trend"] == "down"


def test_adx_is_recorded_but_not_gated(monkeypatch):
    candles = _long_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N, adx14=[55.0] * N)
    assert setup is not None
    assert setup.indicators["adx"] == 55.0


def test_indicators_tag_the_strategy(monkeypatch):
    candles = _long_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup.indicators["strategy"] == "bbma_extreme"


# --- guards -----------------------------------------------------------------

def test_no_setup_below_the_minimum_candle_count(monkeypatch):
    candles = _flat_candles(MIN_CANDLES - 1)
    _patch(monkeypatch, _flat_stack(MIN_CANDLES - 1))
    assert detect_setup("BTCUSD", candles, [ATR] * (MIN_CANDLES - 1)) is None


def test_no_setup_without_an_atr(monkeypatch):
    candles = _short_case(monkeypatch)
    assert detect_setup("BTCUSD", candles, [None] * N) is None


# --- integration against the real stack -------------------------------------

def _walk(n, seed, drift=0.0, vol=1.2):
    """A deterministic random walk with OHLC bars, for satisfiability checks."""
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
    """Guards against a detector that can never fire because the real stack
    never produces the combination the rules ask for."""
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

    assert setups, "no Extreme fired across 900 bars — the rules never combine"
    for setup in setups:
        if setup.direction == "long":
            assert setup.stop_loss < setup.entry
        else:
            assert setup.stop_loss > setup.entry
        tp1, tp2, tp3 = setup.resolved_take_profits()
        risk = abs(setup.entry - setup.stop_loss)
        # TP1 is a structural level beyond entry; TP2/TP3 sit +1R and +2R past it.
        assert abs(tp1 - setup.entry) > 0
        assert abs(abs(tp2 - tp1) - risk) < 1e-6
        assert abs(abs(tp3 - tp1) - 2 * risk) < 1e-6
