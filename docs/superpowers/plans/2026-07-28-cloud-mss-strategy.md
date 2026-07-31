# Cloud + Market Structure Shift (`cloud_mss`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trade the 15m chart off the cloud between a 1h Chandelier Exit and a 15m LWMA200 — sell a rally into an overhead cloud, buy a drop into one below — confirmed by a change of character against the pullback leg.

**Architecture:** One detector package reusing three existing primitives (`chandelier_exit`, `lwma`, `ict_smc`'s pivots), plus two pieces of infrastructure it cannot work without: an MT5-style ATR so the engine's cloud matches the chart, and multi-timeframe support in the windowed backtester so the strategy can be measured at all.

**Tech Stack:** Python 3.12, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-28-cloud-mss-strategy-design.md`

**Run tests with:** `.venv/bin/python -m pytest` (the `.venv/bin/pytest` shim is broken — always `-m pytest`).

## Deviation from the spec, recorded

The spec says this *replaces* `sr_zone` on the 15m session. On this branch the
15m session was already **retired** to `AUXILIARY_SESSIONS` (it measured
−0.415R). So Task 5 **reinstates** a 15m session carrying `cloud_mss` and
removes the retired entry, rather than editing a live one.

The retired entry must not simply be left in place alongside a new one:
`outcome_tracker` builds `_SESSION_BY_TIMEFRAME = {s.timeframe: s for s in
ALL_SESSIONS}`, so two sessions at 15m would silently collide and one would
win at random.

---

## File Structure

| File | Responsibility |
|---|---|
| `signals/indicators.py` (modify) | add `sma_atr`; `chandelier_exit` gains `atr_fn` |
| `signals/strategies/cloud_mss/__init__.py` (create) | export `detect_setup` |
| `signals/strategies/cloud_mss/detector.py` (create) | the strategy |
| `signals/strategies/router.py` (modify) | dispatch with `h1_candles` |
| `signals/models.py` (modify) | register key; reinstate the 15m session |
| `signals/run.py` (modify) | fetch 1h + raise the candle limit |
| `signals/backtest.py` (modify) | `backtest_windowed` gains aligned HTF candles |
| `signals/chart/plan.py` (modify) | `_cloud_mss` builder |
| `scripts/cloud_mss_report.py` (create) | the measurement sweep |

---

## Task 1: MT5-style ATR

**Files:**
- Modify: `signals/indicators.py`
- Test: `tests/core/test_indicators.py`

- [ ] **Step 1: Write the failing tests**

Change the import line at the top of `tests/core/test_indicators.py` to:

```python
from signals.indicators import adx, atr, bollinger, ema, macd_histogram, rsi, sma_atr
```

Append:

```python
def test_sma_atr_is_a_plain_mean_of_true_range():
    """MT5's iATR averages true range with a plain SMA. On a constant-range
    series it equals that range exactly, same as Wilder."""
    n = 30
    highs = [102.0] * n
    lows = [98.0] * n
    closes = [100.0] * n
    result = sma_atr(highs, lows, closes, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert abs(v - 4.0) < 1e-9


def test_sma_atr_differs_from_wilder_on_a_changing_series():
    """The whole reason this exists. Wilder weights history far more heavily,
    so after a volatility step the two disagree — and a Chandelier band built
    on one sits somewhere the other would not put it."""
    n = 40
    highs = [101.0] * 20 + [110.0] * 20
    lows = [99.0] * 20 + [90.0] * 20
    closes = [100.0] * 40
    wilder = atr(highs, lows, closes, 14)
    simple = sma_atr(highs, lows, closes, 14)
    assert abs(simple[-1] - wilder[-1]) > 0.5


def test_sma_atr_aligns_and_pads_like_wilder():
    n = 40
    highs = [100.0 + i for i in range(n)]
    lows = [99.0 + i for i in range(n)]
    closes = [99.5 + i for i in range(n)]
    simple = sma_atr(highs, lows, closes, 14)
    wilder = atr(highs, lows, closes, 14)
    assert len(simple) == n
    assert [v is None for v in simple] == [v is None for v in wilder]


def test_sma_atr_too_short_is_all_none():
    assert sma_atr([1.0] * 5, [0.5] * 5, [0.8] * 5, 14) == [None] * 5


def test_chandelier_exit_accepts_an_alternative_atr():
    from signals.indicators import chandelier_exit

    n = 60
    highs = [100.0 + i for i in range(n)]
    lows = [99.0 + i for i in range(n)]
    closes = [99.5 + i for i in range(n)]
    default = chandelier_exit(highs, lows, closes, period=22, lookback=22)
    swapped = chandelier_exit(highs, lows, closes, period=22, lookback=22,
                              atr_fn=sma_atr)
    assert default[0][-1] != swapped[0][-1]


def test_chandelier_exit_default_path_is_unchanged():
    """ce_lwma is live on this default. Adding the hook must not move it."""
    from signals.indicators import chandelier_exit

    n = 60
    highs = [100.0 + i for i in range(n)]
    lows = [99.0 + i for i in range(n)]
    closes = [99.5 + i for i in range(n)]
    explicit = chandelier_exit(highs, lows, closes, period=22, lookback=22,
                               atr_fn=atr)
    implicit = chandelier_exit(highs, lows, closes, period=22, lookback=22)
    assert explicit == implicit
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/core/test_indicators.py -k sma_atr -v
```

Expected: FAIL — `ImportError: cannot import name 'sma_atr'`.

- [ ] **Step 3: Implement**

In `signals/indicators.py`, add immediately after `atr`:

```python
def sma_atr(highs, lows, closes, period=14):
    """Simple-average True Range — MetaTrader's iATR, not Wilder's.

    MT5 averages true range with a plain SMA. Wilder's smoothing (see `atr`)
    weights older bars far more heavily, so after any change in volatility the
    two diverge, and a Chandelier band built on one sits where the other would
    not put it.

    strategy_doc/TrendFollowingClaud.pine calls this out deliberately —
    "MT5 iATR is a simple average of True Range, not Wilder smoothing" — so a
    strategy read off that chart has to use this definition or the engine's
    levels will not match the levels a human is looking at.

    Padding matches `atr` exactly so the two are interchangeable.
    """
    n = len(closes)
    if n < period + 1:
        return [None] * n
    true_ranges = [None]
    for i in range(1, n):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    out = [None] * period
    for i in range(period, n):
        window = true_ranges[i - period + 1:i + 1]
        out.append(sum(window) / period)
    return out
```

Then change the `chandelier_exit` signature and its ATR call:

```python
def chandelier_exit(highs, lows, closes, period=22, multiplier=4.5,
                    lookback=None, atr_fn=atr):
```

```python
    atr_vals = atr_fn(highs, lows, closes, period)
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/core/test_indicators.py -v
```

Expected: PASS, all pre-existing indicator tests included.

- [ ] **Step 5: Commit**

```bash
git add signals/indicators.py tests/core/test_indicators.py
git commit -m "feat(indicators): add MT5-style simple-average ATR"
```

---

## Task 2: The `cloud_mss` detector

**Files:**
- Create: `signals/strategies/cloud_mss/__init__.py`, `signals/strategies/cloud_mss/detector.py`
- Test: `tests/strategies/test_cloud_mss_detector.py`

**Constant note:** the spec listed both `TOUCH_LOOKBACK` (6) and
`MAX_BARS_SINCE_TOUCH` (4). Since the CHoCH is always the latest bar, the touch
can never be more than `MAX_BARS_SINCE_TOUCH` bars back, which makes
`TOUCH_LOOKBACK` dead. Only `MAX_BARS_SINCE_TOUCH` is implemented.

- [ ] **Step 1: Write the failing tests**

Create `tests/strategies/test_cloud_mss_detector.py`:

```python
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
ATR = 2.0
CLOUD_LOW = 110.0
CLOUD_HIGH = 114.0
H1 = [Candle(i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(60)]


def _c(open_, high, low, close, i):
    return Candle(open_time=i * 900_000, open=open_, high=high, low=low,
                  close=close, volume=1.0)


def _patch_cloud(monkeypatch, trend):
    monkeypatch.setattr(mod, "_cloud",
                        lambda _h1, _ma: (trend, CLOUD_LOW, CLOUD_HIGH))


def _sell_series():
    """Price below an overhead cloud, a rally that wicks into it and closes
    back below, then a close under the pre-touch swing low."""
    candles = [_c(100.0, 100.6, 99.4, 100.0, i) for i in range(N)]
    # A pivot low at 96 then a pivot high at 104, both before the touch.
    candles[N - 12] = _c(99.0, 99.5, 96.0, 99.0, N - 12)     # swing low 96
    candles[N - 8] = _c(102.0, 104.0, 101.5, 103.0, N - 8)   # swing high 104
    # Touch: wicks into the cloud, closes back below it.
    candles[N - 3] = _c(105.0, 111.0, 104.0, 106.0, N - 3)
    candles[N - 2] = _c(106.0, 106.5, 100.0, 101.0, N - 2)
    # CHoCH: first close below the swing low of 96.
    candles[N - 1] = _c(101.0, 101.5, 94.0, 95.0, N - 1)
    return candles


def _buy_series():
    """Mirror: price above a cloud below it, a dip that wicks in and closes
    back above, then a close over the pre-touch swing high."""
    candles = [_c(124.0, 124.6, 123.4, 124.0, i) for i in range(N)]
    candles[N - 12] = _c(125.0, 128.0, 124.5, 125.0, N - 12)  # swing high 128
    candles[N - 8] = _c(122.0, 122.5, 120.0, 121.0, N - 8)    # swing low 120
    candles[N - 3] = _c(119.0, 120.0, 113.0, 118.0, N - 3)    # wick into cloud
    candles[N - 2] = _c(118.0, 124.0, 117.5, 123.0, N - 2)
    candles[N - 1] = _c(123.0, 130.0, 122.5, 129.0, N - 1)    # close > 128
    return candles


# --- sell ------------------------------------------------------------------

def test_sell_fires_on_a_rejection_then_choch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    setup = detect_setup("BTCUSD", _sell_series(), [ATR] * N, h1_candles=H1)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 95.0


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
    bearish. Bullish trend means the cloud below has been left behind."""
    _patch_cloud(monkeypatch, 1)
    assert detect_setup("BTCUSD", _sell_series(), [ATR] * N,
                        h1_candles=H1) is None


def test_no_setup_when_price_sits_inside_the_cloud(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 1] = _c(101.0, 113.0, 94.0, 112.0, N - 1)   # closes in the cloud
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_when_the_touch_bar_closes_inside_the_cloud(monkeypatch):
    """Closing inside means the cloud has not rejected price yet."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(105.0, 113.0, 104.0, 112.0, N - 3)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_without_a_touch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(105.0, 106.0, 104.0, 105.5, N - 3)   # never reaches it
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_no_setup_without_a_choch(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 1] = _c(101.0, 101.5, 97.5, 98.0, N - 1)     # 98 > swing low 96
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_a_breakout_through_the_cloud_voids_the_setup(monkeypatch):
    """A close above the pre-touch swing high between the touch and the break
    means the pullback resolved as continuation. The setup is dead, and must
    stay dead even though the final bar closes below the swing low."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    # The bar between the touch and the break closes above the swing high (104).
    candles[N - 2] = _c(104.5, 106.0, 104.0, 105.0, N - 2)
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_choch_must_be_the_first_break_not_a_later_one(monkeypatch):
    """If an earlier bar already broke the swing low, that bar was the CHoCH
    and fired then. Re-firing would open a second trade on one setup."""
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 2] = _c(106.0, 106.5, 93.0, 94.5, N - 2)     # broke it first
    assert detect_setup("BTCUSD", candles, [ATR] * N, h1_candles=H1) is None


def test_touch_older_than_the_limit_is_ignored(monkeypatch):
    _patch_cloud(monkeypatch, -1)
    candles = _sell_series()
    candles[N - 3] = _c(105.0, 106.0, 104.0, 105.5, N - 3)   # no touch here
    far = N - 2 - MAX_BARS_SINCE_TOUCH - 1
    candles[far] = _c(105.0, 111.0, 104.0, 106.0, far)       # too far back
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


# --- buy -------------------------------------------------------------------

def test_buy_fires_on_the_mirror_setup(monkeypatch):
    _patch_cloud(monkeypatch, 1)
    setup = detect_setup("BTCUSD", _buy_series(), [ATR] * N, h1_candles=H1)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 129.0
    assert setup.stop_loss == CLOUD_LOW - STOP_ATR_BUFFER * ATR
    assert setup.indicators["side"] == "discount"


# --- guards ----------------------------------------------------------------

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
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/strategies/test_cloud_mss_detector.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.cloud_mss'`.

- [ ] **Step 3: Implement the detector**

Create `signals/strategies/cloud_mss/detector.py`:

```python
"""Cloud + market structure shift.

The cloud is the band between a 1h Chandelier Exit and a 15m LWMA200 — the
shaded region in strategy_doc/TrendFollowingClaud.pine. It acts as a dynamic
support/resistance zone, and which side of price it sits on sets the bias:

  * PREMIUM  — cloud overhead, 1h Chandelier bearish. A rally into it is a sell.
  * DISCOUNT — cloud below, 1h Chandelier bullish. A drop into it is a buy.

Three ordered events make a setup: price wicks into the cloud and closes back
out (the rejection), then within a few bars closes through the pivot on the far
side of the pullback leg (the change of character), and that bar is the entry.

The Chandelier here uses `sma_atr`, MetaTrader's simple-average true range,
because the Pine does. `ce_lwma` uses the Wilder default and is untouched.
"""
from signals.indicators import chandelier_exit, lwma, sma_atr
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows

CE_ATR_PERIOD = 22
CE_MULTIPLIER = 4.5
CE_LOOKBACK = 22
MA_PERIOD = 200

# LWMA200 warm-up plus room for the structure window. _load_market_data fetches
# 260 and drops the forming bar, leaving 259 — comfortably above this. A test
# pins that relationship so the two cannot drift apart.
MIN_CANDLES = 230
# Chandelier needs max(period, lookback) + 1 bars before it emits a direction.
MIN_H1_CANDLES = max(CE_ATR_PERIOD, CE_LOOKBACK) + 2
# How many bars may sit between the cloud rejection and the structure break.
MAX_BARS_SINCE_TOUCH = 4
# Bars of 15m history scanned for the pivots that define the pullback leg.
STRUCTURE_WINDOW = 60
STOP_ATR_BUFFER = 0.5
MAX_STOP_ATR = 2.5


def _cloud(h1_candles, ma_value):
    """(trend, cloud_low, cloud_high) from the 1h Chandelier and the 15m MA.

    Returns None while the Chandelier is still warming up. This is the seam the
    rule tests monkeypatch — it is the only place 1h data enters the strategy.
    """
    highs = [c.high for c in h1_candles]
    lows = [c.low for c in h1_candles]
    closes = [c.close for c in h1_candles]
    long_stop, short_stop, direction = chandelier_exit(
        highs, lows, closes, period=CE_ATR_PERIOD, multiplier=CE_MULTIPLIER,
        lookback=CE_LOOKBACK, atr_fn=sma_atr,
    )
    trend = direction[-1]
    if trend is None:
        return None
    band = long_stop[-1] if trend == 1 else short_stop[-1]
    if band is None:
        return None
    return trend, min(band, ma_value), max(band, ma_value)


def _indicators(side, trend, cloud_low, cloud_high, ma_value, swing, atr_value,
                adx14, htf_trend):
    out = {
        "strategy": "cloud_mss",
        "side": side,
        "ce_trend": "up" if trend == 1 else "down",
        "cloud_low": cloud_low,
        "cloud_high": cloud_high,
        "ma200": ma_value,
        "choch_level": swing,
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _pivot_levels(candles, touch_index):
    """(swing_low, swing_high) from the bars strictly before the touch."""
    structure = candles[max(0, touch_index - STRUCTURE_WINDOW):touch_index]
    low_idx = pivot_lows(structure)
    high_idx = pivot_highs(structure)
    if not low_idx or not high_idx:
        return None, None
    return structure[low_idx[-1]].low, structure[high_idx[-1]].high


def _touch_indices(candles):
    """Candidate touch bars, most recent first."""
    n = len(candles)
    return range(n - 2, max(-1, n - 2 - MAX_BARS_SINCE_TOUCH), -1)


def detect_setup(symbol, candles, atr14, h1_candles=None, adx14=None,
                 htf_trend=None):
    """Return a CandidateSetup on a confirmed cloud rejection, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    if not h1_candles or len(h1_candles) < MIN_H1_CANDLES:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    ma = lwma([c.close for c in candles], MA_PERIOD)
    if ma[-1] is None:
        return None
    cloud = _cloud(h1_candles, ma[-1])
    if cloud is None:
        return None
    trend, cloud_low, cloud_high = cloud

    bar = candles[-1]
    n = len(candles)

    # --- premium: cloud overhead, sell the rally into it --------------------
    if trend == -1 and bar.close < cloud_low:
        for t in _touch_indices(candles):
            touch = candles[t]
            if not (touch.high >= cloud_low and touch.close < cloud_low):
                continue
            swing_low, swing_high = _pivot_levels(candles, t)
            if swing_low is None:
                continue
            between = candles[t + 1:n - 1]
            # A close back above the pre-touch swing high is the pullback
            # resolving as continuation — the setup is void, not pending.
            if any(c.close > swing_high for c in between):
                continue
            # If an earlier bar already broke the low, that bar was the CHoCH.
            if any(c.close < swing_low for c in between):
                continue
            if bar.close >= swing_low:
                continue
            stop = cloud_high + STOP_ATR_BUFFER * atr_value
            if stop <= bar.close:
                continue
            if abs(bar.close - stop) / atr_value > MAX_STOP_ATR:
                continue
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "short")
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("premium", trend, cloud_low, cloud_high, ma[-1],
                            swing_low, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    # --- discount: cloud below, buy the drop into it ------------------------
    if trend == 1 and bar.close > cloud_high:
        for t in _touch_indices(candles):
            touch = candles[t]
            if not (touch.low <= cloud_high and touch.close > cloud_high):
                continue
            swing_low, swing_high = _pivot_levels(candles, t)
            if swing_high is None:
                continue
            between = candles[t + 1:n - 1]
            if any(c.close < swing_low for c in between):
                continue
            if any(c.close > swing_high for c in between):
                continue
            if bar.close <= swing_high:
                continue
            stop = cloud_low - STOP_ATR_BUFFER * atr_value
            if stop >= bar.close:
                continue
            if abs(bar.close - stop) / atr_value > MAX_STOP_ATR:
                continue
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "long")
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("discount", trend, cloud_low, cloud_high, ma[-1],
                            swing_high, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
```

Create `signals/strategies/cloud_mss/__init__.py`:

```python
"""Cloud + market structure shift — the 15m playbook from
strategy_doc/TrendFollowingClaud.pine."""
from signals.strategies.cloud_mss.detector import detect_setup

__all__ = ["detect_setup"]
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_cloud_mss_detector.py -v
```

Expected: PASS. If a fixture does not produce the intended pivots, adjust the
FIXTURE bar prices — never the detector — and keep the assertion.

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/cloud_mss tests/strategies/test_cloud_mss_detector.py
git commit -m "feat(cloud-mss): add the cloud rejection + CHoCH detector"
```

---

## Task 3: Register the strategy

**Files:**
- Modify: `signals/models.py`, `signals/strategies/router.py`
- Test: `tests/strategies/test_cloud_mss_router.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_cloud_mss_router.py`:

```python
"""cloud_mss must be dispatchable and must receive the 1h candles it needs."""
from signals.models import SIGNAL_STRATEGIES, Candle
from signals.strategies import detect_setup
from signals.strategies.cloud_mss.detector import MIN_CANDLES

H1 = [Candle(i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(60)]


def _candles(n):
    return [Candle(i * 900_000, 100.0, 100.5, 99.5, 100.0, 1.0)
            for i in range(n)]


def _dispatch(candles, h1_candles):
    n = len(candles)
    return detect_setup(
        "cloud_mss", "BTCUSD", candles,
        [None] * n, [None] * n, [None] * n, [None] * n, [2.0] * n,
        adx14=None, htf_trend=None, h1_candles=h1_candles,
    )


def test_key_is_registered():
    assert "cloud_mss" in SIGNAL_STRATEGIES


def test_router_dispatches_without_error():
    assert _dispatch(_candles(MIN_CANDLES), H1) is None


def test_router_returns_none_when_h1_is_missing():
    """The router must pass h1_candles through. If it dropped them the
    detector would return None for the wrong reason and the failure would be
    invisible."""
    assert _dispatch(_candles(MIN_CANDLES), None) is None
```

Append to `tests/core/test_pipeline.py`:

```python
def test_fifteen_minute_session_runs_cloud_mss():
    from signals.models import ALL_SESSIONS, TRADING_SESSIONS

    by_tf = {s.timeframe: s for s in TRADING_SESSIONS}
    assert "15m" in by_tf, "the 15m session must be scanned again"
    assert by_tf["15m"].strategy == "cloud_mss"
    assert by_tf["15m"].max_open_days == 2
    # Exactly one session may claim a timeframe: outcome_tracker keys expiry
    # off ALL_SESSIONS by timeframe, so a duplicate would win at random.
    timeframes = [s.timeframe for s in ALL_SESSIONS]
    assert len(timeframes) == len(set(timeframes))
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/strategies/test_cloud_mss_router.py -q
```

Expected: FAIL — `assert 'cloud_mss' in SIGNAL_STRATEGIES`.

- [ ] **Step 3: Register**

In `signals/models.py`, extend `SIGNAL_STRATEGIES`:

```python
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry", "cloud_mss")
```

Add the 15m session back into `TRADING_SESSIONS`, between `super_scalp` and
`swing`:

```python
    TradingSession(
        name="scalp", timeframe="15m", max_open_days=2,
        confluence_timeframe=None, strategy="cloud_mss",
    ),
```

And **delete** the retired `scalp` entry from `AUXILIARY_SESSIONS`, leaving only
`xau_scalp`. Update the comment above `TRADING_SESSIONS` to:

```python
# Sessions the main engine scans, in order, every run.
# Super scalp = 5m ICT+FVG (tight R); scalp = 15m cloud rejection + CHoCH;
# swing = admin strategy.
```

In `signals/strategies/router.py`, add the import:

```python
from signals.strategies.cloud_mss import detect_setup as detect_cloud_mss
```

and a branch before the `sr_zone` one:

```python
    if strategy == "cloud_mss":
        if not h1_candles:
            return None
        return detect_cloud_mss(
            symbol, candles, atr14, h1_candles=h1_candles,
            adx14=adx14, htf_trend=htf_trend,
        )
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_cloud_mss_router.py tests/core/test_pipeline.py tests/core/test_outcome.py -q
```

Expected: PASS. If a pipeline test asserts the old two-session set, update it to
expect `5m + 15m + 1h` — that is the intended change, not a regression.

- [ ] **Step 5: Commit**

```bash
git add signals/models.py signals/strategies/router.py tests/
git commit -m "feat(cloud-mss): reinstate the 15m session running cloud_mss"
```

---

## Task 4: Fetch 1h candles for the 15m scan

**Files:**
- Modify: `signals/run.py`
- Test: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_pipeline.py`:

```python
def test_load_market_data_fetches_h1_for_cloud_mss(monkeypatch):
    """cloud_mss builds its cloud from 1h candles. Without them the detector
    returns None on every bar and the session silently produces nothing."""
    fetched = []

    def fake_fetch(symbol, interval, limit, session=None):
        fetched.append((interval, limit))
        return [
            run_module.Candle(i * 900_000, 100.0, 100.5, 99.5, 100.0, 1.0)
            for i in range(limit)
        ]

    monkeypatch.setattr(run_module, "fetch_candles", fake_fetch)
    market, _ = run_module._load_market_data(
        "BTCUSDT", "15m", "cloud_mss", _config(), session=None)

    assert market is not None
    assert market.h1_candles, "1h candles were not loaded"
    intervals = [i for i, _ in fetched]
    assert "1h" in intervals
    # 260 fetched, forming bar dropped -> 259 closed, above MIN_CANDLES (230).
    primary_limit = next(lim for iv, lim in fetched if iv == "15m")
    assert primary_limit >= 260


def test_cloud_mss_candle_limit_clears_its_own_minimum():
    """A fetch that yields fewer closed bars than MIN_CANDLES would leave a
    detector that can never fire — silently, with no error anywhere."""
    from signals.strategies.cloud_mss.detector import MIN_CANDLES

    cfg = _config()
    limit = run_module._candle_limit_for("cloud_mss", cfg)
    assert limit - 1 > MIN_CANDLES
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/core/test_pipeline.py -k cloud_mss -q
```

Expected: FAIL — `AttributeError: module 'signals.run' has no attribute '_candle_limit_for'`.

- [ ] **Step 3: Implement**

In `signals/run.py`, add above `_load_market_data`:

```python
# Strategies that need more history than the default scan window, and why.
#   ce_lwma   — LWMA200 on the 15m series
#   cloud_mss — LWMA200 plus the structure window; 260 fetched leaves 259
#               closed bars against a MIN_CANDLES of 230
EXTRA_HISTORY = {"ce_lwma": 220, "cloud_mss": 260}
# Strategies whose detector reads 1h candles directly.
NEEDS_H1 = ("ce_lwma", "cloud_mss")


def _candle_limit_for(strategy, cfg):
    """Bars to fetch for `strategy`'s primary timeframe."""
    return max(cfg.candle_limit, EXTRA_HISTORY.get(strategy, 0))
```

Replace the `candle_limit` line inside `_load_market_data`:

```python
    candle_limit = _candle_limit_for(strategy, cfg)
```

Replace the `if strategy == "ce_lwma":` guard that fetches H1 with:

```python
    if strategy in NEEDS_H1:
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/core/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add signals/run.py tests/core/test_pipeline.py
git commit -m "feat(cloud-mss): load 1h candles and deeper history for the 15m scan"
```

---

## Task 5: Multi-timeframe support in the backtester

`backtest.py`'s own docstring says multi-timeframe strategies are not covered.
This is what makes `cloud_mss` measurable — and `ce_lwma` too, which has never
been measured over long history.

**Files:**
- Modify: `signals/backtest.py`
- Test: `tests/core/test_backtest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_backtest.py`:

```python
def test_windowed_replay_passes_only_closed_htf_candles():
    """A 15m bar must never see a 1h candle that had not finished forming.
    Leaking the in-progress candle is lookahead and would flatter every
    multi-timeframe result."""
    hour = 3_600_000
    primary = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(400)]
    htf = [Candle(i * hour, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(20)]

    seen = []

    def spy(symbol, candles, atr14, htf_trend=None, h1_candles=None):
        seen.append((candles[-1].open_time, h1_candles[-1].open_time
                     if h1_candles else None))
        return None

    backtest_windowed(spy, "BTCUSD", primary, [2.0] * len(primary),
                      [None] * len(primary), window=200,
                      htf_candles=htf, htf_minutes=60)

    assert seen, "the detector was never called"
    for bar_time, htf_time in seen:
        if htf_time is None:
            continue
        assert htf_time + hour <= bar_time, (
            f"htf candle at {htf_time} had not closed by {bar_time}")


def test_windowed_replay_without_htf_candles_omits_the_argument():
    """Single-timeframe detectors do not accept h1_candles. Passing it
    unconditionally would break every existing strategy."""
    primary = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(300)]
    calls = []

    def spy(symbol, candles, atr14, htf_trend=None):
        calls.append(1)
        return None

    backtest_windowed(spy, "BTCUSD", primary, [2.0] * len(primary),
                      [None] * len(primary), window=200)
    assert calls
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/core/test_backtest.py -k htf -q
```

Expected: FAIL — `TypeError: backtest_windowed() got an unexpected keyword argument 'htf_candles'`.

- [ ] **Step 3: Implement**

In `signals/backtest.py`, add above `backtest_windowed`:

```python
# 1h bars handed to a multi-timeframe detector per primary bar. The Chandelier
# needs ~44; 120 leaves headroom without making the slice cost grow with the
# length of the backtest.
HTF_WINDOW = 120


def htf_close_index(primary_candles, htf_candles, htf_minutes):
    """Per primary bar, the index of the last HTF candle that had CLOSED.

    -1 means none had. Same causality rule as `htf_trend_series`, computed once
    with a forward-walking cursor rather than re-scanned per bar.
    """
    htf_ms = htf_minutes * 60_000
    out = []
    j = -1
    for bar in primary_candles:
        while (j + 1 < len(htf_candles)
               and htf_candles[j + 1].open_time + htf_ms <= bar.open_time):
            j += 1
        out.append(j)
    return out
```

Change the signature of `backtest_windowed`:

```python
def backtest_windowed(detector, symbol, candles, atr14, trends, *,
                      window=200, max_hold=2000, bps=None,
                      htf_candles=None, htf_minutes=None):
```

Immediately before the `while` loop, add:

```python
    htf_index = (htf_close_index(candles, htf_candles, htf_minutes)
                 if htf_candles and htf_minutes else None)
```

Replace the detector call with:

```python
        kwargs = {"htf_trend": trends[i]}
        if htf_index is not None:
            j = htf_index[i]
            if j < 0:
                i += 1
                continue
            kwargs["h1_candles"] = htf_candles[max(0, j + 1 - HTF_WINDOW):j + 1]
        setup = detector(symbol, candles[lo:i + 1], atr14[lo:i + 1], **kwargs)
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/core/test_backtest.py -v
```

Expected: PASS, all pre-existing backtest tests included.

- [ ] **Step 5: Commit**

```bash
git add signals/backtest.py tests/core/test_backtest.py
git commit -m "feat(backtest): feed aligned higher-timeframe candles to detectors"
```

---

## Task 6: Chart overlay

**Files:**
- Modify: `signals/chart/plan.py`
- Test: `tests/chart/test_plan.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/chart/test_plan.py` (match the fixture helpers already in that
file; if it builds signals via a local helper, reuse it):

```python
def test_cloud_mss_plan_draws_the_cloud_and_choch():
    from signals.chart.plan import build_chart_plan
    from signals.models import Candle, Signal

    candles = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(60)]
    signal = Signal(
        id="s1", symbol="BTCUSD", timeframe="15m", direction="short",
        entry=95.0, stop_loss=115.0, take_profit=75.0, confidence=70,
        rationale="", news_headlines=[], created_at="2026-07-28T00:00:00Z",
        take_profit_2=55.0, take_profit_3=35.0,
        indicators={
            "strategy": "cloud_mss", "side": "premium",
            "cloud_low": 110.0, "cloud_high": 114.0,
            "ma200": 112.0, "choch_level": 96.0, "ce_trend": "down",
        },
    )
    plan = build_chart_plan(candles, signal)
    kinds = {a["kind"] for a in plan}
    assert "zone" in kinds, "the cloud must be drawn"
    labels = " ".join(a.get("label", "") for a in plan)
    assert "Cloud" in labels
    assert "CHoCH" in labels
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/chart/test_plan.py -k cloud_mss -q
```

Expected: FAIL — no `zone` in the plan, because unregistered strategies fall
through to `_no_structure`.

- [ ] **Step 3: Implement**

In `signals/chart/plan.py`, add before `_BUILDERS`:

```python
def _cloud_mss(candles, signal):
    """The cloud as a zone, the MA200 it is anchored to, and the structure
    level whose break confirmed the entry."""
    ind = signal.indicators
    side = ind.get("side", "cloud")
    out = [
        zone(ind["cloud_high"], ind["cloud_low"], None,
             f"Cloud ({side})", "premium" if side == "premium" else "discount"),
    ]
    closes = [c.close for c in candles]
    pts = [{"time": c.open_time, "value": v}
           for c, v in zip(candles, lwma(closes, 200))]
    out.append(series(pts, "LWMA200", "lwma"))
    if ind.get("choch_level") is not None:
        out.append(level(ind["choch_level"], "CHoCH level", "choch",
                         style="dashed"))
    return out
```

Register it:

```python
    "cloud_mss": _cloud_mss,
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/chart -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add signals/chart/plan.py tests/chart/test_plan.py
git commit -m "feat(cloud-mss): draw the cloud, MA200 and CHoCH level on charts"
```

---

## Task 7: Measure it

**Files:**
- Create: `scripts/cloud_mss_report.py`
- Create: `docs/cloud-mss-backtest-results.md`

- [ ] **Step 1: Write the sweep**

Create `scripts/cloud_mss_report.py`:

```python
"""cloud_mss over the full verified Binance history.

15m primary with 1h for the cloud. Provenance for the archives is established
by scripts/history_provenance.py — SHA256 against Binance's published digests
plus known market events at their correct dates.

Scored under the corrected fixed-stop R model (docs/r-model-correction.md):
one third booked at each of TP1/TP2/TP3, the published stop never moves, so an
unbooked remainder loses its full share when the stop is hit.

Usage: .venv/bin/python -m scripts.cloud_mss_report
"""
import statistics

import requests

from signals.backtest import backtest_windowed
from signals.history import load_history
from signals.indicators import atr
from signals.strategies.cloud_mss import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
PRIMARY = "15m"
HTF = "1h"
HTF_MINUTES = 60
WINDOW = 260          # matches _candle_limit_for("cloud_mss", cfg)
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled = []
    print("cloud_mss over verified Binance history. 15m primary, 1h cloud.")
    print("Fixed stop as published; net subtracts r_model round-trip costs.\n")
    print(f"{'symbol':8} {'years':>6} {'bars':>8} {'trades':>7} {'tp1%':>6} "
          f"{'gross':>8} {'net':>8} {'total':>9}")
    print("-" * 66)

    for symbol in SYMBOLS:
        candles = load_history(symbol, PRIMARY, session=session)
        htf = load_history(symbol, HTF, session=session)
        atr14 = atr([c.high for c in candles], [c.low for c in candles],
                    [c.close for c in candles], 14)
        out = backtest_windowed(
            detect_setup, symbol, candles, atr14, [None] * len(candles),
            window=WINDOW, max_hold=MAX_HOLD,
            htf_candles=htf, htf_minutes=HTF_MINUTES,
        )
        gross, net = out["gross"], out["net"]
        trades = len(gross)
        pooled += net
        years = ((candles[-1].open_time - candles[0].open_time)
                 / 1000 / 86400 / 365.25)
        if not trades:
            print(f"{symbol:8} {years:6.2f} {len(candles):8d} {0:7d}   no trades")
            continue
        print(f"{symbol:8} {years:6.2f} {len(candles):8d} {trades:7d} "
              f"{out['tp1_hits'] / trades * 100:5.1f}% "
              f"{statistics.mean(gross):+7.3f}R {statistics.mean(net):+7.3f}R "
              f"{sum(net):+8.1f}R")

    n = len(pooled)
    if n < 2:
        print(f"\nPOOLED n={n} — too few to summarise")
        return
    mean = statistics.mean(pooled)
    se = statistics.stdev(pooled) / (n ** 0.5)
    print("\n" + "=" * 66)
    print(f"POOLED n={n}  net={mean:+.3f}R  t={mean / se:+.2f}  "
          f"95% CI [{mean - 1.96 * se:+.3f}, {mean + 1.96 * se:+.3f}]  "
          f"total={sum(pooled):+.1f}R")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full suite**

```bash
.venv/bin/python -m pytest -q --ignore=tests/ml
```

Expected: all pass. Fix any regression before measuring — never record results
from a codebase with failing tests.

- [ ] **Step 3: Run the sweep**

```bash
.venv/bin/python -m scripts.cloud_mss_report
```

This downloads and SHA256-verifies 15m and 1h archives on first run and takes
several minutes. Save the output verbatim.

- [ ] **Step 4: Record the result**

Create `docs/cloud-mss-backtest-results.md` containing:

1. The command and the UTC date it ran.
2. The raw table, verbatim.
3. The R model in force, linking `docs/r-model-correction.md`, stating plainly
   that a fixed stop is scored — an unbooked remainder loses its full share.
4. A verdict. The bar: **positive net expectancy with a confidence interval
   excluding zero, on both symbols.** Every strategy measured in this repo so
   far has failed that bar; say so if this one does too.
5. Whether it should take the 15m session slot. If the answer is no, say the
   session should stay retired and that Task 3's reinstatement must be reverted
   before merge.

- [ ] **Step 5: Commit**

```bash
git add scripts/cloud_mss_report.py docs/cloud-mss-backtest-results.md
git commit -m "docs(cloud-mss): record the backtest sweep results"
```

---

## Verification checklist

- [ ] `.venv/bin/python -m pytest --ignore=tests/ml` — green (`tests/ml` needs
      `sklearn`, absent from this venv; pre-existing)
- [ ] `.venv/bin/python -m scripts.cloud_mss_report` — runs and prints a table
- [ ] `git log --oneline` — one commit per task, seven in total
- [ ] Exactly one session per timeframe:
      `python -c "from signals.models import ALL_SESSIONS; tf=[s.timeframe for s in ALL_SESSIONS]; assert len(tf)==len(set(tf)), tf; print('ok')"`
- [ ] `ce_lwma` still uses Wilder:
      `grep -n "atr_fn" signals/strategies/ce_lwma/detector.py` returns nothing
