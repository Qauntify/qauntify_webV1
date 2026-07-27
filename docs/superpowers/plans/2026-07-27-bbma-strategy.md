# BBMA Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two BBMA (Bollinger Bands + Moving Average) detectors — `bbma_extreme` (mean reversion) and `bbma_reentry` (trend continuation) — to the pluggable strategy system, and measure both with the existing backtester.

**Architecture:** One package `signals/strategies/bbma/` holding a shared indicator stack plus two independent detectors, registered as two separate strategy keys so each is measured and gated on its own. One new pure indicator primitive (`bollinger`), one data-layer correction (gold's 4h series is currently hourly), and a net-of-cost R column added to the backtester because BBMA's tight ladder is cost-sensitive.

**Tech Stack:** Python 3.12, pytest. No new dependencies — `lwma` and `ema` already exist in `signals/indicators.py`, and `r_model` already owns the cost model.

**Spec:** `docs/superpowers/specs/2026-07-27-bbma-strategy-design.md`

**Run tests with:** `.venv/bin/python -m pytest` (the `.venv/bin/pytest` shim is broken in this project — always use `-m pytest`).

---

## File Structure

| File | Responsibility |
|---|---|
| `signals/indicators.py` (modify) | add `bollinger()` — pure primitive, same contract as its neighbours |
| `signals/market_client.py` (modify) | fold Yahoo's hourly gold series into true 4h buckets |
| `signals/strategies/bbma/__init__.py` (create) | export `detect_extreme`, `detect_reentry` |
| `signals/strategies/bbma/stack.py` (create) | the 5-line BBMA stack + shared constants + guards |
| `signals/strategies/bbma/extreme.py` (create) | mean-reversion detector |
| `signals/strategies/bbma/reentry.py` (create) | continuation detector |
| `signals/strategies/router.py` (modify) | two dispatch branches |
| `signals/models.py` (modify) | two entries in `SIGNAL_STRATEGIES` |
| `signals/backtest.py` (modify) | `net_r_multiples()` + net stats + two registry entries |
| `scripts/bbma_report.py` (create) | the timeframe × symbol sweep |
| `tests/core/test_indicators.py` (modify) | `bollinger` correctness |
| `tests/clients/test_market_client.py` (modify) | gold 4h resample |
| `tests/strategies/test_bbma_stack.py` (create) | stack alignment |
| `tests/strategies/test_bbma_extreme.py` (create) | Extreme rule logic + integration |
| `tests/strategies/test_bbma_reentry.py` (create) | Re-entry rule logic + integration |
| `tests/core/test_backtest.py` (modify) | net-of-cost arithmetic |
| `tests/core/test_bbma_report.py` (create) | sweep's confluence mapping |
| `docs/bbma-backtest-results.md` (create) | the measured outcome |

**Testing strategy note (read before Task 4).** The detector rule tests
monkeypatch `bbma_stack` with a hand-built flat stack. This is deliberate: it
separates *rule logic* (what those tests are for) from *Bollinger arithmetic*
(covered by Task 1) and *stack assembly* (covered by Task 3). Hand-computing a
candle series that makes a real LWMA cross a real Bollinger band is fragile
fixture arithmetic that tests nothing about the rules. Each detector also gets
one integration test against a real generated series, asserting satisfiability
and geometry rather than a specific bar.

---

## Task 1: `bollinger` indicator primitive

**Files:**
- Modify: `signals/indicators.py`
- Test: `tests/core/test_indicators.py`

- [ ] **Step 1: Write the failing tests**

Add to the top import line of `tests/core/test_indicators.py`:

```python
from signals.indicators import adx, atr, bollinger, ema, lwma, macd_histogram, rsi
```

Append these tests to the file:

```python
def test_bollinger_shorter_than_period_is_all_none():
    upper, mid, lower = bollinger([1.0, 2.0, 3.0], 20)
    assert upper == [None, None, None]
    assert mid == [None, None, None]
    assert lower == [None, None, None]


def test_bollinger_constant_series_has_zero_width():
    values = [50.0] * 30
    upper, mid, lower = bollinger(values, 20)
    assert upper[:19] == [None] * 19
    for u, m, l in zip(upper[19:], mid[19:], lower[19:]):
        assert abs(u - 50.0) < 1e-9
        assert abs(m - 50.0) < 1e-9
        assert abs(l - 50.0) < 1e-9


def test_bollinger_uses_population_sigma():
    """1..20 has population variance (n^2-1)/12 = 33.25, so sigma = 5.7663.

    Sample sigma would widen the band by sqrt(20/19) — a material difference at
    period 20, and MT4/TradingView (the charts BBMA is drawn on) use the
    population form.
    """
    values = [float(i) for i in range(1, 21)]
    upper, mid, lower = bollinger(values, 20, 2.0)
    assert abs(mid[-1] - 10.5) < 1e-9
    assert abs(upper[-1] - 22.0325626) < 1e-6
    assert abs(lower[-1] - (-1.0325626)) < 1e-6


def test_bollinger_series_are_aligned_to_input():
    values = [float(i % 7) for i in range(40)]
    upper, mid, lower = bollinger(values, 20)
    assert len(upper) == len(mid) == len(lower) == 40


def test_bollinger_rejects_non_positive_period():
    with pytest.raises(ValueError):
        bollinger([1.0, 2.0], 0)
```

`tests/core/test_indicators.py` may not import `pytest` yet. If it does not, add
`import pytest` as the first line of the file.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/test_indicators.py -k bollinger -v
```

Expected: FAIL — `ImportError: cannot import name 'bollinger'`.

- [ ] **Step 3: Implement `bollinger`**

Add to `signals/indicators.py`, after `lwma` and before `chandelier_exit`:

```python
def bollinger(values, period=20, num_std=2.0):
    """Bollinger Bands: (upper, mid, lower), each aligned 1:1 with `values`.

    Mid is the simple moving average. The band offset uses the POPULATION
    standard deviation over the same window (divide by n), matching the
    MT4/TradingView convention — sample sigma would widen the bands by
    sqrt(n/(n-1)), which is not a rounding error at period 20.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    if n < period:
        return [None] * n, [None] * n, [None] * n
    upper = [None] * (period - 1)
    mid = [None] * (period - 1)
    lower = [None] * (period - 1)
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / period
        offset = num_std * variance ** 0.5
        mid.append(mean)
        upper.append(mean + offset)
        lower.append(mean - offset)
    return upper, mid, lower
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/test_indicators.py -v
```

Expected: PASS, including all pre-existing indicator tests.

- [ ] **Step 5: Commit**

```bash
git add signals/indicators.py tests/core/test_indicators.py
git commit -m "feat(indicators): add Bollinger Bands with population sigma"
```

---

## Task 2: Fix gold's 4h series

`YAHOO_INTERVAL["4h"] = ("1h", "6mo")` means `fetch_candles("XAUUSD", "4h")`
returns hourly candles. Measured: 2,829 bars at a median 60-minute gap. Every
strategy's 4h HTF confluence for gold is affected, not just BBMA.

**Files:**
- Modify: `signals/market_client.py`
- Test: `tests/clients/test_market_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/clients/test_market_client.py`:

```python
# Eight hourly gold bars spanning exactly two 4h buckets. 1720008000 is a
# multiple of 14400, so the bucket boundaries are unambiguous.
HOURLY_GOLD_PAYLOAD = {
    "chart": {
        "result": [
            {
                "timestamp": [1720008000 + 3600 * i for i in range(8)],
                "indicators": {
                    "quote": [
                        {
                            "open": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
                            "high": [15.0, 16.0, 17.0, 18.0, 20.0, 21.0, 22.0, 23.0],
                            "low": [9.0, 8.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
                            "close": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0],
                            "volume": [1, 2, 3, 4, 5, 6, 7, 8],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


def test_gold_4h_folds_the_hourly_source_into_true_4h_bars():
    """Yahoo has no 4h gold series, so a 4h request is served hourly and must
    be aggregated — otherwise a '4h' backtest silently runs on 1h data."""
    session = FakeSession(HOURLY_GOLD_PAYLOAD)
    candles = fetch_candles("XAUUSD", "4h", 100, session=session)

    assert len(candles) == 2
    assert candles[1].open_time - candles[0].open_time == 4 * 3600 * 1000

    first = candles[0]
    assert first.open_time == 1720008000 * 1000
    assert first.open == 10.0     # first open of the bucket
    assert first.high == 18.0     # max high
    assert first.low == 8.0       # min low
    assert first.close == 14.0    # last close
    assert first.volume == 10.0   # summed

    second = candles[1]
    assert second.open == 14.0
    assert second.high == 23.0
    assert second.low == 13.0
    assert second.close == 18.0
    assert second.volume == 26.0


def test_gold_1h_is_not_resampled():
    session = FakeSession(HOURLY_GOLD_PAYLOAD)
    candles = fetch_candles("XAUUSD", "1h", 100, session=session)
    assert len(candles) == 8


def test_gold_4h_buckets_are_epoch_aligned_not_fetch_aligned():
    """Boundaries must not depend on where the fetch happened to start, or the
    same bar lands in different buckets on consecutive runs."""
    session = FakeSession(HOURLY_GOLD_PAYLOAD)
    candles = fetch_candles("XAUUSD", "4h", 100, session=session)
    for candle in candles:
        assert (candle.open_time // 1000) % (4 * 3600) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/clients/test_market_client.py -k gold_4h -v
```

Expected: FAIL — `assert 8 == 2`, because the hourly bars are returned as-is.

- [ ] **Step 3: Implement the resample**

Add to `signals/market_client.py`, immediately before `_fetch_yahoo_gold_candles`:

```python
def _resample(candles, minutes):
    """Fold candles into `minutes`-wide buckets aligned to the UTC epoch.

    Yahoo publishes no 4h gold series, so a 4h request is served from its
    hourly one and aggregated here. Buckets are keyed on floor(open_time /
    width) rather than on the first bar of the response, so the same wall-clock
    bar always lands in the same bucket regardless of when the fetch ran.

    A partial trailing bucket is kept — callers drop the still-forming bar
    themselves (backtest.py does this with `[:-1]`), and silently discarding it
    here would hide a bar they expect to see.
    """
    width = minutes * 60_000
    out: list[Candle] = []
    for candle in candles:
        bucket = candle.open_time - (candle.open_time % width)
        if out and out[-1].open_time == bucket:
            prev = out[-1]
            out[-1] = Candle(
                open_time=bucket,
                open=prev.open,
                high=max(prev.high, candle.high),
                low=min(prev.low, candle.low),
                close=candle.close,
                volume=prev.volume + candle.volume,
            )
        else:
            out.append(Candle(
                open_time=bucket,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            ))
    return out
```

Then change the final `return candles` of `_fetch_yahoo_gold_candles` to:

```python
    # YAHOO_INTERVAL maps "4h" to Yahoo's hourly series because no 4h gold
    # series exists. Without this fold a 4h request returns 1h bars.
    if interval == "4h":
        candles = _resample(candles, INTERVAL_MINUTES["4h"])
    return candles
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/clients/test_market_client.py -v
```

Expected: PASS, all pre-existing market-client tests included.

- [ ] **Step 5: Verify against the live source**

```bash
.venv/bin/python -c "
import statistics, requests
from signals.market_client import fetch_candles
c = fetch_candles('XAUUSD', '4h', 5000, session=requests.Session())
gaps = [(b.open_time-a.open_time)/60000 for a,b in zip(c, c[1:])]
print('bars', len(c), 'median gap', statistics.median(gaps))
"
```

Expected: `median gap 240.0` (it was 60.0 before this task).

- [ ] **Step 6: Commit**

```bash
git add signals/market_client.py tests/clients/test_market_client.py
git commit -m "fix(market): fold Yahoo's hourly gold series into true 4h bars"
```

---

## Task 3: BBMA indicator stack

**Files:**
- Create: `signals/strategies/bbma/__init__.py`, `signals/strategies/bbma/stack.py`
- Test: `tests/strategies/test_bbma_stack.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_bbma_stack.py`:

```python
"""The BBMA stack must stay aligned to its candles — every detector indexes
these series positionally against bars."""
from signals.models import Candle
from signals.strategies.bbma.stack import (
    MAX_STOP_ATR,
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

KEYS = {"upper", "mid", "lower", "ma5h", "ma5l", "ma10h", "ma10l", "ema50"}


def _candles(n):
    return [
        Candle(open_time=i * 3_600_000, open=100.0 + i, high=101.0 + i,
               low=99.0 + i, close=100.5 + i, volume=1.0)
        for i in range(n)
    ]


def test_stack_has_every_expected_series():
    assert set(bbma_stack(_candles(80))) == KEYS


def test_every_series_is_aligned_to_the_candles():
    candles = _candles(80)
    stack = bbma_stack(candles)
    for key, series in stack.items():
        assert len(series) == len(candles), key


def test_ma5_is_applied_to_highs_and_lows_not_closes():
    """BBMA's MA5 High/Low read the bar's extremes. Reading closes instead
    would silently collapse the MA5 pair into one line."""
    stack = bbma_stack(_candles(80))
    assert stack["ma5h"][-1] > stack["ma5l"][-1]


def test_fast_ma_leads_slow_ma_in_an_uptrend():
    stack = bbma_stack(_candles(80))
    assert stack["ma5h"][-1] > stack["ma10h"][-1]


def test_stack_is_not_ready_during_warm_up():
    stack = bbma_stack(_candles(30))  # below the EMA50 warm-up
    assert stack_ready(stack) is False


def test_stack_is_ready_once_every_series_has_warmed_up():
    stack = bbma_stack(_candles(MIN_CANDLES))
    assert stack_ready(stack) is True


def test_risk_ok_accepts_a_stop_within_the_atr_cap():
    assert risk_ok(100.0, 98.0, 2.0) is True      # 1.0 ATR


def test_risk_ok_rejects_a_stop_beyond_the_atr_cap():
    assert risk_ok(100.0, 90.0, 2.0) is False     # 5.0 ATR > MAX_STOP_ATR


def test_risk_ok_rejects_a_non_positive_atr():
    assert risk_ok(100.0, 98.0, 0.0) is False


def test_stop_buffer_and_cap_are_the_documented_values():
    assert STOP_ATR_BUFFER == 0.5
    assert MAX_STOP_ATR == 2.5
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_stack.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.bbma'`.

- [ ] **Step 3: Implement the package**

Create `signals/strategies/bbma/stack.py`:

```python
"""The BBMA indicator stack — the five lines every BBMA setup is read against.

Settings are the canonical MT4 ones from the Oma Ally material: Bollinger Bands
20/2 on close, MA5 and MA10 as LINEAR WEIGHTED averages applied separately to
highs and lows, and EMA50 on close.

The moving averages being linear weighted is not incidental. The whole system
is taught and charted on LWMA, so `lwma` is the correct primitive here and
substituting `ema` or a simple average would move every level the rules test
against.
"""
from signals.indicators import bollinger, ema, lwma

BB_PERIOD = 20
BB_DEV = 2.0
MA_FAST = 5
MA_SLOW = 10
EMA_TREND = 50

# EMA50 warm-up plus headroom for the detectors' lookback windows.
MIN_CANDLES = 60
# Stops sit this many ATRs beyond the structural level — obvious levels get
# wick-hunted, so resting exactly on one is a donation.
STOP_ATR_BUFFER = 0.5
# Reject setups whose stop is farther than this many ATRs from entry.
MAX_STOP_ATR = 2.5


def bbma_stack(candles):
    """Return the eight aligned BBMA series for `candles` as a dict.

    Keys: upper, mid, lower, ma5h, ma5l, ma10h, ma10l, ema50. Every value is a
    list aligned 1:1 with `candles`, None-padded through its own warm-up.
    """
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    upper, mid, lower = bollinger(closes, BB_PERIOD, BB_DEV)
    return {
        "upper": upper,
        "mid": mid,
        "lower": lower,
        "ma5h": lwma(highs, MA_FAST),
        "ma5l": lwma(lows, MA_FAST),
        "ma10h": lwma(highs, MA_SLOW),
        "ma10l": lwma(lows, MA_SLOW),
        "ema50": ema(closes, EMA_TREND),
    }


def stack_ready(stack):
    """True when every series carries a value on the latest bar."""
    return all(series[-1] is not None for series in stack.values())


def risk_ok(entry, stop, atr_value):
    """True when the stop is within MAX_STOP_ATR of entry.

    Side is NOT checked here — each detector asserts its own direction, the
    same split sr_zone uses.
    """
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR
```

Create `signals/strategies/bbma/__init__.py`:

```python
"""BBMA (Bollinger Bands + Moving Average) — two setups from the Oma Ally
playbook, registered as separate strategies because they are opposite trades:
`extreme` fades a move, `reentry` follows it.
"""
from signals.strategies.bbma.extreme import detect_setup as detect_extreme
from signals.strategies.bbma.reentry import detect_setup as detect_reentry

__all__ = ["detect_extreme", "detect_reentry"]
```

Because `__init__.py` imports both detectors, create empty placeholders so this
task's tests can run — Tasks 4 and 5 fill them in:

```bash
printf 'def detect_setup(*args, **kwargs):\n    return None\n' > signals/strategies/bbma/extreme.py
printf 'def detect_setup(*args, **kwargs):\n    return None\n' > signals/strategies/bbma/reentry.py
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_stack.py -v
```

Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/bbma/ tests/strategies/test_bbma_stack.py
git commit -m "feat(bbma): add the shared BBMA indicator stack"
```

---

## Task 4: `bbma_extreme` detector

**Files:**
- Modify: `signals/strategies/bbma/extreme.py`
- Test: `tests/strategies/test_bbma_extreme.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/strategies/test_bbma_extreme.py`:

```python
"""Rule tests for the BBMA Extreme detector.

The stack is monkeypatched with a hand-built flat stack on purpose: these tests
are about the RULES, and hand-fitting a candle series that makes a real LWMA
cross a real Bollinger band tests arithmetic already covered by
tests/core/test_indicators.py and tests/strategies/test_bbma_stack.py.
"""
import random

from signals.indicators import atr
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


def test_short_uses_the_scalp_ladder(monkeypatch):
    """BBMA calls Extreme an unconfirmed reversal and takes profit early —
    0.5/1/1.5R, not the engine's usual 1/2/3R."""
    candles = _short_case(monkeypatch)
    setup = detect_setup("BTCUSD", candles, [ATR] * N)
    risk = setup.stop_loss - setup.entry          # 4.5
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp1 - (102.0 - 0.5 * risk)) < 1e-9
    assert abs(tp2 - (102.0 - 1.0 * risk)) < 1e-9
    assert abs(tp3 - (102.0 - 1.5 * risk)) < 1e-9


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
        assert abs(abs(tp1 - setup.entry) - 0.5 * risk) < 1e-6
        assert abs(abs(tp3 - setup.entry) - 1.5 * risk) < 1e-6
```

**If `test_rules_are_satisfiable_against_the_real_stack` finds zero setups**,
the fixture, not the detector, is at fault. Try `seed=23`, then `seed=47`, then
`vol=2.0`, and leave a comment recording which was used. Do **not** weaken the
assertion or the detector to make it pass.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_extreme.py -v
```

Expected: FAIL — `ImportError: cannot import name 'EXTREME_LOOKBACK'` (the
placeholder from Task 3 has no constants).

- [ ] **Step 3: Implement the detector**

Replace `signals/strategies/bbma/extreme.py` entirely:

```python
"""BBMA Extreme — mean reversion off a Bollinger Band escape.

The setup: MA5 (linear weighted, on highs for a sell / lows for a buy) escapes
outside the band, then price rejects back inside. BBMA treats this as an early
reversal signal and explicitly as a scalp — the doctrine is to take profit
quickly because direction is not yet confirmed, which is why the ladder here is
0.5/1/1.5R rather than the engine's usual 1/2/3R.

There is deliberately NO band-expansion test. BBMA invalidates an Extreme when
the candle closes OUTSIDE an expanding band (that is momentum, not exhaustion)
and validates it when the candle closes back inside. Requiring the close back
inside therefore excludes the momentum case by construction — no invented
bandwidth threshold, and nothing to overfit.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

# How far back the MA may have escaped the band and still count.
EXTREME_LOOKBACK = 6
# Scalp ladder — an unconfirmed reversal is banked early.
EXTREME_TP1_R = 0.5
EXTREME_TP2_R = 1.0
EXTREME_TP3_R = 1.5


def _indicators(side, stack, atr_value, adx14, htf_trend):
    out = {
        "strategy": "bbma_extreme",
        "side": side,
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "atr": atr_value,
    }
    # Recorded, never gated — see detect_setup's docstring.
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _escaped(ma_series, band_series, window, above):
    """True when the MA sat outside the band on any bar of `window`."""
    for i in window:
        ma, band = ma_series[i], band_series[i]
        if ma is None or band is None:
            continue
        if (ma > band) if above else (ma < band):
            return True
    return False


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a BBMA Extreme rejection, else None.

    `adx14` and `htf_trend` are RECORDED into the setup's indicators but never
    gated on. Extreme is counter-trend by construction, so a trend filter would
    veto nearly every instance of it; carrying the values instead lets the
    backtest answer afterwards whether such a gate would have helped, rather
    than guessing now. This is deliberate — see the design spec.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(candles)
    if not stack_ready(stack):
        return None

    bar = candles[-1]
    n = len(candles)
    # Includes the current bar: the rejecting bar may itself still have its MA
    # outside the band.
    window = range(n - EXTREME_LOOKBACK, n)
    recent = candles[-EXTREME_LOOKBACK:]
    ma5h, ma5l = stack["ma5h"][-1], stack["ma5l"][-1]

    if (_escaped(stack["ma5h"], stack["upper"], window, above=True)
            and bar.close < stack["upper"][-1]
            and bar.close < bar.open
            and bar.high >= ma5h
            and bar.close < ma5h):
        stop = max(c.high for c in recent) + STOP_ATR_BUFFER * atr_value
        if stop > bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(
                bar.close, stop, "short",
                r1=EXTREME_TP1_R, r2=EXTREME_TP2_R, r3=EXTREME_TP3_R,
            )
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("upper", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    if (_escaped(stack["ma5l"], stack["lower"], window, above=False)
            and bar.close > stack["lower"][-1]
            and bar.close > bar.open
            and bar.low <= ma5l
            and bar.close > ma5l):
        stop = min(c.low for c in recent) - STOP_ATR_BUFFER * atr_value
        if stop < bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(
                bar.close, stop, "long",
                r1=EXTREME_TP1_R, r2=EXTREME_TP2_R, r3=EXTREME_TP3_R,
            )
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("lower", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_extreme.py -v
```

Expected: PASS (17 tests).

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/bbma/extreme.py tests/strategies/test_bbma_extreme.py
git commit -m "feat(bbma): add the Extreme mean-reversion detector"
```

---

## Task 5: `bbma_reentry` detector

**Files:**
- Modify: `signals/strategies/bbma/reentry.py`
- Test: `tests/strategies/test_bbma_reentry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/strategies/test_bbma_reentry.py`:

```python
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
```

Same fixture rule as Task 4: if the integration test finds zero setups, try
`seed=23`, then `seed=47`, then `drift=0.4`. Never weaken the assertion.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_reentry.py -v
```

Expected: FAIL — `ImportError: cannot import name 'MOMENTUM_LOOKBACK'`.

- [ ] **Step 3: Implement the detector**

Replace `signals/strategies/bbma/reentry.py` entirely:

```python
"""BBMA Re-entry — trend continuation off the MA5/MA10 pullback.

The setup BBMA sources unanimously call the safest: after a momentum leg, price
pulls back into the MA5/MA10 zone and holds it. For a buy, the bar's low dips
below MA5-Low while its close stays above MA10-High, and the close must not
pass back through the MA10 / Mid BB confluence.

Rule 2 (Mid BB rising) stands in for BBMA's "vertical vs horizontal band"
distinction. The alternative — a bandwidth-expansion threshold — would need a
number no source specifies, so it would be fitted to whatever data we tested it
on. Mid-BB slope captures the same direction with no free parameter, reusing a
lookback the rules already have.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

# How far back the momentum leg may sit, and the span the Mid BB slope is
# measured over.
MOMENTUM_LOOKBACK = 10


def _indicators(side, stack, atr_value, adx14, htf_trend):
    out = {
        "strategy": "bbma_reentry",
        "side": side,
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "ma10h": stack["ma10h"][-1],
        "ma10l": stack["ma10l"][-1],
        "ema50": stack["ema50"][-1],
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _closed_outside(candles, band, window, above):
    """True when any bar of `window` closed beyond its band value."""
    for i in window:
        level = band[i]
        if level is None:
            continue
        if (candles[i].close > level) if above else (candles[i].close < level):
            return True
    return False


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a BBMA Re-entry pullback, else None.

    `htf_trend` IS gated here — unlike Extreme, this is a with-trend trade, so
    a long against a "down" higher timeframe is refused.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(candles)
    if not stack_ready(stack):
        return None

    n = len(candles)
    mid_then = stack["mid"][n - MOMENTUM_LOOKBACK]
    if mid_then is None:
        return None

    bar = candles[-1]
    mid, ema50 = stack["mid"][-1], stack["ema50"][-1]
    ma5h, ma5l = stack["ma5h"][-1], stack["ma5l"][-1]
    ma10h, ma10l = stack["ma10h"][-1], stack["ma10l"][-1]
    # Excludes the current bar: that bar is the pullback, and a bar closing
    # outside the band is the momentum candle rather than a re-entry into one.
    leg = range(n - MOMENTUM_LOOKBACK, n - 1)

    if (htf_trend != "down"
            and _closed_outside(candles, stack["upper"], leg, above=True)
            and mid > mid_then
            and bar.close > ema50
            and bar.low <= ma5l
            and bar.close >= ma10h
            and bar.close > mid):
        stop = min(bar.low, ma10l) - STOP_ATR_BUFFER * atr_value
        if stop < bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "long")
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("support", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    if (htf_trend != "up"
            and _closed_outside(candles, stack["lower"], leg, above=False)
            and mid < mid_then
            and bar.close < ema50
            and bar.high >= ma5h
            and bar.close <= ma10l
            and bar.close < mid):
        stop = max(bar.high, ma10h) + STOP_ATR_BUFFER * atr_value
        if stop > bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "short")
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("resistance", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_reentry.py -v
```

Expected: PASS (19 tests).

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/bbma/reentry.py tests/strategies/test_bbma_reentry.py
git commit -m "feat(bbma): add the Re-entry continuation detector"
```

---

## Task 6: Register both strategies

**Files:**
- Modify: `signals/models.py:105`, `signals/strategies/router.py`
- Test: `tests/strategies/test_bbma_router.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_bbma_router.py`:

```python
"""Both BBMA keys must be dispatchable, and must NOT leak into the admin
dropdown — they have no session and no migration entry."""
from signals.models import (
    ADMIN_SELECTABLE_STRATEGIES,
    Candle,
    SIGNAL_STRATEGIES,
    TRADING_SESSIONS,
)
from signals.strategies import detect_setup
from signals.strategies.bbma import detect_extreme, detect_reentry
from signals.strategies.bbma.stack import MIN_CANDLES


def _flat_candles(n):
    """Flat bars — no setup should fire, so both paths return None and the
    assertion is about the router reaching the right detector, not about the
    rules. Defined here rather than imported from another test module:
    tests/strategies has no __init__.py and nothing else in this suite imports
    across test files.
    """
    return [
        Candle(open_time=i * 3_600_000, open=100.0, high=100.5, low=99.5,
               close=100.0, volume=1.0)
        for i in range(n)
    ]


def _dispatch(strategy, candles, atr14):
    """Call the router the way backtest.py does."""
    return detect_setup(
        strategy, "BTCUSD", candles,
        [None] * len(candles), [None] * len(candles), [None] * len(candles),
        [None] * len(candles), atr14,
        adx14=None, htf_trend=None, h1_candles=None,
    )


def test_both_keys_are_registered():
    assert "bbma_extreme" in SIGNAL_STRATEGIES
    assert "bbma_reentry" in SIGNAL_STRATEGIES


def test_neither_key_is_admin_selectable():
    """Adding one would need the bot_settings CHECK constraint migration and
    the web dropdown to change with it — out of scope until one is promoted."""
    assert "bbma_extreme" not in ADMIN_SELECTABLE_STRATEGIES
    assert "bbma_reentry" not in ADMIN_SELECTABLE_STRATEGIES


def test_neither_key_is_pinned_to_a_live_session():
    pinned = {s.strategy for s in TRADING_SESSIONS if s.strategy}
    assert "bbma_extreme" not in pinned
    assert "bbma_reentry" not in pinned


def test_router_reaches_the_extreme_detector():
    candles = _flat_candles(MIN_CANDLES)
    atr14 = [2.0] * MIN_CANDLES
    assert _dispatch("bbma_extreme", candles, atr14) == detect_extreme(
        "BTCUSD", candles, atr14)


def test_router_reaches_the_reentry_detector():
    candles = _flat_candles(MIN_CANDLES)
    atr14 = [2.0] * MIN_CANDLES
    assert _dispatch("bbma_reentry", candles, atr14) == detect_reentry(
        "BTCUSD", candles, atr14)


def test_unknown_strategy_still_falls_back_to_ema_cross(capsys):
    """The BBMA branches must not swallow the router's existing fallback."""
    candles = _flat_candles(MIN_CANDLES)
    _dispatch("nonsense_strategy", candles, [2.0] * MIN_CANDLES)
    assert "Unknown signal_strategy" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_router.py -v
```

Expected: FAIL — `test_both_keys_are_registered` asserts False.

- [ ] **Step 3: Register the strategies**

In `signals/models.py`, replace line 105:

```python
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry")
```

In `signals/strategies/router.py`, add to the imports (keeping them alphabetical):

```python
from signals.strategies.bbma import detect_extreme, detect_reentry
```

and add these branches immediately before the `if strategy == "sr_zone":` branch:

```python
    if strategy == "bbma_extreme":
        return detect_extreme(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
    if strategy == "bbma_reentry":
        return detect_reentry(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_bbma_router.py tests/core/test_strategy_choices.py -v
```

Expected: PASS. `test_strategy_choices.py` must still pass — it pins
`ADMIN_SELECTABLE_STRATEGIES` against the migration and the web dropdown, and
adding to `SIGNAL_STRATEGIES` alone keeps that subset relationship intact.

- [ ] **Step 5: Commit**

```bash
git add signals/models.py signals/strategies/router.py tests/strategies/test_bbma_router.py
git commit -m "feat(bbma): register both BBMA keys with the strategy router"
```

---

## Task 7: Net-of-cost R in the backtester

Extreme's TP1 sits at 0.5R of a deliberately tight stop, and cost expressed in
R scales inversely with stop distance. A gross-only number would flatter it —
that same effect separated the losing 15m `sr_limit` variant from the winning
1h one.

**Files:**
- Modify: `signals/backtest.py`
- Test: `tests/core/test_backtest.py`

- [ ] **Step 1: Write the failing tests**

Add `net_r_multiples` to the existing import block at the top of
`tests/core/test_backtest.py`:

```python
from signals.backtest import (
    htf_trend_series,
    net_r_multiples,
    realized_r,
    scaled_r,
    simulate_scaled,
    simulate_trade,
    summarize,
)
```

Append these tests:

```python
def test_net_r_subtracts_the_round_trip_cost():
    """BTCUSD is 20 bps of notional. Entry 100 with a stop 2 away means risk 2,
    so the cost in R is 0.0020 * 100 / 2 = 0.1R."""
    assert net_r_multiples("BTCUSD", [1.0], [100.0], [98.0]) == [0.9]


def test_cost_in_r_shrinks_as_the_stop_widens():
    """The same venue is far more expensive on a tight stop than a wide one —
    the reason a 0.5R scalp ladder needs its net number quoted."""
    tight = net_r_multiples("BTCUSD", [1.0], [100.0], [99.0])   # risk 1 → 0.2R
    wide = net_r_multiples("BTCUSD", [1.0], [100.0], [90.0])    # risk 10 → 0.02R
    assert tight[0] < wide[0]
    assert abs(tight[0] - 0.8) < 1e-9
    assert abs(wide[0] - 0.98) < 1e-9


def test_net_r_costs_a_loss_as_well_as_a_win():
    assert abs(net_r_multiples("BTCUSD", [-1.0], [100.0], [98.0])[0] + 1.1) < 1e-9


def test_net_r_is_empty_for_no_trades():
    assert net_r_multiples("BTCUSD", [], [], []) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/test_backtest.py -k net -v
```

Expected: FAIL — `ImportError: cannot import name 'net_r_multiples'`.

- [ ] **Step 3: Implement it**

In `signals/backtest.py`, change the `r_model` import to:

```python
from signals.r_model import cost_r, scaled_r  # noqa: F401
```

Add this function immediately after `summarize`:

```python
def net_r_multiples(symbol, r_multiples, entries, stops):
    """Per-trade R after the round-trip cost for that trade's stop distance.

    Cost is a fraction of PRICE while R is a fraction of the stop distance, so
    it has to be charged per trade rather than as one average — a tight-stop
    scalp and a wide-stop swing on the same symbol pay very different amounts
    in R. `r_model` stays the single definition of what a trade cost.
    """
    return [
        r - cost_r(symbol, entry, stop)
        for r, entry, stop in zip(r_multiples, entries, stops)
    ]
```

In `backtest_strategy`, add two accumulators next to `r_multiples`:

```python
    r_multiples = []
    entries = []
    stops = []
```

Record them where the R-multiple is appended, immediately after the existing
`r_multiples.append(...)` call:

```python
        entries.append(setup.entry)
        stops.append(setup.stop_loss)
```

and extend the stats block at the end of the function:

```python
    stats = summarize(r_multiples)
    trades = stats["trades"]
    stats["tp1_rate"] = tp1_hits / trades if trades else 0.0
    stats["tp3_rate"] = tp3_hits / trades if trades else 0.0
    net = net_r_multiples(symbol, r_multiples, entries, stops)
    stats["net_expectancy_r"] = sum(net) / trades if trades else 0.0
    stats["net_total_r"] = sum(net)
    return stats
```

The early-return branch for too-few candles must also carry the new keys, so
callers never have to guess whether they exist:

```python
    if n <= warmup + 1:
        stats = summarize([])
        stats["tp1_rate"] = 0.0
        stats["tp3_rate"] = 0.0
        stats["net_expectancy_r"] = 0.0
        stats["net_total_r"] = 0.0
        return stats
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/test_backtest.py -v
```

Expected: PASS, all pre-existing backtest tests included.

- [ ] **Step 5: Commit**

```bash
git add signals/backtest.py tests/core/test_backtest.py
git commit -m "feat(backtest): report expectancy net of round-trip costs"
```

---

## Task 8: Add BBMA to the backtest registry

**Files:**
- Modify: `signals/backtest.py:30-47`

- [ ] **Step 1: Extend both registries**

Replace `STRATEGY_TIMEFRAMES`:

```python
STRATEGY_TIMEFRAMES = {
    "ict_fvg": "5m",
    "ema_cross": "1h",
    "ict_smc": "1h",
    "sr_zone": "1h",
    "bbma_extreme": "1h",
    "bbma_reentry": "1h",
}
```

Replace `CONFLUENCE_TIMEFRAMES`:

```python
CONFLUENCE_TIMEFRAMES = {
    "ict_fvg": "15m",
    "ema_cross": "4h",
    "ict_smc": "4h",
    "sr_zone": "4h",
    # bbma_extreme is deliberately absent: it is counter-trend by construction,
    # so an HTF trend gate would veto nearly every setup.
    "bbma_reentry": "4h",
}
```

- [ ] **Step 2: Verify the registry is consistent**

```bash
.venv/bin/python -c "
from signals.backtest import CONFLUENCE_TIMEFRAMES, STRATEGY_TIMEFRAMES
from signals.models import SIGNAL_STRATEGIES
assert set(STRATEGY_TIMEFRAMES) <= set(SIGNAL_STRATEGIES), 'unknown strategy in registry'
assert set(CONFLUENCE_TIMEFRAMES) <= set(STRATEGY_TIMEFRAMES), 'confluence for an unbacktested strategy'
assert 'bbma_extreme' not in CONFLUENCE_TIMEFRAMES, 'extreme must stay ungated'
print('registry consistent')
"
```

Expected: `registry consistent`.

- [ ] **Step 3: Commit**

```bash
git add signals/backtest.py
git commit -m "feat(backtest): register the BBMA strategies at 1h"
```

---

## Task 9: `scripts/bbma_report.py`

**Files:**
- Create: `scripts/bbma_report.py`
- Test: `tests/core/test_bbma_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_bbma_report.py`:

```python
"""The sweep's gating map — Extreme must never pick up an HTF gate by accident."""
from scripts.bbma_report import CONFLUENCE, TIMEFRAMES, htf_for


def test_extreme_is_ungated_on_every_timeframe():
    for timeframe in TIMEFRAMES:
        assert htf_for("bbma_extreme", timeframe) is None


def test_reentry_steps_one_timeframe_up():
    assert htf_for("bbma_reentry", "1h") == "4h"
    assert htf_for("bbma_reentry", "4h") == "1d"


def test_every_swept_timeframe_has_a_confluence_mapping():
    for timeframe in TIMEFRAMES:
        assert timeframe in CONFLUENCE


def test_15m_is_not_swept():
    """Kraken caps OHLC at 721 bars — 7.5 days at 15m, which cannot produce a
    trade count worth reading."""
    assert "15m" not in TIMEFRAMES
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/core/test_bbma_report.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.bbma_report'`.

- [ ] **Step 3: Write the script**

Create `scripts/bbma_report.py`:

```python
"""Backtest sweep for the two BBMA detectors.

Reports each pattern separately, on each symbol, at each timeframe, gross AND
net of round-trip costs. The split matters: `bbma_extreme` fades a move and
`bbma_reentry` follows one, so a single blended number could hide a profitable
half behind a losing one.

Read the trade count before the expectancy. Kraken caps OHLC at 721 bars, so a
1h row spans about 30 days and a 4h row about 120 — thin enough that a handful
of trades proves nothing either way.

Usage: .venv/bin/python -m scripts.bbma_report
"""
import requests

from signals.backtest import backtest_strategy
from signals.market_client import fetch_candles

STRATEGIES = ("bbma_extreme", "bbma_reentry")
SYMBOLS = ("BTCUSD", "ETHUSD", "XAUUSD", "GBPUSD")
# 15m is omitted deliberately — see the module docstring.
TIMEFRAMES = ("1h", "4h")
# One step up for the higher-timeframe trend gate.
CONFLUENCE = {"1h": "4h", "4h": "1d"}
TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
# bbma_extreme is counter-trend by design and takes no HTF gate.
GATED = frozenset({"bbma_reentry"})
# Kraken caps at 721 regardless; ask for everything each source will serve.
CANDLE_LIMIT = 5000


def htf_for(strategy, timeframe):
    """The confluence timeframe for one row, or None when the strategy is
    ungated."""
    if strategy not in GATED:
        return None
    return CONFLUENCE.get(timeframe)


def _row(strategy, symbol, timeframe, session):
    htf = htf_for(strategy, timeframe)
    candles = fetch_candles(symbol, timeframe, CANDLE_LIMIT,
                            session=session)[:-1]
    htf_candles = None
    if htf is not None:
        htf_candles = fetch_candles(symbol, htf, CANDLE_LIMIT,
                                    session=session)[:-1]
    stats = backtest_strategy(
        strategy, symbol, candles,
        htf_candles=htf_candles,
        htf_minutes=TF_MINUTES[htf] if htf else None,
    )
    stats["bars"] = len(candles)
    return stats


def main():
    session = requests.Session()
    print("Scale-out model: 1/3 booked at each of TP1/TP2/TP3, stop to "
          "breakeven after TP1. Net subtracts r_model round-trip costs.")
    print("bbma_extreme ladder is 0.5/1/1.5R; bbma_reentry is 1/2/3R.")
    print(f"{'strategy':13} {'symbol':7} {'tf':3} {'bars':>5} {'trades':>6} "
          f"{'tp1%':>6} {'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>8}")
    print("-" * 78)
    for strategy in STRATEGIES:
        for timeframe in TIMEFRAMES:
            for symbol in SYMBOLS:
                try:
                    s = _row(strategy, symbol, timeframe, session)
                except Exception as exc:
                    print(f"{strategy:13} {symbol:7} {timeframe:3} "
                          f"data unavailable ({type(exc).__name__}: {exc})")
                    continue
                print(f"{strategy:13} {symbol:7} {timeframe:3} {s['bars']:5d} "
                      f"{s['trades']:6d} {s['tp1_rate'] * 100:5.1f}% "
                      f"{s['tp3_rate'] * 100:5.1f}% "
                      f"{s['expectancy_r']:+6.2f}R {s['net_expectancy_r']:+6.2f}R "
                      f"{s['total_r']:+7.1f}R")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/core/test_bbma_report.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/bbma_report.py tests/core/test_bbma_report.py
git commit -m "feat(bbma): add the backtest sweep script"
```

---

## Task 10: Run the sweep and record the result

**Files:**
- Create: `docs/bbma-backtest-results.md`

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/python -m pytest
```

Expected: all tests pass. Fix any regression before continuing — do not record
results from a codebase with failing tests.

- [ ] **Step 2: Run the sweep**

```bash
.venv/bin/python -m scripts.bbma_report
```

This makes live HTTP calls to Kraken and Yahoo, so it takes a minute. Save the
full output — it goes into the results doc verbatim.

- [ ] **Step 3: Write the results doc**

Create `docs/bbma-backtest-results.md` containing:

1. The command that produced the numbers and the UTC date it was run.
2. The raw table, pasted verbatim.
3. A "How to read this" section restating the sample limits: Kraken caps OHLC
   at 721 bars, so a 1h row is ~30 days and a 4h row ~120 days per symbol; any
   row in single-digit trades is noise, not evidence.
4. A verdict per pattern, stated plainly. The bar agreed in the spec is
   **positive net expectancy on more than one symbol with a non-trivial trade
   count**. If neither pattern clears it, say so directly and recommend against
   promotion — a negative result reported honestly is the deliverable, not a
   failure of the work.
5. Any follow-up worth doing, with the reason. Candidates the design left open
   on purpose: whether an ADX veto would have helped `bbma_extreme` (the values
   are already recorded in each setup's indicators), and whether a longer
   history source would change the picture.

- [ ] **Step 4: Commit**

```bash
git add docs/bbma-backtest-results.md
git commit -m "docs(bbma): record the backtest sweep results"
```

- [ ] **Step 5: Report back**

Summarise for the user: trade counts, gross vs net expectancy per pattern, and
the promotion verdict. Quote the actual numbers rather than characterising
them, and state plainly if the sample is too thin to conclude anything.

---

## Verification checklist

- [ ] `.venv/bin/python -m pytest` — full suite green
- [ ] `.venv/bin/python -m signals.backtest` — runs, prints BBMA rows alongside the existing strategies
- [ ] `.venv/bin/python -m scripts.bbma_report` — runs, prints the full sweep
- [ ] `git log --oneline` — one commit per task, ten in total
- [ ] `TRADING_SESSIONS`, `ADMIN_SELECTABLE_STRATEGIES` and `supabase/migrations/` are untouched:
      `git diff main --stat -- signals/models.py supabase/` shows only the `SIGNAL_STRATEGIES` line
