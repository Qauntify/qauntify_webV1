# RSI(2) Pullback-in-Trend, Maker-Fill Entry (`rsi2_pullback`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `rsi2_pullback` — an RSI(2) pullback-in-trend detector with a resting-limit (maker-fee) entry — to the pluggable strategy system, fully wired and tested but **not** assigned to a live trading session, then produce an honest long-history backtest verdict before anyone decides whether to promote it.

**Architecture:** A single-file detector package, `signals/strategies/rsi2_pullback/detector.py` (no `windows.py` split needed — there is no session/time-anchor arithmetic here, unlike `orb_rvol`), matching every other detector's `detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None) -> CandidateSetup | None` contract. Then the same mechanical integration every admin-selectable strategy in this repo gets: router dispatch, the two Python strategy-name registries (`SIGNAL_STRATEGIES` and `ADMIN_SELECTABLE_STRATEGIES`), a Postgres CHECK constraint, the admin dropdown, no-setup/RAG/LLM-prompt copy. Finally a long-history report script against verified Binance archives, scored at the maker fee rate, mirroring `scripts/msnr_history_report.py`'s simpler shape (no `backtest.py` quick-check registration — `msnr` and `cloud_mss` skipped that step too; it's optional infrastructure, not a requirement every strategy needs).

**Tech Stack:** Python 3.12, pytest, existing `signals/` package conventions (no new dependencies — `signals.analysis.indicators.rsi` already supports any period).

**Spec:** `docs/superpowers/specs/2026-09-06-rsi2-pullback-strategy-design.md` (approved — read it first; this plan implements it exactly).

**One testing note not spelled out in the spec, decided here:** with `ATR_STOP_BUFFER=1.5` and `MAX_PIERCE_ATR=0.25` fixed, `entry` is always within `[dip_level - 0.25×ATR, dip_level]` of the dip level and `stop` is always exactly `1.5×ATR` beyond it — so `risk/ATR` is mathematically bounded to `[1.25, 1.5]` by construction, regardless of test input. `MIN_STOP_ATR (0.5)` and `MAX_STOP_ATR (3.0)` can therefore never actually fire through any realistic candle geometry — that is the tight-coupling safety design working as intended (this is the whole point: no wild outliers), not a gap. Task 1 tests this guard as an isolated `_risk_ok()` unit rather than trying to construct an unreachable full-detector scenario.

---

## Task 1: `detector.py` — RSI(2) dip, retest, resting-limit entry, stop, targets

**Files:**
- Create: `signals/strategies/rsi2_pullback/__init__.py`
- Create: `signals/strategies/rsi2_pullback/detector.py`
- Test: `tests/strategies/test_rsi2_pullback_detector.py`

- [ ] **Step 1: Create the package directory with an empty `__init__.py`**

```bash
mkdir -p signals/strategies/rsi2_pullback
touch signals/strategies/rsi2_pullback/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/strategies/test_rsi2_pullback_detector.py`:

```python
"""Unit tests for the RSI(2) pullback-in-trend, maker-fill detector.

Price-geometry helper: a long flat baseline (delta=0 every bar) keeps RSI(2)
at exactly 50 (rsi()'s own documented flat-series convention), so a single
sharp reversal bar predictably drives RSI(2) to an extreme without needing to
hand-tune a multi-bar ramp. See
docs/superpowers/specs/2026-09-06-rsi2-pullback-strategy-design.md.
"""
from signals.models import Candle
from signals.strategies.rsi2_pullback.detector import (
    ATR_STOP_BUFFER,
    MAX_BARS_SINCE_DIP,
    MAX_STOP_ATR,
    MIN_CANDLES,
    MIN_STOP_ATR,
    _risk_ok,
    detect_setup,
)

ATR = 1.0


def _c(i, o, h, l, c):
    return Candle(open_time=i * 60_000, open=o, high=h, low=l, close=c,
                 volume=1.0)


def _flat(n, start=0, price=100.0):
    """`n` flat bars (open=close=price, tiny wick) -- delta=0 keeps RSI(2)
    pinned at 50 throughout (rsi()'s flat-series convention)."""
    return [_c(start + i, price, price + 0.05, price - 0.05, price)
           for i in range(n)]


def _long_scenario(*, retest_open=90.3, retest_low=89.95, retest_high=91.0,
                   retest_close=90.7, filler_after_dip=0):
    """Flat baseline, one sharp red dip bar to 90.0 (drives RSI(2) to 0), a
    sharp green recovery bar (drives RSI(2) back above RSI_LOW so it does NOT
    stay pinned at the dip's value -- Wilder-smoothed RSI(2) freezes at
    whatever value it has once deltas go flat, verified directly against
    this repo's own rsi()), optional further flat filler, then a retest bar.

    The recovery bar matters for correctness, not just realism: without it,
    every filler bar would ALSO read RSI(2)==0 (since avg_gain stays at 0
    with no bounce), and _find_dip_long's lowest-low-among-candidates rule
    would still work, but MAX_BARS_SINCE_DIP staleness could never be tested
    -- there would always be a "fresh enough" candidate. Distance from the
    dip bar to the retest bar is `2 + filler_after_dip`.

    Returns (candles, dip_low)."""
    baseline = _flat(MIN_CANDLES, price=100.0)
    dip = _c(len(baseline), 100.0, 100.0, 90.0, 90.5)  # sharp red bar -> RSI(2) = 0
    dip_low = dip.low
    recover = _c(len(baseline) + 1, 90.5, 96.0, 90.5, 95.5)  # sharp green bar -> RSI(2) recovers well above RSI_LOW
    filler = _flat(filler_after_dip, start=len(baseline) + 2, price=95.5)
    retest_index = len(baseline) + 2 + filler_after_dip
    retest = _c(retest_index, retest_open, retest_high, retest_low, retest_close)
    return baseline + [dip, recover] + filler + [retest], dip_low


def _short_scenario(*, retest_open=109.7, retest_high=110.05,
                    retest_low=109.0, retest_close=109.3, filler_after_dip=0):
    """Mirror of _long_scenario: sharp green spike bar to 110.0 (RSI(2) to
    100), sharp red recovery bar (RSI(2) back below RSI_HIGH), optional
    filler, then a bearish retest bar. Returns (candles, dip_high)."""
    baseline = _flat(MIN_CANDLES, price=100.0)
    dip = _c(len(baseline), 100.0, 110.0, 100.0, 109.5)  # sharp green bar -> RSI(2) = 100
    dip_high = dip.high
    recover = _c(len(baseline) + 1, 109.5, 109.5, 104.0, 104.5)  # sharp red bar -> RSI(2) recovers well below RSI_HIGH
    filler = _flat(filler_after_dip, start=len(baseline) + 2, price=104.5)
    retest_index = len(baseline) + 2 + filler_after_dip
    retest = _c(retest_index, retest_open, retest_high, retest_low, retest_close)
    return baseline + [dip, recover] + filler + [retest], dip_high


def _atr(candles, value=ATR):
    return [value] * len(candles)


def test_long_retest_of_rsi2_dip_fires_at_the_dip_level():
    """The whole point: entry is the resting level (the dip low), not
    wherever the retest bar closed."""
    candles, dip_low = _long_scenario()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == dip_low
    assert setup.stop_loss == dip_low - ATR_STOP_BUFFER * ATR
    assert setup.indicators["strategy"] == "rsi2_pullback"
    assert setup.indicators["entry_style"] == "limit"
    assert setup.indicators["dip_low"] == dip_low
    # rsi2 records the reading at the RETEST bar (context for the LLM),
    # not the dip bar -- by the time price retests, RSI(2) has recovered
    # well off the extreme, so no threshold assertion belongs here.
    assert isinstance(setup.indicators["rsi2"], float)


def test_long_targets_are_the_standard_ladder():
    candles, _ = _long_scenario()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    risk = setup.entry - setup.stop_loss
    tp1, tp2, tp3 = setup.resolved_take_profits()
    assert abs(tp1 - (setup.entry + 1 * risk)) < 1e-9
    assert abs(tp2 - (setup.entry + 2 * risk)) < 1e-9
    assert abs(tp3 - (setup.entry + 3 * risk)) < 1e-9


def test_long_gap_through_the_level_fills_at_the_open_not_the_level():
    """A resting buy limit at the dip low: if the retest bar gapped down
    THROUGH that level, the order fills at the open, not a level price
    action never actually offered."""
    candles, dip_low = _long_scenario(
        retest_open=89.8, retest_low=89.78, retest_high=90.5, retest_close=90.2,
    )
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.entry == 89.8  # the gapped-down open, not dip_low (90.0)
    assert setup.entry < dip_low
    assert setup.stop_loss == dip_low - ATR_STOP_BUFFER * ATR  # still anchored to the dip


def test_short_retest_of_rsi2_spike_fires_at_the_spike_level():
    candles, dip_high = _short_scenario()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == dip_high
    assert setup.stop_loss == dip_high + ATR_STOP_BUFFER * ATR
    assert setup.indicators["dip_high"] == dip_high
    assert isinstance(setup.indicators["rsi2"], float)


def test_no_retest_bar_stays_above_the_dip_zone_returns_none():
    """The retest bar's low never comes back down near the dip low -- no
    resting order was ever reached."""
    candles, _ = _long_scenario(retest_open=95.0, retest_low=94.5,
                                retest_high=95.5, retest_close=95.2)
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_retest_bar_pierces_too_far_below_the_dip_low_returns_none():
    """A break well past the level, not a shallow retest -- MAX_PIERCE_ATR
    (0.25xATR) exceeded."""
    candles, _ = _long_scenario(retest_open=89.0, retest_low=89.5,
                                retest_high=89.9, retest_close=89.7)
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_retest_bar_closes_bearish_returns_none():
    """The retest bar must close bullish (a rejection), not continue lower."""
    candles, _ = _long_scenario(retest_open=90.3, retest_low=89.95,
                                retest_high=90.5, retest_close=90.0)
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_dip_older_than_max_bars_since_dip_returns_none():
    """Distance from dip to retest is 2 + filler_after_dip; one past
    MAX_BARS_SINCE_DIP is the tightest meaningful "too old" case."""
    candles, _ = _long_scenario(filler_after_dip=MAX_BARS_SINCE_DIP - 1)
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_dip_within_max_bars_since_dip_still_fires():
    """Boundary check the other direction: exactly at the edge of the
    lookback window (distance == MAX_BARS_SINCE_DIP), the dip is still
    found."""
    candles, dip_low = _long_scenario(filler_after_dip=MAX_BARS_SINCE_DIP - 2)
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.entry == dip_low


def test_htf_downtrend_blocks_the_long():
    candles, _ = _long_scenario()
    assert detect_setup("BTCUSD", candles, _atr(candles),
                        htf_trend="down") is None


def test_htf_uptrend_blocks_the_short():
    candles, _ = _short_scenario()
    assert detect_setup("BTCUSD", candles, _atr(candles),
                        htf_trend="up") is None


def test_htf_trend_none_does_not_block_either_direction():
    long_candles, _ = _long_scenario()
    assert detect_setup("BTCUSD", long_candles, _atr(long_candles),
                        htf_trend=None) is not None


def test_no_dip_in_a_flat_series_returns_none():
    candles = _flat(MIN_CANDLES + 5)
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_insufficient_history_is_rejected():
    candles, _ = _long_scenario()
    short = candles[-(MIN_CANDLES - 1):]
    assert detect_setup("BTCUSD", short, _atr(short)) is None


def test_missing_atr_is_rejected():
    candles, _ = _long_scenario()
    atr14 = _atr(candles)
    atr14[-1] = None
    assert detect_setup("BTCUSD", candles, atr14) is None


def test_adx_recorded_but_not_required():
    candles, _ = _long_scenario()
    adx14 = [25.0] * len(candles)
    setup = detect_setup("BTCUSD", candles, _atr(candles), adx14=adx14)
    assert setup is not None
    assert setup.indicators["adx"] == 25.0


# --- _risk_ok isolated unit tests -------------------------------------------
# The detector's own entry/stop coupling keeps real risk/ATR mathematically
# bounded to [1.25, 1.5] (ATR_STOP_BUFFER minus/exactly MAX_PIERCE_ATR) -- so
# MIN_STOP_ATR/MAX_STOP_ATR can never actually fire through detect_setup with
# any realistic candle input. That is the safety design working (no wild
# outliers, unlike ict_fvg's pre-fix construction), not a gap -- but it means
# these two guards have to be verified directly rather than through a full
# scenario. See this plan's header note.

def test_risk_ok_true_within_bounds():
    assert _risk_ok(entry=100.0, stop=98.5, atr_value=1.0) is True  # 1.5x


def test_risk_ok_false_below_min_stop_atr():
    assert _risk_ok(entry=100.0, stop=99.9, atr_value=1.0) is False  # 0.1x


def test_risk_ok_false_above_max_stop_atr():
    assert _risk_ok(entry=100.0, stop=90.0, atr_value=1.0) is False  # 10x


def test_risk_ok_false_at_zero_atr():
    assert _risk_ok(entry=100.0, stop=98.0, atr_value=0.0) is False


def test_risk_ok_boundary_values_are_inclusive():
    assert _risk_ok(entry=100.0, stop=100.0 - MIN_STOP_ATR, atr_value=1.0) is True
    assert _risk_ok(entry=100.0, stop=100.0 - MAX_STOP_ATR, atr_value=1.0) is True
```

- [ ] **Step 3: Run the tests to verify they fail with an import error**

Run: `.venv/bin/python -m pytest tests/strategies/test_rsi2_pullback_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.rsi2_pullback.detector'`

- [ ] **Step 4: Write `detector.py`**

Create `signals/strategies/rsi2_pullback/detector.py`:

```python
"""RSI(2) pullback-in-trend, maker-fill entry.

Finds a short-term RSI(2) extreme (Connors' method), then waits for price to
retest that extreme's own level within a tight lookback -- not a fresh break
-- before firing. Entry prices as a RESTING LIMIT at the extreme's level
(sr_limit's exact convention: entry = min/max of the level and the retest
bar's open, so a gap-through fills at the open, not a level price action
never offered), earning the maker fee in cost_r() instead of a market/taker
fill. Stop sits a further ATR_STOP_BUFFER beyond that same level -- entry and
stop are always anchored to the SAME bar, unlike ict_fvg's decoupled
sweep-bar-vs-current-close construction that caused a near-zero-risk bug (see
docs/ict-fvg-backtest-results.md). See
docs/superpowers/specs/2026-09-06-rsi2-pullback-strategy-design.md.

Not assigned to any live session -- admin-selectable only, pending the
long-history verdict in docs/rsi2-pullback-backtest-results.md.
"""
from signals.analysis.indicators import rsi
from signals.models import CandidateSetup, take_profits_from_risk

RSI_PERIOD = 2  # Connors' period
RSI_LOW = 10  # oversold threshold
RSI_HIGH = 90  # overbought threshold
MAX_BARS_SINCE_DIP = 6  # retest must occur within 30 minutes of the dip (5m bars)
MAX_PIERCE_ATR = 0.25  # how far past the dip level a retest may still reach
RETEST_TOLERANCE_ATR = 0.15  # how far short of the dip level still counts as "reached" it
ATR_STOP_BUFFER = 1.5  # stop distance beyond the dip level (Donchian-convention ATR stop)
MIN_STOP_ATR = 0.5  # floor -- the ict_fvg fix, built in from the start
MAX_STOP_ATR = 3.0  # ceiling -- matches msnr/ict_smc's range
MIN_CANDLES = 30  # RSI(2) warm-up plus margin


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    stop_atr = abs(entry - stop) / atr_value
    return MIN_STOP_ATR <= stop_atr <= MAX_STOP_ATR


def _find_dip_long(candles, rsi2, last_i):
    """Lowest-low bar within MAX_BARS_SINCE_DIP (strictly before `last_i`)
    whose RSI(2) was below RSI_LOW, or None.

    Ranked by price extremity, not recency: Wilder-smoothed RSI(2) can stay
    pinned below RSI_LOW for several bars after the actual extreme (avg_gain
    stays at 0 until a real bounce prints — verified directly against this
    repo's own `rsi()`), so "most recent qualifying bar" would pick a later,
    shallower low instead of the level actually worth retesting.
    """
    start = max(0, last_i - MAX_BARS_SINCE_DIP)
    candidates = [i for i in range(start, last_i)
                 if rsi2[i] is not None and rsi2[i] < RSI_LOW]
    if not candidates:
        return None
    return min(candidates, key=lambda i: candles[i].low)


def _find_dip_short(candles, rsi2, last_i):
    start = max(0, last_i - MAX_BARS_SINCE_DIP)
    candidates = [i for i in range(start, last_i)
                 if rsi2[i] is not None and rsi2[i] > RSI_HIGH]
    if not candidates:
        return None
    return max(candidates, key=lambda i: candles[i].high)


def _indicators(rsi2_value, atr_value, adx14, htf_trend, extra):
    out = {"strategy": "rsi2_pullback", "entry_style": "limit",
          "rsi2": rsi2_value, "atr": atr_value, **extra}
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _long_setup(symbol, candles, atr_value, rsi2, adx14, htf_trend):
    if htf_trend == "down":
        return None
    last_i = len(candles) - 1
    dip_i = _find_dip_long(candles, rsi2, last_i)
    if dip_i is None:
        return None
    dip_low = candles[dip_i].low
    bar = candles[last_i]
    if bar.close <= bar.open:
        return None
    if bar.low < dip_low - MAX_PIERCE_ATR * atr_value:
        return None
    if bar.low > dip_low + RETEST_TOLERANCE_ATR * atr_value:
        return None
    entry = min(dip_low, bar.open)
    stop = dip_low - ATR_STOP_BUFFER * atr_value
    if stop >= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
    indicators = _indicators(
        rsi2[last_i], atr_value, adx14, htf_trend,
        {"dip_low": dip_low, "dip_time": candles[dip_i].open_time},
    )
    return CandidateSetup(
        symbol, "long", entry, stop, tp1, indicators,
        take_profit_2=tp2, take_profit_3=tp3,
    )


def _short_setup(symbol, candles, atr_value, rsi2, adx14, htf_trend):
    if htf_trend == "up":
        return None
    last_i = len(candles) - 1
    dip_i = _find_dip_short(candles, rsi2, last_i)
    if dip_i is None:
        return None
    dip_high = candles[dip_i].high
    bar = candles[last_i]
    if bar.close >= bar.open:
        return None
    if bar.high > dip_high + MAX_PIERCE_ATR * atr_value:
        return None
    if bar.high < dip_high - RETEST_TOLERANCE_ATR * atr_value:
        return None
    entry = max(dip_high, bar.open)
    stop = dip_high + ATR_STOP_BUFFER * atr_value
    if stop <= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
    indicators = _indicators(
        rsi2[last_i], atr_value, adx14, htf_trend,
        {"dip_high": dip_high, "dip_time": candles[dip_i].open_time},
    )
    return CandidateSetup(
        symbol, "short", entry, stop, tp1, indicators,
        take_profit_2=tp2, take_profit_3=tp3,
    )


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on an RSI(2) pullback-in-trend retest, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None
    closes = [c.close for c in candles]
    rsi2 = rsi(closes, RSI_PERIOD)

    setup = _long_setup(symbol, candles, atr_value, rsi2, adx14, htf_trend)
    if setup is not None:
        return setup
    return _short_setup(symbol, candles, atr_value, rsi2, adx14, htf_trend)
```

- [ ] **Step 5: Write the package `__init__.py`**

Create `signals/strategies/rsi2_pullback/__init__.py` (mirrors `ict_fvg`, `msnr`):

```python
from signals.strategies.rsi2_pullback.detector import detect_setup

__all__ = ["detect_setup"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/strategies/test_rsi2_pullback_detector.py -v`
Expected: PASS — 22 tests

- [ ] **Step 7: Commit**

```bash
git add signals/strategies/rsi2_pullback/ tests/strategies/test_rsi2_pullback_detector.py
git commit -m "feat(rsi2_pullback): add RSI(2) pullback-in-trend detector with resting-limit entry"
```

---

## Task 2: Router dispatch and strategy registration

**Files:**
- Modify: `signals/strategies/router.py`
- Modify: `signals/models.py`
- Test: `tests/strategies/test_rsi2_pullback_router.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/strategies/test_rsi2_pullback_router.py` (mirrors `test_orb_rvol_router.py`):

```python
"""rsi2_pullback must be dispatchable through the shared router."""
from signals.models import Candle, SIGNAL_STRATEGIES
from signals.strategies import detect_setup


def _candles(n):
    return [Candle(i * 300_000, 100.0, 100.2, 99.8, 100.0, 1.0)
            for i in range(n)]


def test_key_is_registered():
    assert "rsi2_pullback" in SIGNAL_STRATEGIES


def test_router_dispatches_without_error():
    n = 40
    candles = _candles(n)
    result = detect_setup(
        "rsi2_pullback", "BTCUSD", candles,
        [None] * n, [None] * n, [None] * n, [None] * n, [1.0] * n,
        adx14=None, htf_trend=None, h1_candles=None,
    )
    # A perfectly flat synthetic series has no RSI(2) extreme to retest --
    # the point of this test is that dispatch itself does not raise, not
    # that a setup fires.
    assert result is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_rsi2_pullback_router.py -v`
Expected: FAIL — `AssertionError` on `test_key_is_registered` (`rsi2_pullback` not yet in `SIGNAL_STRATEGIES`)

- [ ] **Step 3: Add `rsi2_pullback` dispatch to the router**

In `signals/strategies/router.py`, add the import (insert alphabetically, after the `orb_rvol` import and before `sr_zone`):

```python
from signals.strategies.rsi2_pullback import detect_setup as detect_rsi2_pullback_setup
```

Add a new branch inside `detect_setup`, right after the `orb_rvol` branch:

```python
    if strategy == "rsi2_pullback":
        return detect_rsi2_pullback_setup(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
```

- [ ] **Step 4: Add `"rsi2_pullback"` to `SIGNAL_STRATEGIES` in `signals/models.py`**

Change:

```python
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry", "cloud_mss", "msnr",
                     "orb_rvol")
```

to:

```python
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry", "cloud_mss", "msnr",
                     "orb_rvol", "rsi2_pullback")
```

(`ADMIN_SELECTABLE_STRATEGIES` is handled in Task 3 — do not touch it here.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_rsi2_pullback_router.py -v`
Expected: PASS — 2 tests

- [ ] **Step 6: Run the full strategies test directory to check for regressions**

Run: `.venv/bin/python -m pytest tests/strategies/ -v`
Expected: PASS — all tests, including every other strategy's router tests

- [ ] **Step 7: Commit**

```bash
git add signals/strategies/router.py signals/models.py tests/strategies/test_rsi2_pullback_router.py
git commit -m "feat(rsi2_pullback): register the strategy and wire router dispatch"
```

---

## Task 3: Admin-selectable sync — `ADMIN_SELECTABLE_STRATEGIES`, migration, admin dropdown

**Files:**
- Modify: `signals/models.py`
- Modify: `web/src/lib/supabase/admin.ts`
- Create: `supabase/migrations/20260906000000_allow_rsi2_pullback_strategy.sql`
- Test: `tests/core/test_strategy_choices.py` (existing — no edits, just must keep passing)

Python, the admin dropdown, and the Postgres CHECK constraint must all agree
in the SAME ORDER — `test_admin_dropdown_matches_python` and
`test_database_constraint_matches_python` both do an exact tuple-order
comparison against `ADMIN_SELECTABLE_STRATEGIES`, not just a set comparison.
Appending `rsi2_pullback` at the end in all three places (matching exactly
how `orb_rvol` itself was appended last time) keeps this trivially correct.

- [ ] **Step 1: Confirm the pinning test currently passes (baseline before the change)**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: PASS — 5 tests (`rsi2_pullback` is not yet in any of the three sources, so they still agree with each other)

- [ ] **Step 2: Add `"rsi2_pullback"` to `ADMIN_SELECTABLE_STRATEGIES` in `signals/models.py`**

Change:

```python
ADMIN_SELECTABLE_STRATEGIES = ("ema_cross", "ict_smc", "sr_zone",
                               "bbma_reentry", "bbma_extreme", "orb_rvol")
```

to:

```python
ADMIN_SELECTABLE_STRATEGIES = ("ema_cross", "ict_smc", "sr_zone",
                               "bbma_reentry", "bbma_extreme", "orb_rvol",
                               "rsi2_pullback")
```

- [ ] **Step 3: Run the pinning test to see it fail against the other two sources**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: FAIL — `test_admin_dropdown_matches_python` and `test_database_constraint_matches_python` both fail (Python now has `rsi2_pullback`, the other two don't yet)

- [ ] **Step 4: Add the dropdown entry to `web/src/lib/supabase/admin.ts`**

In the `SIGNAL_STRATEGIES` array, after the `orb_rvol` entry and before the closing `] as const;`, add:

```typescript
  {
    id: "rsi2_pullback",
    label: "RSI(2) Pullback (maker-fill)",
    description:
      "Buys/sells a retest of a short-term RSI(2) extreme within an HTF-confirmed trend, using a resting limit order at the extreme's own level (earns the maker fee) and a ~1.5x ATR stop. Not yet backtested over long history — see docs/rsi2-pullback-backtest-results.md once available.",
  },
```

- [ ] **Step 5: Create the migration**

Create `supabase/migrations/20260906000000_allow_rsi2_pullback_strategy.sql` (mirrors `20260817010000_allow_orb_rvol_strategy.sql`):

```sql
-- Allow the swing session to be switched to rsi2_pullback.
--
-- Only the SWING session reads bot_settings.signal_strategy; the scalp
-- sessions pin their own strategy in TRADING_SESSIONS and ignore the toggle.
-- So this set must stay identical to:
--
--   * signals.models.ADMIN_SELECTABLE_STRATEGIES
--   * SIGNAL_STRATEGIES in web/src/lib/supabase/admin.ts (the dropdown)
--
-- tests/core/test_strategy_choices.py pins all three together.
--
-- rsi2_pullback is NOT assigned to a live TRADING_SESSIONS slot by this
-- migration or the work that introduced it -- it is admin-selectable only
-- so it can be tried manually, pending the long-history verdict in
-- docs/rsi2-pullback-backtest-results.md. See
-- docs/superpowers/specs/2026-09-06-rsi2-pullback-strategy-design.md.
--
-- Idempotent: re-creating the constraint is safe.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone',
                               'bbma_reentry', 'bbma_extreme', 'orb_rvol',
                               'rsi2_pullback'));
```

- [ ] **Step 6: Run the pinning test to verify all three sources agree**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: PASS — 5 tests

- [ ] **Step 7: Run the full Python test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no failures

- [ ] **Step 8: Commit**

```bash
git add signals/models.py web/src/lib/supabase/admin.ts supabase/migrations/20260906000000_allow_rsi2_pullback_strategy.sql
git commit -m "feat(rsi2_pullback): make the strategy admin-selectable (Python + dropdown + DB constraint)"
```

> Note: this migration is not applied to the live database by this plan — that is a separate, deliberate operational step (running `supabase db push` or equivalent against production), out of scope here. Flag it to the user before applying.

---

## Task 4: No-setup indicators in the scan pipeline

**Files:**
- Modify: `signals/pipeline/scan.py`
- Test: `tests/core/test_rsi2_pullback_no_setup_indicators.py`

`_no_setup_indicators` decides what gets logged to `ai_events` when a
strategy finds nothing — every strategy needs a branch or it silently falls
through to the generic EMA/RSI/MACD fallback, which would log misleading
fields for a strategy that uses none of them.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_rsi2_pullback_no_setup_indicators.py`:

```python
"""rsi2_pullback must not fall through to the generic EMA/RSI/MACD no-setup
indicators -- that would log misleading fields for a strategy that uses none
of them (see orb_rvol's/cloud_mss's equivalent regression tests)."""
from signals.pipeline.scan import _no_setup_indicators


def test_rsi2_pullback_no_setup_indicators_are_strategy_tagged():
    indicators = _no_setup_indicators(
        "rsi2_pullback", [1.5] * 5, [25.0] * 5, "up",
        [1.0] * 5, [1.0] * 5, [50.0] * 5, [0.0] * 5,
    )
    assert indicators["strategy"] == "rsi2_pullback"
    assert indicators["atr"] == 1.5
    assert indicators["adx"] == 25.0
    assert indicators["htf_trend"] == "up"
    assert "ema9" not in indicators
    assert "rsi" not in indicators


def test_rsi2_pullback_no_setup_indicators_none_while_atr_warms_up():
    assert _no_setup_indicators(
        "rsi2_pullback", [None], [None], None, [None], [None], [None], [None],
    ) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_rsi2_pullback_no_setup_indicators.py -v`
Expected: FAIL — `test_rsi2_pullback_no_setup_indicators_are_strategy_tagged` gets `ema9`/`rsi` keys instead (falls through to the generic branch)

- [ ] **Step 3: Add `rsi2_pullback` to the strategy tuple**

In `signals/pipeline/scan.py`, inside `_no_setup_indicators`, change:

```python
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "cloud_mss", "orb_rvol"):
```

to:

```python
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "cloud_mss", "orb_rvol",
                    "rsi2_pullback"):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_rsi2_pullback_no_setup_indicators.py -v`
Expected: PASS — 2 tests

- [ ] **Step 5: Run the full pipeline test directory to check for regressions**

Run: `.venv/bin/python -m pytest tests/core/ -q`
Expected: PASS — no failures

- [ ] **Step 6: Commit**

```bash
git add signals/pipeline/scan.py tests/core/test_rsi2_pullback_no_setup_indicators.py
git commit -m "feat(rsi2_pullback): tag no-setup ai_events with strategy-specific indicators"
```

---

## Task 5: LLM confirmation prompt — no-setup reason, indicator formatting, strategy line

**Files:**
- Modify: `signals/pipeline/composer.py`
- Modify: `tests/core/test_composer.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_composer.py`:

```python
def test_build_messages_rsi2_pullback_does_not_crash_on_missing_ema9():
    """rsi2_pullback indicators have no ema9/ema21/rsi/macd_hist keys -- the
    generic EMA fallback in _format_indicators must not be reached for it."""
    setup = CandidateSetup(
        symbol="BTCUSD", direction="long", entry=64500.0,
        stop_loss=64100.0, take_profit=65300.0,
        indicators={
            "strategy": "rsi2_pullback", "entry_style": "limit",
            "rsi2": 6.4, "dip_low": 64450.0, "atr": 120.0,
        },
    )
    user_content = build_messages(setup, strategy="rsi2_pullback")[1]["content"]
    assert "rsi(2)" in user_content.lower() or "rsi2" in user_content.lower()


def test_confirm_setup_rsi2_pullback_calls_llm_instead_of_fail_closed_rejecting():
    """Regression guard, same shape as orb_rvol's/cloud_mss's: a broken
    _format_indicators branch would make every rsi2_pullback candidate crash
    inside build_messages, which confirm_setup silently turns into a
    fail-closed reject without ever calling the LLM."""
    setup = CandidateSetup(
        symbol="BTCUSD", direction="long", entry=64500.0,
        stop_loss=64100.0, take_profit=65300.0,
        indicators={
            "strategy": "rsi2_pullback", "entry_style": "limit",
            "rsi2": 6.4, "dip_low": 64450.0, "atr": 120.0,
        },
    )
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 65, "rationale": "ok"}')
    result = confirm_setup(setup, llm, strategy="rsi2_pullback")
    assert llm.last_messages is not None
    assert result.verdict == "confirm"


def test_no_setup_rationale_rsi2_pullback():
    from signals.pipeline.composer import no_setup_rationale

    rationale = no_setup_rationale(
        "BTCUSD", "5m",
        {"strategy": "rsi2_pullback", "atr": 120.0},
        strategy="rsi2_pullback",
    )
    assert "rsi(2)" in rationale.lower() or "rsi2" in rationale.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -k rsi2_pullback -v`
Expected: FAIL — all three (no `rsi2_pullback` branch exists yet in any of `_no_setup_reason`, `_format_indicators`, or `build_messages`)

- [ ] **Step 3: Add the `rsi2_pullback` branch to `_no_setup_reason`**

In `signals/pipeline/composer.py`, inside `_no_setup_reason`, add (after the `orb_rvol` branch, before the `bbma_extreme`/`bbma_reentry` one):

```python
    if strategy == "rsi2_pullback":
        return (
            f"The rules engine found no valid RSI(2) pullback setup (need a "
            f"short-term RSI(2) extreme retested within {6} bars, in the "
            f"direction of the higher-timeframe trend, on the {chart})."
        )
```

- [ ] **Step 4: Add the `rsi2_pullback` branch to `_format_indicators`**

In the same file, inside `_format_indicators`, add (after the `orb_rvol` branch, before the `bbma_extreme`/`bbma_reentry` one):

```python
    if active == "rsi2_pullback":
        parts = []
        for key, label in (
            ("rsi2", "RSI(2)"),
            ("dip_low", "dip low"),
            ("dip_high", "dip high"),
            ("entry_style", "entry"),
            ("atr", "ATR"),
            ("adx", "ADX"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no RSI(2) reading"
```

- [ ] **Step 5: Add the `rsi2_pullback` branch to `build_messages`**

In the same file, inside `build_messages`, add (after the `orb_rvol` `elif`, before the `bbma_extreme` one):

```python
    elif active == "rsi2_pullback":
        rsi2_value = ind.get("rsi2")
        rsi2_text = f"{rsi2_value:.1f}" if isinstance(rsi2_value, float) else "n/a"
        strategy_line = (
            f"- Strategy: RSI(2) Pullback, maker-fill entry (RSI(2)={rsi2_text} "
            f"retest of a short-term extreme; resting limit at the extreme's "
            f"own level; ~1.5x ATR stop; HTF-trend gated)\n"
        )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -k rsi2_pullback -v`
Expected: PASS — 3 tests

- [ ] **Step 7: Run the full composer test file to check for regressions**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -v`
Expected: PASS — all tests

- [ ] **Step 8: Commit**

```bash
git add signals/pipeline/composer.py tests/core/test_composer.py
git commit -m "feat(rsi2_pullback): wire the LLM confirmation prompt and no-setup rationale"
```

---

## Task 6: RAG playbook chunks

**Files:**
- Modify: `signals/rag/playbook.py`
- Test: `tests/rag/test_rag.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/rag/test_rag.py`:

```python
def test_playbook_covers_rsi2_pullback():
    chunks = [c for c in PLAYBOOK_CHUNKS if c["strategy"] == "rsi2_pullback"]
    assert len(chunks) == 2
    titles = {c["title"].lower() for c in chunks}
    assert any("confirm" in t for t in titles)
    assert any("reject" in t for t in titles)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/rag/test_rag.py::test_playbook_covers_rsi2_pullback -v`
Expected: FAIL — `assert 0 == 2`

- [ ] **Step 3: Add the two chunks**

In `signals/rag/playbook.py`, add to the `PLAYBOOK_CHUNKS` tuple, after the `orb_rvol` chunks, right before the closing `)`:

```python
    {
        "strategy": "rsi2_pullback",
        "title": "5m RSI(2) Pullback confirm gate",
        "body": (
            "rsi2_pullback: Larry Connors' RSI(2) mean-reversion method -- a "
            "short-term RSI(2) dip below 10 (long) or spike above 90 "
            "(short), retested within 6 bars, in the direction of the "
            "15m higher-timeframe trend (a hard gate, not a soft "
            "preference). Entry is a RESTING LIMIT at the extreme's own "
            "level, not a market fill -- earns the maker fee, which is the "
            "entire point of this strategy relative to ict_fvg's failed "
            "market-entry 5m attempt (docs/ict-fvg-backtest-results.md). "
            "Stop sits ~1.5x ATR beyond the level -- deliberately wide for "
            "a 5m detector. Confirm when the retest bar closed bullish "
            "(long) or bearish (short) and HTF trend agrees or is unknown."
        ),
    },
    {
        "strategy": "rsi2_pullback",
        "title": "5m RSI(2) Pullback reject cues",
        "body": (
            "Reject rsi2_pullback when the higher-timeframe trend directly "
            "opposes the setup's direction (the hard gate), when the "
            "retest bar closed the wrong way (bearish on a long, bullish "
            "on a short -- not a rejection), or when the retest pierced "
            "well past the dip/spike level rather than a shallow touch. Do "
            "not reject solely for a wide-looking stop -- ~1.5x ATR is by "
            "design here, not a red flag the way a tight ict_fvg stop was."
        ),
    },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/rag/test_rag.py -v`
Expected: PASS — all tests, including the new one and the pre-existing `test_playbook_covers_all_strategies`

- [ ] **Step 5: Commit**

```bash
git add signals/rag/playbook.py tests/rag/test_rag.py
git commit -m "feat(rsi2_pullback): add RAG playbook confirm-gate and reject-cue chunks"
```

---

## Task 7: Long-history verdict — `scripts/rsi2_pullback_history_report.py`

**Files:**
- Create: `scripts/rsi2_pullback_history_report.py`

This is the actual gate. Modeled directly on `scripts/msnr_history_report.py`
(the simpler, no-pipeline-gate shape — `rsi2_pullback`, like `msnr`, isn't
wired into any live session yet, so there is no `scan.py`-level gate to
replicate). The one deliberate methodology difference from every taker-fill
strategy's report script: **`bps=MAKER_BPS`**, mirroring exactly how
`scripts/history_sweep.py` scores `sr_limit` — because this detector rests a
limit order, charging it the taker rate would measure a strategy nobody
would actually run. Do not "fix" this back to the default; it is deliberate,
not an oversight.

- [ ] **Step 1: Write the script**

Create `scripts/rsi2_pullback_history_report.py`:

```python
"""rsi2_pullback backtested over the full verified Binance history (~8.9 years).

Same data and harness as scripts/msnr_history_report.py: SHA256-verified
monthly archives (scripts/history_provenance.py -- run that first if you have
not), replayed through backtest_windowed so a setup only counts here if it
would have fired live.

`bps=MAKER_BPS` is passed to backtest_windowed -- the one deliberate
difference from ict_fvg_history_report.py's default (taker) rate. This
detector rests a limit order at the dip/spike level (entry_style="limit" in
its own indicators); charging it the 20bps taker fee would score a strategy
that isn't the one this detector actually is. See
scripts/history_sweep.py's identical treatment of sr_limit and
docs/superpowers/specs/2026-09-06-rsi2-pullback-strategy-design.md.

Binance lists no gold, so XAUUSD is not covered here -- see
signals.analysis.backtest.main for a shorter, live-API-paginated check
instead (not registered in STRATEGY_TIMEFRAMES by this work -- see this
plan's header note on why the backtest.py quick-check registration was
skipped).

`rsi2_pullback` isn't wired into any live session yet, so unlike
ict_fvg_history_report.py there is no pipeline-level gate to replicate here.

Usage: .venv/bin/python -m scripts.rsi2_pullback_history_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed, htf_trend_series
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.analysis.r_model import MAKER_BPS
from signals.strategies.rsi2_pullback.detector import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "5m"
CONFLUENCE_TIMEFRAME = "15m"
CONFLUENCE_MINUTES = 15
WINDOW = 200
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled_gross, pooled_net = [], []

    print("rsi2_pullback over the full verified Binance history. Scale-out "
          "model: 1/3 at each of TP1/TP2/TP3 (1R/2R/3R), fixed stop as "
          "published. Scored at the MAKER fee rate (4bps) -- this detector "
          "rests a limit order, not a market fill.")
    print(f"{WINDOW}-bar rolling window (matches ScanConfig.candle_limit-1 -- "
          "the live scan's own view). Gated on 15m HTF trend (hard filter "
          "inside the detector).\n")
    print(f"{'symbol':7} {'years':>6} {'bars':>7} {'trades':>7} {'tp1%':>6} "
          f"{'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>9}")
    print("-" * 70)

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        htf_candles = load_history(symbol, CONFLUENCE_TIMEFRAME, session=session)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = htf_trend_series(candles, htf_candles, CONFLUENCE_MINUTES)

        out = backtest_windowed(detect_setup, symbol, candles, atr14, trends,
                                window=WINDOW, max_hold=MAX_HOLD, bps=MAKER_BPS)
        gross, net = out["gross"], out["net"]
        trades = len(gross)
        pooled_gross += gross
        pooled_net += net

        years = ((candles[-1].open_time - candles[0].open_time)
                 / 1000 / 86400 / 365.25)
        if trades:
            print(f"{symbol:7} {years:6.2f} {len(candles):7d} {trades:7d} "
                  f"{out['tp1_hits'] / trades * 100:5.1f}% "
                  f"{out['tp3_hits'] / trades * 100:5.1f}% "
                  f"{statistics.mean(gross):+6.3f}R "
                  f"{statistics.mean(net):+6.3f}R "
                  f"{sum(net):+8.1f}R")
        else:
            print(f"{symbol:7} {years:6.2f} {len(candles):7d} {0:7d}   "
                  "no trades")

    print("\n" + "=" * 70)
    n = len(pooled_net)
    if n < 2:
        print(f"POOLED n={n} -- too few to summarise")
        return
    mean = statistics.mean(pooled_net)
    sd = statistics.stdev(pooled_net)
    se = sd / (n ** 0.5)
    print(f"POOLED n={n:5d}  gross={statistics.mean(pooled_gross):+.3f}R  "
          f"net={mean:+.3f}R  sd={sd:.3f}  t={mean / se:+.2f}  "
          f"95% CI [{mean - 1.96 * se:+.3f}, {mean + 1.96 * se:+.3f}]  "
          f"total={sum(pooled_net):+.1f}R")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script imports cleanly**

Run: `.venv/bin/python -c "from scripts.rsi2_pullback_history_report import main; print('ok')"`
Expected: `ok` (confirms `backtest_windowed`, `htf_trend_series`, `load_history`, `MAKER_BPS`, and the detector all resolve)

- [ ] **Step 3: Commit**

```bash
git add scripts/rsi2_pullback_history_report.py
git commit -m "feat(rsi2_pullback): add the long-history backtest report script (maker fee rate)"
```

---

## Task 8: Run the full suite, run the verdict, record the result

**Files:**
- Create: `docs/rsi2-pullback-backtest-results.md`

- [ ] **Step 1: Run the complete Python test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — every test, including all `rsi2_pullback` tests added in Tasks 1–6 and no regressions anywhere else

- [ ] **Step 2: Run data provenance verification (skip if the cache is already warm from prior reports)**

Run: `.venv/bin/python -m scripts.history_provenance`
Expected: prints SHA256 verification results and known-market-event checks, all passing.

- [ ] **Step 3: Run the long-history report and capture its output**

Run: `.venv/bin/python -m scripts.rsi2_pullback_history_report | tee /tmp/rsi2_pullback_report_output.txt`
Expected: a table (BTCUSD row, ETHUSD row) followed by a POOLED summary line with `net=`, `sd=`, `t=`, and a 95% CI. 5m over 8.9+ years is a large bar count (comparable to `ict_fvg_history_report.py`'s run) — expect this to take a while.

- [ ] **Step 4: Sanity-check the distribution before trusting the headline number**

This is the exact check that caught `ict_fvg`'s near-zero-risk bug earlier in
this project (`docs/ict-fvg-backtest-results.md`) — run it every time, even
though this detector was specifically designed to avoid that failure mode
structurally. Do not skip it just because the design is safer on paper.

Run:

```bash
.venv/bin/python - <<'EOF'
import statistics
from signals.analysis.backtest import backtest_windowed, htf_trend_series
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.analysis.r_model import MAKER_BPS
from signals.strategies.rsi2_pullback.detector import detect_setup
import requests

session = requests.Session()
for symbol in ("BTCUSD", "ETHUSD"):
    candles = load_history(symbol, "5m", session=session)
    htf_candles = load_history(symbol, "15m", session=session)
    highs = [c.high for c in candles]; lows = [c.low for c in candles]; closes = [c.close for c in candles]
    atr14 = atr(highs, lows, closes, 14)
    trends = htf_trend_series(candles, htf_candles, 15)
    out = backtest_windowed(detect_setup, symbol, candles, atr14, trends,
                            window=200, max_hold=2000, bps=MAKER_BPS)
    net = sorted(out["net"])
    n = len(net)
    def pct(p):
        return net[int(p / 100 * (n - 1))]
    print(symbol, "n", n, "median", round(pct(50), 3), "mean", round(statistics.mean(net), 3),
          "p1", round(pct(1), 3), "p99", round(pct(99), 3),
          "min", round(net[0], 2), "max", round(net[-1], 2))
EOF
```

Expected, given `ATR_STOP_BUFFER=1.5` and the scale-out ladder tops out at
+2R: a plausible spread roughly bounded near `[-2, +2]` per trade (allowing
some room either side for the maker-fee adjustment and TP-hit variability),
no multi-hundred-R outliers, and median reasonably close to mean (no
extreme skew). **If the distribution looks anything like `ict_fvg`'s original
broken run (wild min/max, mean far from median, sd blown out) — stop and
diagnose before writing the results doc; do not report a number you have not
sanity-checked.**

- [ ] **Step 5: Write `docs/rsi2-pullback-backtest-results.md`**

Using the actual numbers from Steps 3–4's output (not placeholder numbers —
copy the real printed table, POOLED line, and distribution check), write the
results doc following the same shape and tone as
`docs/msnr-backtest-results.md` and `docs/orb-rvol-backtest-results.md`
(both written this session) — **the honest answer, whichever direction it
comes out, with no lean toward "and then we promote it."** Promotion is out
of scope for this task regardless of the number; that decision belongs to
the user once the number is in, per this spec's "Out of scope" section.

Include:

- A headline stating plainly whether `rsi2_pullback` is net profitable at
  the measured net expectancy and t-statistic.
- The full per-symbol table and pooled statistics, verbatim from the
  report's output, plus the distribution sanity-check numbers from Step 4
  (median vs mean, percentile spread, min/max) — stated explicitly as the
  check that caught `ict_fvg`'s bug, confirming this result was verified the
  same way even though no bug was expected here.
- A comparison against every other strategy's net-per-trade number already
  on record in this repo (reuse the table from
  `docs/ict-fvg-backtest-results.md`'s "Where msnr sits" section as the base
  and add this result to it): `bbma_reentry` +0.120R, `sr_limit` (maker)
  −0.015R, `bbma_extreme` −0.019R to −0.153R, `cloud_mss` −0.046R, `msnr`
  −0.168R, `bbma_reentry` (15m-equivalent scope) −0.137R, `orb_rvol`
  −0.238R, `sr_zone` −0.415R, `ict_fvg` −1.253R (pulled).
- If net is positive: state clearly this is a candidate for the silent
  `super_scalp`/`xau_scalp` slot, but that assigning it there is a decision
  for the user with the number in hand — do not make that call in this task.
- If net is negative: state clearly this specific concept did not overcome
  the cost mechanism either, note where it falls in the table above, and
  that the silent scalp slot remains open pending a different concept — same
  honest-negative-result tone as `docs/orb-rvol-backtest-results.md` and
  `docs/msnr-backtest-results.md`.
- The standard caveats this repo states for every Binance-archive report:
  crypto only (no `XAUUSD`/`GBPUSD` coverage), BTC/ETH correlation narrows
  the effective independent sample size below the raw trade count, no
  profitability tuning was performed after seeing the result.

- [ ] **Step 6: Commit**

```bash
git add docs/rsi2-pullback-backtest-results.md
git commit -m "docs(rsi2-pullback): record the long-history backtest verdict"
```

---

## Self-Review Notes

**Spec coverage:** Goal/"Why this concept" → context, no dedicated task (informs Task 8's writeup). Research basis / "Considered and rejected" → context only, no code. Detector contract & Algorithm (10 steps) → Task 1, translated step-for-step (guard clause → guard clause; HTF gate → `htf_trend == "down"/"up"` checks; RSI(2) scan → `rsi(closes, RSI_PERIOD)` + `_find_dip_long`/`_find_dip_short`; retest bounds → the `MAX_PIERCE_ATR`/`RETEST_TOLERANCE_ATR` checks; resting-limit entry → `min`/`max` with `bar.open`; stop → `ATR_STOP_BUFFER`; risk check → `_risk_ok`; targets → `take_profits_from_risk`; indicators → `_indicators()`). "Why entry and stop stay tightly coupled" → directly produced the `MAX_BARS_SINCE_DIP=6` bound and `MIN_STOP_ATR` floor in Task 1, plus the header note explaining why those bounds are tested in isolation. Parameters table → all eight constants defined once in `detector.py`, matching the spec's values exactly (`ATR_STOP_BUFFER=1.5`, not the earlier draft's 1.0 — this plan copied the corrected spec). Measurement section → Task 7, including the `bps=MAKER_BPS` requirement and its justification comment. File layout → Task 1 (single file, no `windows.py`, as specified). Integration table → Tasks 2–6, one task per row group, skipping the `backtest.py` row (the spec never listed one — it modeled measurement on `msnr_history_report.py`, which also skipped it). Testing section → Task 1's test list, with the `MIN_STOP_ATR`/`MAX_STOP_ATR` items redirected to isolated `_risk_ok` tests per this plan's header note (a testing-strategy decision, not a spec deviation — the guard itself is still implemented and still tested, just not through an unreachable full-detector path). Out of scope → correctly left undone (no `TRADING_SESSIONS` edit anywhere in this plan; no gold coverage; no literal-Connors variant; no post-result parameter sweep).

**Placeholder scan:** No TBD/TODO markers. Task 8's results-doc step is necessarily written against real output this plan cannot pre-compute (an actual 8.9-year backtest run), so it specifies exactly what to capture, what to sanity-check first, and how to structure the writeup rather than pre-filling numbers — that is data collection, not an unresolved design decision, the same distinction `orb_rvol`'s plan made in its own Task 10.

**Type/signature consistency:** `detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None)` is identical across Task 1's detector, Task 2's router branch and router test, and Task 7's `backtest_windowed` call convention — checked against `msnr`'s identical signature as the template. `RSI_PERIOD`, `RSI_LOW`, `RSI_HIGH`, `MAX_BARS_SINCE_DIP`, `MAX_PIERCE_ATR`, `RETEST_TOLERANCE_ATR`, `ATR_STOP_BUFFER`, `MIN_STOP_ATR`, `MAX_STOP_ATR`, `MIN_CANDLES` are each defined once in `detector.py` and referenced (not redefined) everywhere else they matter (Task 1's tests import them). `_risk_ok(entry, stop, atr_value)` signature matches its five isolated unit tests exactly. Indicator keys (`strategy`, `entry_style`, `rsi2`, `dip_low`, `dip_high`, `dip_time`, `atr`, `adx`, `htf_trend`) are consistent between Task 1's detector, Task 4's no-setup indicators test, Task 5's composer branches and tests, and Task 6's playbook chunk descriptions — `dip_low` is long-only and `dip_high` is short-only, and Task 5's `_format_indicators` branch checks both keys optionally rather than assuming one.

**Executed, not just read — Task 1's exact code was run.** Rather than trust the code blocks by inspection alone, `detector.py`, `__init__.py`, and the full test file were extracted from this plan verbatim and run for real (in a scratch location, not committed) against this repo's actual `signals.analysis.indicators.rsi`/`signals.models`. The first attempt caught a real bug this way: Wilder-smoothed RSI(2) stays pinned at its extreme value for every subsequent flat bar (avg_gain stays at 0 until an actual bounce prints — confirmed directly, not assumed), so a "most recent bar below threshold" dip-finder picked a later, shallower bar instead of the true extreme once any filler bars were added. Fixed by ranking candidates by price extremity (`min`/`max` by low/high) instead of recency, and the test helpers were given an explicit recovery bar so RSI(2) genuinely clears the threshold before the lookback-staleness tests mean what they claim to. All 21 tests in Task 1 pass against the plan's own code as written, unmodified from what appears above — an implementer following Task 1 verbatim will hit a working, already-debugged first task rather than rediscovering this.
