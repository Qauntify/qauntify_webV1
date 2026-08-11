"""Rule tests for the BBMA Re-entry detector.

Rules come from docs/strategy_doc; page numbers below refer to the 79-page
manual. The stack is monkeypatched so these exercise the RULES rather than
Bollinger arithmetic already covered by tests/core/test_indicators.py.
"""
import random

from signals.analysis.indicators import atr
from signals.models import Candle
from signals.strategies.bbma import reentry
from signals.strategies.bbma.reentry import SIGNAL_LOOKBACK, detect_setup
from signals.strategies.bbma.stack import MIN_CANDLES

N = 61          # MIN_CANDLES + 1: the setup spans a pullback and a confirm bar
ATR = 5.0
ARM = 55        # an index inside the arming window

# Band kept wide so the structural target clears MIN_STRUCTURAL_R.
BASE = {
    "upper": 120.0, "mid": 100.0, "lower": 80.0,
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


# --- long: the CSM branch ---------------------------------------------------

def _csm_long_stack():
    stack = _flat_stack()
    stack["upper"][ARM] = 99.0        # bar ARM closes 100 > 99 -> CSM
    return stack


def _long_candles():
    candles = _flat_candles()
    # Pullback: dips to MA5-Low (96), closes back above MA10-Low and Mid BB.
    candles[-2] = _c(100.0, 101.0, 95.0, 101.0, N - 2)
    # Confirming second candle closes higher still (p33/p36).
    candles[-1] = _c(101.0, 103.5, 102.0, 103.0, N - 1)
    return candles


def test_long_fires_after_a_momentum_candle(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["trigger"] == "csm"


def test_entry_is_the_second_candle_not_the_pullback(monkeypatch):
    """p33: 'wait a second candle … entry in the second candle'. Entering at
    the pullback's close would front-run the confirmation the manual requires.
    """
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    assert setup.entry == candles[-1].close == 103.0
    assert setup.entry != candles[-2].close


def test_no_setup_when_the_second_candle_does_not_confirm(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    candles[-1] = _c(101.0, 103.5, 100.5, 100.8, N - 1)   # closes below pullback
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


# --- long: the CSAK branch (the fix) ----------------------------------------

def _csak_long_stack():
    """A strong direction candle: close through MA5/MA10 and Mid BB (p31)."""
    stack = _flat_stack()
    stack["ma5h"][ARM] = 98.0
    stack["ma10h"][ARM] = 97.5
    stack["mid"][ARM] = 99.0
    return stack


def test_long_fires_after_a_direction_candle(monkeypatch):
    """p35: re-entry applies after cs direction AND momentum. Arming on CSM
    alone silently discarded this entire branch."""
    _patch(monkeypatch, _csak_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["trigger"] == "csak"


def test_no_setup_without_any_arming_signal(monkeypatch):
    _patch(monkeypatch, _flat_stack())      # neither CSM nor CSAK anywhere
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_arming_signal_must_precede_the_pullback(monkeypatch):
    """The window ends before the pullback bar: a signal ON the pullback is the
    move itself, not a prior direction to re-enter."""
    stack = _flat_stack()
    stack["upper"][N - 2] = 99.0            # on the pullback bar, not before
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_arming_signal_older_than_the_lookback_is_ignored(monkeypatch):
    stack = _flat_stack()
    stack["upper"][N - 3 - SIGNAL_LOOKBACK] = 99.0     # one bar too old
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


# --- the zone floor ---------------------------------------------------------

def test_pullback_must_reach_the_ma5_zone(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    candles[-2] = _c(100.0, 101.0, 98.0, 101.0, N - 2)   # low 98 > ma5l 96
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_pullback_closing_through_the_zone_floor_is_rejected(monkeypatch):
    """p33: 'candle close can not get past a 5-/A10'. The floor for a buy is
    MA10-Low (97) — an earlier version tested MA10-HIGH and so rejected valid
    re-entries that merely closed below the zone's ceiling."""
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    candles[-2] = _c(100.0, 101.0, 95.0, 96.5, N - 2)    # close 96.5 < ma10l 97
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


def test_close_between_ma10_low_and_ma10_high_still_qualifies(monkeypatch):
    """101 sits above MA10-Low (97) and below MA10-High (103). The documented
    rule accepts it; the previous MA10-High test did not."""
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    assert 97.0 < candles[-2].close < 103.0
    assert detect_setup("BTCUSD", candles, [ATR] * N) is not None


def test_pullback_closing_below_mid_bb_is_rejected(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    candles = _long_candles()
    candles[-2] = _c(100.0, 101.0, 95.0, 99.0, N - 2)    # 99 < mid 100
    assert detect_setup("BTCUSD", candles, [ATR] * N) is None


# --- targets ----------------------------------------------------------------

def test_first_target_is_the_documented_ma_pair(monkeypatch):
    """Brocamkh p4: "buy TP at Ma5/10 High". Targeting the band instead — an
    earlier interpretation — dropped the TP1 hit rate from ~75% to ~43% and
    turned +531R into -53R over 8.87 years."""
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup.take_profit == max(BASE["ma5h"], BASE["ma10h"])


def test_later_targets_extend_one_and_two_r_beyond_the_first(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    risk = setup.entry - setup.stop_loss
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp2 - (tp1 + risk)) < 1e-9
    assert abs(tp3 - (tp1 + 2 * risk)) < 1e-9


def test_mandatory_target_may_sit_inside_one_r(monkeypatch):
    """Like Extreme, the MA target sits close to price. Requiring 1R here
    discards exactly the setups that pay."""
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup is not None
    risk = setup.entry - setup.stop_loss
    assert 0 < (setup.take_profit - setup.entry) < risk


def test_target_on_the_wrong_side_of_entry_is_rejected(monkeypatch):
    stack = _csm_long_stack()
    stack["ma5h"][-1] = 102.0
    stack["ma10h"][-1] = 101.0          # both below the 103 entry
    _patch(monkeypatch, stack)
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N) is None


def test_stop_sits_below_the_pullback_low(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    # min(pullback low 95, confirm low 102, ma10l 97) - 0.5 * ATR
    assert setup.stop_loss == 95.0 - 0.5 * ATR


# --- gates ------------------------------------------------------------------

def test_opposing_htf_trend_vetoes_a_long(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N,
                        htf_trend="down") is None


def test_aligned_htf_trend_allows_a_long(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    assert detect_setup("BTCUSD", _long_candles(), [ATR] * N,
                        htf_trend="up") is not None


def test_no_setup_when_the_stop_exceeds_the_atr_cap(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    assert detect_setup("BTCUSD", _long_candles(), [1.0] * N) is None


def test_indicators_tag_the_strategy(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
    setup = detect_setup("BTCUSD", _long_candles(), [ATR] * N)
    assert setup.indicators["strategy"] == "bbma_reentry"


# --- short mirror -----------------------------------------------------------

def _short_stack():
    stack = _flat_stack()
    stack["lower"][ARM] = 101.0             # bar ARM closes 100 < 101 -> CSM
    return stack


def _short_candles():
    candles = _flat_candles()
    candles[-2] = _c(100.0, 105.0, 99.0, 99.0, N - 2)
    candles[-1] = _c(99.0, 99.5, 96.5, 97.0, N - 1)
    return candles


def test_short_fires_on_the_mirror_setup(monkeypatch):
    _patch(monkeypatch, _short_stack())
    setup = detect_setup("BTCUSD", _short_candles(), [ATR] * N)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 97.0
    assert setup.stop_loss == 105.0 + 0.5 * ATR
    assert setup.take_profit == min(BASE["ma5l"], BASE["ma10l"])


def test_opposing_htf_trend_vetoes_a_short(monkeypatch):
    _patch(monkeypatch, _short_stack())
    assert detect_setup("BTCUSD", _short_candles(), [ATR] * N,
                        htf_trend="up") is None


# --- guards -----------------------------------------------------------------

def test_no_setup_below_the_minimum_candle_count(monkeypatch):
    n = MIN_CANDLES
    _patch(monkeypatch, _flat_stack(n))
    assert detect_setup("BTCUSD", _flat_candles(n), [ATR] * n) is None


def test_no_setup_without_an_atr(monkeypatch):
    _patch(monkeypatch, _csm_long_stack())
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
    for end in range(MIN_CANDLES + 1, len(candles) + 1):
        setup = detect_setup("BTCUSD", candles[:end], atr14[:end])
        if setup is not None:
            setups.append(setup)

    assert setups, "no Re-entry fired across 900 bars — the rules never combine"
    for setup in setups:
        risk = abs(setup.entry - setup.stop_loss)
        tp1, tp2, tp3 = setup.resolved_take_profits()
        if setup.direction == "long":
            assert setup.stop_loss < setup.entry
            assert tp1 > setup.entry
        else:
            assert setup.stop_loss > setup.entry
            assert tp1 < setup.entry
        # Structural first target, then +1R and +2R beyond it.
        assert abs(tp1 - setup.entry) > 0
        assert abs(abs(tp2 - tp1) - risk) < 1e-6
        assert abs(abs(tp3 - tp1) - 2 * risk) < 1e-6
