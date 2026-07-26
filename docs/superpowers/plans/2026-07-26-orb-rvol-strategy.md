# ORB + Relative Volume Strategy (`orb_rvol`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a session Opening Range Breakout strategy, gated on relative volume, as an admin-selectable playbook — without changing any live signal behaviour.

**Architecture:** A new `signals/strategies/orb_rvol/` package split into `windows.py` (UTC session-anchor arithmetic, opening-range slicing, relative volume) and `detector.py` (entry/stop/TP rules), dispatched from `router.py` exactly like `sr_zone`. `TRADING_SESSIONS` is untouched, so the engine keeps running its current strategies; the new one is reachable only via the `/admin` dropdown and the backtester.

**Tech Stack:** Python 3, pytest, stdlib `datetime` only. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md`

---

## Background for the implementer

You are adding the sixth strategy to a pluggable system. Read
`signals/strategies/sr_zone/detector.py` first — it is the closest existing
analogue and the one whose wiring this plan mirrors.

Two things make this strategy different from every existing detector, and both
are load-bearing:

1. **It reads `Candle.volume`.** No other detector does. The relative-volume
   gate is the entire reason this strategy is worth adding — see the spec's
   research table, where removing it drops the source paper's Sharpe from 2.81
   to 0.48.
2. **It is time-of-day aware.** `Candle.open_time` is **epoch milliseconds**.
   The strategy only trades within fixed UTC windows after 00:00, 07:00 and
   13:30.

`detect_setup` is **stateless** — the engine calls it once per closed bar with
the full candle history. Anything resembling memory ("has this session already
fired?") must be re-derived from the candles each call.

**Virtual environment note:** this project's `.venv/bin/pip` shim is broken.
Always use `.venv/bin/python -m pytest` and `.venv/bin/python -m pip`.

**Repo test convention:** plain pytest functions (no classes), synthetic
`Candle` lists built inline, private `_helper` functions at the top of the
file. Each test file is self-contained — the small builder helpers are
duplicated between the two test files on purpose, matching how every existing
`tests/strategies/*.py` file defines its own `_c`.

---

## File Structure

| File | Responsibility |
|---|---|
| `signals/strategies/orb_rvol/__init__.py` | Re-export `detect_setup` |
| `signals/strategies/orb_rvol/windows.py` | Session anchors, OR/window slicing, relative volume |
| `signals/strategies/orb_rvol/detector.py` | Entry / stop / TP rules |
| `tests/strategies/test_orb_rvol_windows.py` | Unit tests for `windows.py` |
| `tests/strategies/test_orb_rvol_detector.py` | Unit tests for `detector.py` + router dispatch |
| `signals/strategies/router.py` | Dispatch `orb_rvol` |
| `signals/models.py` | Register in `SIGNAL_STRATEGIES` |
| `signals/run.py` | No-setup indicator branch |
| `signals/composer.py` | No-setup reason, indicator formatting, strategy line |
| `signals/rag/playbook.py` | Confirm-gate + reject-cues chunks |
| `signals/backtest.py` | Timeframe registration + extended-history paging |
| `web/src/lib/supabase/admin.ts` | Admin dropdown entry |

---

## Task 1: Session anchor arithmetic

**Files:**
- Create: `signals/strategies/orb_rvol/windows.py`
- Create: `signals/strategies/orb_rvol/__init__.py`
- Test: `tests/strategies/test_orb_rvol_windows.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_orb_rvol_windows.py`:

```python
"""Unit tests for orb_rvol session-window and relative-volume helpers."""
from datetime import datetime, timezone

from signals.models import Candle
from signals.strategies.orb_rvol.windows import active_anchor

BAR_MS = 15 * 60_000
DAY_MS = 86_400_000


def _ts(day, hour, minute=0):
    """Epoch ms for 2026-03-<day> <hour>:<minute> UTC."""
    dt = datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def test_active_anchor_inside_ny_window():
    # NY anchors at 13:30; OR is 13:30-14:00, so the window opens at 14:00.
    found = active_anchor(_ts(7, 14, 0))
    assert found == (_ts(7, 13, 30), "NY")


def test_active_anchor_inside_london_window():
    found = active_anchor(_ts(7, 8, 0))
    assert found == (_ts(7, 7, 0), "London")


def test_active_anchor_inside_asia_window():
    found = active_anchor(_ts(7, 1, 0))
    assert found == (_ts(7, 0, 0), "Asia")


def test_active_anchor_during_opening_range_is_none():
    # 13:45 is still inside the opening range, not yet tradeable.
    assert active_anchor(_ts(7, 13, 45)) is None


def test_active_anchor_after_window_closes_is_none():
    # NY window runs 14:00 -> 18:00 exclusive.
    assert active_anchor(_ts(7, 18, 0)) is None
    assert active_anchor(_ts(7, 17, 45)) == (_ts(7, 13, 30), "NY")


def test_active_anchor_in_dead_zone_is_none():
    # 12:00 is after London's window (ends 11:30) and before NY's (starts 14:00).
    assert active_anchor(_ts(7, 12, 0)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.orb_rvol'`

- [ ] **Step 3: Write minimal implementation**

Create `signals/strategies/orb_rvol/__init__.py` containing **only** this
docstring — it stays import-free until Task 4, because re-exporting
`detect_setup` before `detector.py` exists would break the package import and
take this task's tests down with it:

```python
"""Session opening range breakout gated on relative volume."""
```

Create `signals/strategies/orb_rvol/windows.py`:

```python
"""Session opening-range windows and relative volume for the orb_rvol strategy.

All times are UTC. `Candle.open_time` is epoch **milliseconds** throughout.

The three anchors are the major session opens. Each one's opening range is the
first `OR_BARS` closed 15m candles; breakouts may only trigger in the
`TRADE_WINDOW_BARS` that follow. The windows are deliberately sized so they
never overlap:

    anchor  OR closes  window ends  next anchor
    00:00   00:30      04:30        07:00
    07:00   07:30      11:30        13:30
    13:30   14:00      18:00        00:00
"""
from datetime import datetime, timedelta, timezone

# (hour, minute, label) in UTC. All land on 15m boundaries.
SESSION_ANCHORS_UTC = ((0, 0, "Asia"), (7, 0, "London"), (13, 30, "NY"))

BAR_MS = 15 * 60_000
DAY_MS = 86_400_000
# 15m bars forming the opening range (30 minutes).
OR_BARS = 2
# Bars after the OR closes in which a breakout may trigger (4 hours).
TRADE_WINDOW_BARS = 16


def _anchor_start(ts_ms, hour, minute):
    """Most recent UTC occurrence of hour:minute at or before `ts_ms`."""
    moment = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    anchor = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if anchor > moment:
        anchor -= timedelta(days=1)
    return int(anchor.timestamp() * 1000)


def active_anchor(ts_ms):
    """(anchor_ms, session_label) whose trade window contains `ts_ms`, else None.

    The opening range itself is NOT part of the trade window — a bar inside the
    OR returns None, since the range is not yet complete.
    """
    for hour, minute, label in SESSION_ANCHORS_UTC:
        start = _anchor_start(ts_ms, hour, minute)
        window_start = start + OR_BARS * BAR_MS
        window_end = window_start + TRADE_WINDOW_BARS * BAR_MS
        if window_start <= ts_ms < window_end:
            return start, label
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/orb_rvol/ tests/strategies/test_orb_rvol_windows.py
git commit -m "feat(orb_rvol): session anchor window arithmetic"
```

---

## Task 2: Opening-range and trade-window slicing

**Files:**
- Modify: `signals/strategies/orb_rvol/windows.py`
- Test: `tests/strategies/test_orb_rvol_windows.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_orb_rvol_windows.py`:

```python
from signals.strategies.orb_rvol.windows import or_bars, window_bars


def _flat_day(day, volume=1.0):
    """96 flat 15m candles covering one full UTC day."""
    start = _ts(day, 0)
    return [
        Candle(open_time=start + i * BAR_MS, open=100.0, high=100.2,
               low=99.8, close=100.0, volume=volume)
        for i in range(96)
    ]


def test_or_bars_returns_exactly_two_bars_from_the_anchor():
    candles = _flat_day(7)
    bars = or_bars(candles, _ts(7, 13, 30))
    assert len(bars) == 2
    assert [b.open_time for b in bars] == [_ts(7, 13, 30), _ts(7, 13, 45)]


def test_or_bars_returns_none_when_range_incomplete():
    candles = [c for c in _flat_day(7) if c.open_time <= _ts(7, 13, 30)]
    assert or_bars(candles, _ts(7, 13, 30)) is None


def test_or_bars_returns_none_when_anchor_absent():
    assert or_bars(_flat_day(7), _ts(3, 13, 30)) is None


def test_window_bars_spans_the_trade_window_only():
    candles = _flat_day(7)
    bars = window_bars(candles, _ts(7, 13, 30))
    assert bars[0].open_time == _ts(7, 14, 0)
    assert bars[-1].open_time == _ts(7, 17, 45)
    assert len(bars) == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: FAIL — `ImportError: cannot import name 'or_bars'`

- [ ] **Step 3: Write minimal implementation**

Append to `signals/strategies/orb_rvol/windows.py`:

```python
def or_bars(candles, anchor_ms):
    """The `OR_BARS` candles forming the opening range, or None if incomplete."""
    end = anchor_ms + OR_BARS * BAR_MS
    bars = [c for c in candles if anchor_ms <= c.open_time < end]
    return bars if len(bars) == OR_BARS else None


def window_bars(candles, anchor_ms):
    """Candles inside the anchor's trade window (after the OR, before expiry)."""
    start = anchor_ms + OR_BARS * BAR_MS
    end = start + TRADE_WINDOW_BARS * BAR_MS
    return [c for c in candles if start <= c.open_time < end]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: PASS — 10 passed

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/orb_rvol/windows.py tests/strategies/test_orb_rvol_windows.py
git commit -m "feat(orb_rvol): opening-range and trade-window slicing"
```

---

## Task 3: Relative volume

This is the load-bearing gate. The baseline averages **the same anchor's** prior
opens, never a rolling window — 13:30 UTC volume is structurally many times
00:00 UTC volume, so a rolling mean would measure time-of-day seasonality
instead of the volume anomaly the strategy is looking for.

**Files:**
- Modify: `signals/strategies/orb_rvol/windows.py`
- Test: `tests/strategies/test_orb_rvol_windows.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_orb_rvol_windows.py`:

```python
from signals.strategies.orb_rvol.windows import relative_volume


def _multi_day(days, volume=1.0):
    """Flat candles across consecutive UTC days starting 2026-03-02."""
    out = []
    for offset in range(days):
        out.extend(_flat_day(2 + offset, volume=volume))
    return out


def _set_volume(candles, ts, volume):
    for i, bar in enumerate(candles):
        if bar.open_time == ts:
            candles[i] = Candle(bar.open_time, bar.open, bar.high, bar.low,
                                bar.close, volume)
            return
    raise AssertionError(f"no candle at {ts}")


def test_relative_volume_compares_against_same_anchor_priors():
    candles = _multi_day(6)          # days 2..7, every OR bar volume 1.0
    anchor = _ts(7, 13, 30)
    _set_volume(candles, anchor, 10.0)
    _set_volume(candles, anchor + BAR_MS, 10.0)
    # current OR = 20.0; priors (days 2-6) = 2.0 each -> mean 2.0
    assert relative_volume(candles, anchor) == 10.0


def test_relative_volume_ignores_other_sessions():
    """A volume spike at the London open must not move the NY baseline."""
    candles = _multi_day(6)
    for offset in range(5):
        _set_volume(candles, _ts(2 + offset, 7, 0), 500.0)
    anchor = _ts(7, 13, 30)
    assert relative_volume(candles, anchor) == 1.0


def test_relative_volume_none_with_too_few_priors():
    candles = _multi_day(3)          # days 2,3,4 -> only 2 priors for day 4
    assert relative_volume(candles, _ts(4, 13, 30)) is None


def test_relative_volume_excludes_zero_volume_priors():
    """The gold feed reports 0.0 when Yahoo omits a bar's volume."""
    candles = _multi_day(6)
    for offset in range(2):          # zero out days 2 and 3
        _set_volume(candles, _ts(2 + offset, 13, 30), 0.0)
        _set_volume(candles, _ts(2 + offset, 13, 45), 0.0)
    anchor = _ts(7, 13, 30)
    _set_volume(candles, anchor, 4.0)
    _set_volume(candles, anchor + BAR_MS, 4.0)
    # 3 usable priors (days 4,5,6) of 2.0 each -> mean 2.0; current 8.0
    assert relative_volume(candles, anchor) == 4.0


def test_relative_volume_none_when_current_volume_is_zero():
    candles = _multi_day(6)
    anchor = _ts(7, 13, 30)
    _set_volume(candles, anchor, 0.0)
    _set_volume(candles, anchor + BAR_MS, 0.0)
    assert relative_volume(candles, anchor) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: FAIL — `ImportError: cannot import name 'relative_volume'`

- [ ] **Step 3: Write minimal implementation**

Add the constants near the top of `signals/strategies/orb_rvol/windows.py`,
below `TRADE_WINDOW_BARS`:

```python
# Prior same-anchor opens averaged for the relative-volume baseline.
RVOL_LOOKBACK = 10
# Minimum usable priors before the baseline is trusted.
MIN_RVOL_SAMPLES = 3
```

Append to `signals/strategies/orb_rvol/windows.py`:

```python
def _or_volume(candles, anchor_ms):
    """Total volume across an anchor's opening range, or None if unavailable."""
    bars = or_bars(candles, anchor_ms)
    if bars is None:
        return None
    total = sum(b.volume for b in bars)
    return total if total > 0 else None


def relative_volume(candles, anchor_ms):
    """Opening-range volume over the mean of the previous same-anchor opens.

    Returns None when the current range is missing, has zero volume, or fewer
    than MIN_RVOL_SAMPLES usable priors exist. Zero-volume priors are dropped
    rather than averaged in — the gold feed reports 0.0 for bars where the
    upstream provider omits volume, and counting those would deflate the
    baseline and manufacture false spikes.
    """
    current = _or_volume(candles, anchor_ms)
    if current is None:
        return None
    priors = []
    for back in range(1, RVOL_LOOKBACK + 1):
        prior = _or_volume(candles, anchor_ms - back * DAY_MS)
        if prior is not None:
            priors.append(prior)
    if len(priors) < MIN_RVOL_SAMPLES:
        return None
    return current / (sum(priors) / len(priors))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`

Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/orb_rvol/windows.py tests/strategies/test_orb_rvol_windows.py
git commit -m "feat(orb_rvol): relative volume against same-anchor history"
```

---

## Task 4: Detector — long breakout

**Files:**
- Create: `signals/strategies/orb_rvol/detector.py`
- Modify: `signals/strategies/orb_rvol/__init__.py`
- Test: `tests/strategies/test_orb_rvol_detector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_orb_rvol_detector.py`:

```python
"""Unit tests for the session ORB + relative volume detector (orb_rvol)."""
from datetime import datetime, timezone

from signals.models import Candle
from signals.strategies.orb_rvol.detector import detect_setup

BAR_MS = 15 * 60_000
ATR = 2.0


def _ts(day, hour, minute=0):
    """Epoch ms for 2026-03-<day> <hour>:<minute> UTC."""
    dt = datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _base_series(days=6):
    """Flat 15m candles across days 2..(1+days), volume 1.0.

    Six days is 576 bars, comfortably over the detector's MIN_CANDLES floor,
    and leaves five prior same-anchor opens for the relative-volume baseline.
    """
    start = _ts(2, 0)
    return [
        Candle(open_time=start + i * BAR_MS, open=100.0, high=100.2,
               low=99.8, close=100.0, volume=1.0)
        for i in range(days * 96)
    ]


def _set(candles, ts, o, h, l, c, v):
    for i, bar in enumerate(candles):
        if bar.open_time == ts:
            candles[i] = Candle(ts, o, h, l, c, v)
            return
    raise AssertionError(f"no candle at {ts}")


def _truncate(candles, ts):
    """Drop everything after `ts` so it becomes the latest closed bar."""
    return [c for c in candles if c.open_time <= ts]


def _long_setup_series():
    """Bullish NY opening range on 10x volume, then a breakout close above it.

    OR high 101.2 / low 99.8; breakout bar closes 102.0.
    """
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 10.0)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 101.0, 10.0)
    _set(candles, _ts(7, 14, 0), 101.0, 102.5, 100.9, 102.0, 5.0)
    return _truncate(candles, _ts(7, 14, 0))


def _atr(candles, value=ATR):
    return [value] * len(candles)


def test_long_breakout_on_bullish_range_with_high_relative_volume():
    candles = _long_setup_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 102.0
    # stop = or_low 99.8 - 0.25 * ATR 2.0
    assert setup.stop_loss == 99.3


def test_long_targets_use_the_wide_2r_4r_6r_ladder():
    candles = _long_setup_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    risk = setup.entry - setup.stop_loss          # 2.7
    assert setup.take_profit_1 == setup.entry + 2 * risk
    assert setup.take_profit_2 == setup.entry + 4 * risk
    assert setup.take_profit_3 == setup.entry + 6 * risk


def test_long_indicators_describe_the_setup():
    candles = _long_setup_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup.indicators["strategy"] == "orb_rvol"
    assert setup.indicators["session"] == "NY"
    assert setup.indicators["or_direction"] == "bullish"
    assert setup.indicators["or_high"] == 101.2
    assert setup.indicators["or_low"] == 99.8
    assert setup.indicators["rvol"] == 10.0
    assert setup.indicators["anchor_time"] == _ts(7, 13, 30)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`

Expected: FAIL — `ImportError: cannot import name 'detect_setup'`

- [ ] **Step 3: Write minimal implementation**

Create `signals/strategies/orb_rvol/detector.py`:

```python
"""Session Opening Range Breakout, gated on relative volume.

At each major session open (00:00 / 07:00 / 13:30 UTC) the first 30 minutes
form an opening range. The first bar to close beyond that range, in the
direction the range itself moved, is the entry — but only when the range traded
on abnormally high volume versus the same session's own recent history.

Adapted from Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For
The U.S. Equity Market" (SSRN 4729284). Their base ORB underperformed
buy-and-hold (Sharpe 0.48); adding the relative-volume filter lifted it to 2.81.
The volume gate, not the breakout, is where the edge lives.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.orb_rvol.windows import (
    active_anchor,
    or_bars,
    relative_volume,
    window_bars,
)

# ~4.2 days of 15m bars — enough that MIN_RVOL_SAMPLES prior opens exist for
# every anchor. Three days would only just reach the floor.
MIN_CANDLES = 400
# The paper's own threshold: below 100% average PnL was -0.02R, above it +0.08R.
MIN_RVOL = 1.0
# Stop distance beyond the opposite edge of the opening range.
ATR_STOP_BUFFER = 0.25
# Reject setups whose stop is farther than this many ATRs from entry.
MAX_STOP_ATR = 2.5
# Wide ladder: ORB pays through a few large trend moves, so tight targets cut
# off the exact trades the edge depends on.
ORB_TP1_R = 2.0
ORB_TP2_R = 4.0
ORB_TP3_R = 6.0


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a volume-backed session ORB, else None.

    `adx14` and `htf_trend` are accepted for router uniformity and recorded in
    `indicators`, but deliberately do NOT veto: the opening range is itself the
    directional thesis, and the source paper applies no higher-timeframe filter.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    bar = candles[-1]
    found = active_anchor(bar.open_time)
    if found is None:
        return None
    anchor_ms, session = found

    opening = or_bars(candles, anchor_ms)
    if opening is None:
        return None
    or_high = max(c.high for c in opening)
    or_low = min(c.low for c in opening)
    drift = opening[-1].close - opening[0].open
    if drift == 0:  # doji opening range — no directional thesis
        return None

    rvol = relative_volume(candles, anchor_ms)
    if rvol is None or rvol < MIN_RVOL:
        return None

    # Only the FIRST breakout of a session trades. The detector is stateless,
    # so "first" is re-derived: no earlier bar in the window may have closed
    # beyond the same edge.
    earlier = window_bars(candles, anchor_ms)[:-1]
    entry = bar.close
    if drift > 0:
        if entry <= or_high or any(c.close > or_high for c in earlier):
            return None
        direction = "long"
        stop = or_low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            return None
    else:
        if entry >= or_low or any(c.close < or_low for c in earlier):
            return None
        direction = "short"
        stop = or_high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            return None

    if abs(entry - stop) / atr_value > MAX_STOP_ATR:
        return None

    tp1, tp2, tp3 = take_profits_from_risk(
        entry, stop, direction, r1=ORB_TP1_R, r2=ORB_TP2_R, r3=ORB_TP3_R,
    )
    indicators = {
        "strategy": "orb_rvol",
        "session": session,
        "or_high": or_high,
        "or_low": or_low,
        "or_direction": "bullish" if drift > 0 else "bearish",
        "rvol": rvol,
        "atr": atr_value,
        "anchor_time": anchor_ms,
    }
    if adx14 is not None and adx14[-1] is not None:
        indicators["adx"] = adx14[-1]
    if htf_trend is not None:
        indicators["htf_trend"] = htf_trend
    return CandidateSetup(
        symbol, direction, entry, stop, tp1, indicators,
        take_profit_2=tp2, take_profit_3=tp3,
    )
```

Now that `detector.py` exists, replace `signals/strategies/orb_rvol/__init__.py`
with the re-export (matching `ict_fvg/__init__.py`):

```python
from signals.strategies.orb_rvol.detector import detect_setup

__all__ = ["detect_setup"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`

Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/orb_rvol/ tests/strategies/test_orb_rvol_detector.py
git commit -m "feat(orb_rvol): long breakout detection"
```

---

## Task 5: Detector — short breakout, direction lock, doji

**Files:**
- Test: `tests/strategies/test_orb_rvol_detector.py`

No implementation changes expected — Task 4's detector already handles these.
These tests prove the direction rules, which are the part of the paper most
often implemented wrongly (traders commonly take a breakout either way; the
paper explicitly forbids it).

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_orb_rvol_detector.py`:

```python
def _short_setup_series():
    """Bearish NY opening range on 10x volume, then a breakdown close below it.

    OR high 100.2 / low 98.8; breakdown bar closes 98.2.
    """
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.2, 99.5, 99.6, 10.0)
    _set(candles, anchor + BAR_MS, 99.6, 99.8, 98.8, 99.0, 10.0)
    _set(candles, _ts(7, 14, 0), 99.0, 99.1, 98.0, 98.2, 5.0)
    return _truncate(candles, _ts(7, 14, 0))


def test_short_breakdown_on_bearish_range():
    candles = _short_setup_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 98.2
    # stop = or_high 100.2 + 0.25 * ATR 2.0
    assert setup.stop_loss == 100.7
    assert setup.indicators["or_direction"] == "bearish"


def test_short_targets_use_the_wide_ladder():
    candles = _short_setup_series()
    setup = detect_setup("BTCUSD", candles, _atr(candles))
    risk = setup.stop_loss - setup.entry          # 2.5
    assert setup.take_profit_1 == setup.entry - 2 * risk
    assert setup.take_profit_3 == setup.entry - 6 * risk


def test_bullish_range_does_not_take_a_downside_break():
    """Direction lock: a bullish opening range permits longs only."""
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 10.0)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 101.0, 10.0)
    _set(candles, _ts(7, 14, 0), 100.5, 100.6, 98.5, 99.0, 5.0)
    candles = _truncate(candles, _ts(7, 14, 0))
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_bearish_range_does_not_take_an_upside_break():
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.2, 99.5, 99.6, 10.0)
    _set(candles, anchor + BAR_MS, 99.6, 99.8, 98.8, 99.0, 10.0)
    _set(candles, _ts(7, 14, 0), 99.5, 101.5, 99.4, 101.0, 5.0)
    candles = _truncate(candles, _ts(7, 14, 0))
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_doji_opening_range_is_skipped():
    """Range close == range open: no imbalance to trade."""
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 10.0)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 100.0, 10.0)
    _set(candles, _ts(7, 14, 0), 100.0, 102.5, 99.9, 102.0, 5.0)
    candles = _truncate(candles, _ts(7, 14, 0))
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`

Expected: all 5 new tests PASS immediately (Task 4 implemented these rules).
If any fail, fix `detector.py` — do not weaken the test.

- [ ] **Step 3: No implementation needed**

These paths are already covered by the `drift` sign checks in `detect_setup`.

- [ ] **Step 4: Run the full detector suite**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`

Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_orb_rvol_detector.py
git commit -m "test(orb_rvol): short breakdown and direction-lock coverage"
```

---

## Task 6: Detector — rejection gates

**Files:**
- Test: `tests/strategies/test_orb_rvol_detector.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_orb_rvol_detector.py`:

```python
def test_low_relative_volume_is_rejected():
    """The headline gate: an ordinary-volume open is not tradeable."""
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 0.5)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 101.0, 0.5)
    _set(candles, _ts(7, 14, 0), 101.0, 102.5, 100.9, 102.0, 5.0)
    candles = _truncate(candles, _ts(7, 14, 0))
    # current OR = 1.0 vs prior mean 2.0 -> RVOL 0.5, below MIN_RVOL
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_only_the_first_breakout_of_a_session_trades():
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 10.0)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 101.0, 10.0)
    _set(candles, _ts(7, 14, 0), 101.0, 102.5, 100.9, 102.0, 5.0)
    _set(candles, _ts(7, 14, 15), 102.0, 103.0, 101.5, 102.5, 5.0)
    candles = _truncate(candles, _ts(7, 14, 15))
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_breakout_after_the_trade_window_is_rejected():
    """NY window ends at 18:00; a break at 18:00 is too late."""
    candles = _base_series()
    anchor = _ts(7, 13, 30)
    _set(candles, anchor, 100.0, 100.5, 99.8, 100.4, 10.0)
    _set(candles, anchor + BAR_MS, 100.4, 101.2, 100.2, 101.0, 10.0)
    _set(candles, _ts(7, 18, 0), 101.0, 102.5, 100.9, 102.0, 5.0)
    candles = _truncate(candles, _ts(7, 18, 0))
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_stop_wider_than_max_atr_is_rejected():
    """A tiny ATR makes the OR-width stop an implausible multiple of risk."""
    candles = _long_setup_series()
    # risk 2.325 against ATR 0.5 -> 4.65 ATRs, over MAX_STOP_ATR
    assert detect_setup("BTCUSD", candles, _atr(candles, 0.5)) is None


def test_insufficient_history_is_rejected():
    candles = _long_setup_series()[-200:]
    assert detect_setup("BTCUSD", candles, _atr(candles)) is None


def test_missing_atr_is_rejected():
    candles = _long_setup_series()
    atr = _atr(candles)
    atr[-1] = None
    assert detect_setup("BTCUSD", candles, atr) is None


def test_adx_and_htf_trend_are_recorded_but_never_veto():
    """The opening range is the directional thesis; HTF does not override it."""
    candles = _long_setup_series()
    adx = [10.0] * len(candles)
    setup = detect_setup("BTCUSD", candles, _atr(candles),
                         adx14=adx, htf_trend="down")
    assert setup is not None
    assert setup.direction == "long"
    assert setup.indicators["htf_trend"] == "down"
    assert setup.indicators["adx"] == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`

Expected: all 7 new tests PASS (Task 4 implemented these gates). Investigate
and fix `detector.py` if any fail.

- [ ] **Step 3: No implementation needed**

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/strategies/ -v`

Expected: PASS — 15 passed in the detector file, 15 in the windows file, plus
the pre-existing strategy tests, all green.

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_orb_rvol_detector.py
git commit -m "test(orb_rvol): rejection gate coverage"
```

---

## Task 7: Register the strategy (models + router)

**Files:**
- Modify: `signals/models.py:104`
- Modify: `signals/strategies/router.py`
- Test: `tests/strategies/test_orb_rvol_detector.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_orb_rvol_detector.py`:

```python
def test_router_dispatches_orb_rvol():
    from signals.models import SIGNAL_STRATEGIES
    from signals.strategies import detect_setup as route

    assert "orb_rvol" in SIGNAL_STRATEGIES
    candles = _long_setup_series()
    atr = _atr(candles)
    empty = [None] * len(candles)
    setup = route("orb_rvol", "BTCUSD", candles, empty, empty, empty, empty,
                  atr)
    assert setup is not None
    assert setup.indicators["strategy"] == "orb_rvol"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py::test_router_dispatches_orb_rvol -v`

Expected: FAIL — `assert 'orb_rvol' in ('ema_cross', 'ict_smc', 'ce_lwma', 'ict_fvg', 'sr_zone')`

- [ ] **Step 3: Write minimal implementation**

In `signals/models.py`, replace line 104:

```python
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "orb_rvol")
```

In `signals/strategies/router.py`, add the import alongside the others:

```python
from signals.strategies.orb_rvol import detect_setup as detect_orb_setup
```

and add this branch immediately before the `if strategy == "sr_zone":` branch:

```python
    if strategy == "orb_rvol":
        return detect_orb_setup(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/ -v`

Expected: PASS — all strategy tests green

- [ ] **Step 5: Commit**

```bash
git add signals/models.py signals/strategies/router.py tests/strategies/test_orb_rvol_detector.py
git commit -m "feat(orb_rvol): register strategy and router dispatch"
```

---

## Task 8: Engine plumbing (run, composer, playbook)

These are the three files the `sr_zone` spec identified as easy to forget. All
are user-visible: they drive the AI prompt, the no-setup explanations, and the
`/admin` AI event feed.

**Files:**
- Modify: `signals/run.py:291`
- Modify: `signals/composer.py` (three locations)
- Modify: `signals/rag/playbook.py`

- [ ] **Step 1: Add the no-setup indicator branch**

In `signals/run.py`, change line 291 from:

```python
    if strategy in ("ict_smc", "ict_fvg", "sr_zone"):
```

to:

```python
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "orb_rvol"):
```

- [ ] **Step 2: Add the no-setup reason**

In `signals/composer.py`, insert immediately after the `sr_zone` block that
ends with `on the {chart})."\n        )`:

```python
    if strategy == "orb_rvol":
        return (
            f"The rules engine found no valid session ORB setup (no session "
            f"open with above-average relative volume, or no breakout of the "
            f"opening range in its own direction on the {chart})."
        )
```

- [ ] **Step 3: Add indicator formatting**

In `signals/composer.py`, insert after the `sr_zone` formatting block (the one
returning `"no S/R reading"`):

```python
    if active == "orb_rvol":
        parts = []
        for key, label in (
            ("session", "session"),
            ("or_direction", "OR dir"),
            ("or_high", "OR high"),
            ("or_low", "OR low"),
            ("rvol", "RVOL"),
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
        return ", ".join(parts) if parts else "no ORB reading"
```

- [ ] **Step 4: Add the strategy line**

In `signals/composer.py`, insert a branch before the final `else:` in the
`strategy_line` chain:

```python
    elif active == "orb_rvol":
        strategy_line = (
            "- Strategy: Session opening-range breakout on high relative "
            "volume (wide 2R/4R/6R targets)\n"
        )
```

- [ ] **Step 5: Add the playbook chunks**

In `signals/rag/playbook.py`, append these two entries to the chunk list,
following the existing dict shape:

```python
    {
        "strategy": "orb_rvol",
        "title": "Session ORB confirm gate",
        "body": (
            "Session orb_rvol: at the 00:00/07:00/13:30 UTC opens the first 30 "
            "minutes form an opening range. Trade the first close beyond that "
            "range ONLY in the direction the range itself moved, and only when "
            "opening-range relative volume is at least 100% of that same "
            "session's recent average. Stop sits beyond the opposite edge of "
            "the range; targets are a wide 2R/4R/6R because the edge comes "
            "from a few large trend moves. Confirm when the volume anomaly is "
            "clear and the breakout closed decisively outside the range."
        ),
    },
    {
        "strategy": "orb_rvol",
        "title": "Session ORB reject cues",
        "body": (
            "Reject orb_rvol when relative volume is merely average (the edge "
            "disappears entirely without the volume anomaly), when the "
            "breakout fights the opening range's own direction, on a doji "
            "opening range, when the range is so wide that the stop is an "
            "extreme multiple of ATR, when the session's first breakout "
            "already triggered, or when high-impact news is imminent."
        ),
    },
```

- [ ] **Step 6: Verify nothing regressed**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: PASS — the full suite green, no failures

- [ ] **Step 7: Commit**

```bash
git add signals/run.py signals/composer.py signals/rag/playbook.py
git commit -m "feat(orb_rvol): engine plumbing for prompts and no-setup reasons"
```

---

## Task 9: Backtest registration and extended history

`DEFAULT_CANDLE_LIMIT = 720` on 15m is only 7.5 days — roughly 22 session opens
per symbol, minus those consumed warming up the relative-volume baseline. Too
thin to judge the strategy on. `fetch_candles` accepts `start_time` (epoch ms)
and filters forward from it, so history is gathered by paging.

**Files:**
- Modify: `signals/backtest.py`
- Test: `tests/core/test_backtest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_backtest.py`:

```python
def test_fetch_history_pages_forward_until_exhausted():
    from signals.models import Candle
    from signals.backtest import fetch_history

    step = 15 * 60_000
    base = 1_700_000_000_000
    calls = []

    def fake_fetch(symbol, interval, limit, start_time=None, session=None):
        calls.append(start_time)
        if len(calls) > 3:
            return []
        first = start_time // step
        return [
            Candle(open_time=(first + i) * step, open=1.0, high=1.0,
                   low=1.0, close=1.0, volume=1.0)
            for i in range(5)
        ]

    out = fetch_history("BTCUSD", "15m", 12, fetcher=fake_fetch, now_ms=base)
    times = [c.open_time for c in out]
    assert times == sorted(times)
    assert len(set(times)) == len(times)      # no duplicates
    assert len(out) <= 12
    assert len(calls) >= 2                     # actually paged


def test_fetch_history_stops_when_a_batch_returns_nothing():
    from signals.backtest import fetch_history

    def empty_fetch(symbol, interval, limit, start_time=None, session=None):
        return []

    out = fetch_history("BTCUSD", "15m", 100, fetcher=empty_fetch,
                        now_ms=1_700_000_000_000)
    assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_backtest.py -k fetch_history -v`

Expected: FAIL — `ImportError: cannot import name 'fetch_history'`

- [ ] **Step 3: Write minimal implementation**

Add `import time` at the top of `signals/backtest.py`, then append these
constants beside the existing ones:

```python
# Bars of history to gather for strategies that need a long sample. orb_rvol
# only fires at three session opens a day, and burns several days warming up
# its relative-volume baseline, so 720 bars would leave too few trades to
# judge it on.
HISTORY_BARS = {"orb_rvol": 3000}
# Providers cap a single response (Kraken returns at most ~720 OHLC bars per
# `since`), so long histories are gathered by paging forward.
PAGE_LIMIT = 720
MAX_PAGES = 12
```

and this function:

```python
def fetch_history(symbol, timeframe, total, *, session=None, fetcher=None,
                  now_ms=None):
    """Up to `total` recent candles, paging forward past the provider's cap.

    `fetch_candles` filters forward from `start_time`, so each page resumes one
    bar past the previous page's last candle. Stops when a page returns nothing
    new, so a provider that keeps replaying its tail cannot loop forever.
    Returns fewer than `total` bars when the provider's history is shorter —
    intraday history is capped upstream (gold comes from Yahoo).
    """
    from signals.market_client import fetch_candles

    fetcher = fetcher or fetch_candles
    step_ms = TF_MINUTES[timeframe] * 60_000
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    start = now_ms - total * step_ms

    by_time = {}
    for _ in range(MAX_PAGES):
        batch = fetcher(symbol, timeframe, PAGE_LIMIT, start_time=start,
                        session=session)
        fresh = [c for c in batch if c.open_time not in by_time]
        if not fresh:
            break
        for candle in fresh:
            by_time[candle.open_time] = candle
        start = max(c.open_time for c in fresh) + step_ms
        if len(by_time) >= total:
            break

    ordered = [by_time[t] for t in sorted(by_time)]
    return ordered[-total:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_backtest.py -k fetch_history -v`

Expected: PASS — 2 passed

- [ ] **Step 5: Register the strategy in the backtest**

In `signals/backtest.py`, add to `STRATEGY_TIMEFRAMES`:

```python
STRATEGY_TIMEFRAMES = {
    "ict_fvg": "5m",
    "ema_cross": "1h",
    "ict_smc": "1h",
    "sr_zone": "1h",
    "orb_rvol": "15m",
}
```

Leave `CONFLUENCE_TIMEFRAMES` alone — `orb_rvol` has no HTF gate, so
`.get("orb_rvol")` returning None correctly means no confluence is applied.

In `main()`, replace the primary-candle fetch:

```python
                candles = fetch_candles(
                    symbol, timeframe, DEFAULT_CANDLE_LIMIT, session=session,
                )[:-1]  # drop the still-forming last bar
```

with:

```python
                bars = HISTORY_BARS.get(strategy, DEFAULT_CANDLE_LIMIT)
                if bars > DEFAULT_CANDLE_LIMIT:
                    candles = fetch_history(
                        symbol, timeframe, bars, session=session,
                    )[:-1]
                else:
                    candles = fetch_candles(
                        symbol, timeframe, bars, session=session,
                    )[:-1]  # drop the still-forming last bar
```

- [ ] **Step 6: Verify the suite still passes**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: PASS — full suite green

- [ ] **Step 7: Commit**

```bash
git add signals/backtest.py tests/core/test_backtest.py
git commit -m "feat(orb_rvol): backtest registration with paged history"
```

---

## Task 10: Admin dropdown

**Files:**
- Modify: `web/src/lib/supabase/admin.ts:25-43`

- [ ] **Step 1: Add the entry**

In `web/src/lib/supabase/admin.ts`, append to the `SIGNAL_STRATEGIES` array,
after the `sr_zone` entry and before the closing `] as const;`:

```typescript
  {
    id: "orb_rvol",
    label: "Session ORB (relative volume)",
    description:
      "Breakout of the 00:00 / 07:00 / 13:30 UTC opening range, in the range's own direction, only on above-average volume. Wide 2R/4R/6R targets.",
  },
```

- [ ] **Step 2: Verify the web build type-checks**

Run: `cd web && npm run build`

Expected: build succeeds. If the project has a faster type-check script
(check `web/package.json` scripts for `typecheck` or `lint`), prefer that.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/supabase/admin.ts
git commit -m "feat(orb_rvol): expose strategy in the admin dropdown"
```

---

## Task 11: Run the backtest and report

The whole point of the chosen rollout: `orb_rvol` earns a live session slot only
if the numbers justify it.

- [ ] **Step 1: Run the backtester**

Run: `.venv/bin/python -m signals.backtest`

This hits live market data, so it takes a minute and the exact numbers will
differ run to run.

- [ ] **Step 2: Record the results**

Capture the `orb_rvol` rows alongside the existing strategies' rows. Report:
trade count per symbol, TP1 rate, TP3 rate, expectancy in R, total R.

- [ ] **Step 3: Interpret honestly**

State plainly in the summary:
- The trade count. If `orb_rvol` produced fewer than ~15 trades per symbol,
  say so and state that the expectancy figure is not statistically meaningful
  at that sample size — do not present it as evidence either way.
- Whether expectancy beat the incumbent strategies on the same symbols.
- That these are rules-only results; the live engine also runs an LLM
  confirmation gate that the backtester deliberately skips.

Do **not** recommend promoting `orb_rvol` into `TRADING_SESSIONS` on a thin or
negative sample. Reverting to "keep it admin-only" is a valid outcome and
should be stated as such.

- [ ] **Step 4: Commit nothing**

This task produces a report, not a code change. `TRADING_SESSIONS` stays
untouched regardless of the numbers — promoting the strategy is a separate,
explicit decision for the user.

---

## Verification checklist

- [ ] `.venv/bin/python -m pytest tests/ -q` — full suite passes
- [ ] `grep -rn "orb_rvol" signals/ | wc -l` — appears in models, router, run,
      composer, playbook, backtest, and its own package
- [ ] `TRADING_SESSIONS` in `signals/models.py` is unchanged (diff it against
      `main`) — no live signal behaviour was altered
- [ ] `cd web && npm run build` succeeds
- [ ] The backtest report from Task 11 has been shown to the user
