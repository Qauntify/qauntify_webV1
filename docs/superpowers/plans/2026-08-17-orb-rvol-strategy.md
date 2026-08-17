# Session Opening Range Breakout on Relative Volume (`orb_rvol`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `orb_rvol` — a session opening-range breakout strategy gated on relative volume — to the pluggable strategy system, fully wired and tested but **not** assigned to a live trading session, then produce an honest long-history backtest verdict before anyone decides whether to promote it.

**Architecture:** A new `signals/strategies/orb_rvol/` package with two modules — `windows.py` (session-anchor detection, opening-range slicing, relative-volume arithmetic — the fiddly, independently-testable part) and `detector.py` (the entry/stop/target rules built on top, matching every other detector's `detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None) -> CandidateSetup | None` contract). Then the same mechanical integration every strategy in this repo gets: router dispatch, the two Python strategy-name registries (`SIGNAL_STRATEGIES` and `ADMIN_SELECTABLE_STRATEGIES`), a Postgres CHECK constraint, the admin dropdown, no-setup/RAG/LLM-prompt copy, and a backtest registration. Finally a long-history report script against verified Binance archives, mirroring `scripts/bbma_history_report.py`.

**Tech Stack:** Python 3.12, pytest, existing `signals/` package conventions (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md` (refreshed 2026-08-17 — read it first; this plan implements it exactly, including the 2026-08-17 amendments).

---

## Task 1: `windows.py` — session anchors, opening-range slicing, relative volume

**Files:**
- Create: `signals/strategies/orb_rvol/__init__.py` (empty package marker for now — Task 2 fills it in)
- Create: `signals/strategies/orb_rvol/windows.py`
- Test: `tests/strategies/test_orb_rvol_windows.py`

- [ ] **Step 1: Create the package directory with an empty `__init__.py`**

```bash
mkdir -p signals/strategies/orb_rvol
touch signals/strategies/orb_rvol/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/strategies/test_orb_rvol_windows.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail with an import error**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.orb_rvol.windows'`

- [ ] **Step 4: Write `windows.py`**

Create `signals/strategies/orb_rvol/windows.py`:

```python
"""Session opening-range anchors, range slicing, and relative volume.

Split from detector.py because this arithmetic — locating an anchor's trade
window, slicing its opening range, and averaging same-anchor volume history —
is the fiddly part and is worth testing independently of the entry/stop/TP
rules built on top of it. See
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.

Anchors are matched against each bar's own open_time (UTC wall clock), not
counted forward from the start of `candles` — so behaviour does not shift if
the caller passes a differently-sized window (the live engine's rolling
candle_limit slice vs. a full backtest history).
"""

# (hour, minute, name), UTC. All three land on 15m boundaries.
SESSION_ANCHORS_UTC = ((0, 0, "Asia"), (7, 0, "London"), (13, 30, "NY"))

OR_BARS = 2  # 15m bars forming the opening range (30 minutes)
TRADE_WINDOW_BARS = 16  # bars after the OR closes in which a breakout may trigger
RVOL_LOOKBACK = 10  # prior same-anchor opens averaged
MIN_RVOL_SAMPLES = 3  # minimum priors before RVOL is trusted

_BAR_MS = 15 * 60_000
_DAY_MS = 24 * 60 * 60_000
_ANCHOR_MS = tuple((name, (h * 60 + m) * 60_000) for h, m, name in SESSION_ANCHORS_UTC)
_WINDOW_END_MS = (OR_BARS + TRADE_WINDOW_BARS) * _BAR_MS


def _anchor_indices(candles):
    """[(index, anchor_name), ...] for every bar whose open_time lands
    exactly on a session anchor, oldest first."""
    hits = []
    for i, c in enumerate(candles):
        ms_of_day = c.open_time % _DAY_MS
        for name, anchor_ms in _ANCHOR_MS:
            if ms_of_day == anchor_ms:
                hits.append((i, name))
                break
    return hits


def current_anchor(candles):
    """(anchor_name, anchor_index) whose trade window contains the LAST bar
    in `candles`, or (None, None) if it falls in no anchor's window.

    `anchor_index` is where the anchor's own bar sits in `candles` — the
    opening range is `candles[anchor_index : anchor_index + OR_BARS]`.
    """
    if not candles:
        return None, None
    last = candles[-1]
    idx, name = None, None
    for i, n in _anchor_indices(candles):
        if candles[i].open_time <= last.open_time:
            idx, name = i, n
    if idx is None:
        return None, None
    if last.open_time - candles[idx].open_time >= _WINDOW_END_MS:
        return None, None
    return name, idx


def opening_range(candles, anchor_index):
    """(or_high, or_low, or_direction) for the OR starting at `anchor_index`,
    or None if fewer than OR_BARS bars are available there.

    `or_direction` is "bullish" (the OR's last close is above its first
    open), "bearish" (below), or None for a doji (equal).
    """
    bars = candles[anchor_index:anchor_index + OR_BARS]
    if len(bars) < OR_BARS:
        return None
    or_high = max(b.high for b in bars)
    or_low = min(b.low for b in bars)
    if bars[-1].close > bars[0].open:
        direction = "bullish"
    elif bars[-1].close < bars[0].open:
        direction = "bearish"
    else:
        direction = None
    return or_high, or_low, direction


def opening_range_volume(candles, anchor_index):
    """Summed volume of the OR_BARS opening-range bars, or None if
    incomplete."""
    bars = candles[anchor_index:anchor_index + OR_BARS]
    if len(bars) < OR_BARS:
        return None
    return sum(b.volume for b in bars)


def relative_volume(candles, anchor_name, anchor_index):
    """current OR volume / mean OR volume of the previous RVOL_LOOKBACK
    same-`anchor_name` occurrences (zero-volume ones excluded), or None if
    fewer than MIN_RVOL_SAMPLES qualify, or the current OR volume is 0.

    Comparing against the SAME anchor's history (not a rolling average
    across all anchors) is a necessary adaptation, not a stylistic one:
    volume at 13:30 UTC is structurally many times volume at 00:00 UTC, so a
    rolling mean would flag every NY open as "abnormal" and every Asia open
    as "quiet" — measuring time-of-day seasonality, not the catalyst this
    strategy is trying to detect.
    """
    current = opening_range_volume(candles, anchor_index)
    if not current:  # None (incomplete) or 0.0
        return None
    priors = [
        v for i, name in _anchor_indices(candles[:anchor_index])
        if name == anchor_name
        for v in [opening_range_volume(candles, i)]
        if v
    ][-RVOL_LOOKBACK:]
    if len(priors) < MIN_RVOL_SAMPLES:
        return None
    return current / (sum(priors) / len(priors))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py -v`
Expected: PASS — 16 tests

- [ ] **Step 6: Commit**

```bash
git add signals/strategies/orb_rvol/__init__.py signals/strategies/orb_rvol/windows.py tests/strategies/test_orb_rvol_windows.py
git commit -m "feat(orb_rvol): add session-anchor, opening-range, and RVOL arithmetic"
```

---

## Task 2: `detector.py` — entry, stop, and target rules

**Files:**
- Modify: `signals/strategies/orb_rvol/__init__.py`
- Create: `signals/strategies/orb_rvol/detector.py`
- Test: `tests/strategies/test_orb_rvol_detector.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/strategies/test_orb_rvol_detector.py`:

```python
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
        candles.append(_bar(today + 15, open_=99.6, high=99.9, low=98.5,
                            close=99.0, volume=or_volume))  # close 99.0 < open 100.0
        or_high, or_low = 100.5, 98.5
        breakout_bar = _bar(today + 30, open_=99.0, high=99.1, low=97.5,
                            close=98.0, volume=or_volume)
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
    assert setup.entry == 98.0
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
```

- [ ] **Step 2: Run the tests to verify they fail with an import error**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.strategies.orb_rvol.detector'`

- [ ] **Step 3: Write `detector.py`**

Create `signals/strategies/orb_rvol/detector.py`:

```python
"""Session Opening Range Breakout on Relative Volume.

Trade the first breakout beyond a session's opening range, in the direction
the range itself moved, but only when that range traded on abnormally high
volume relative to the same session anchor's own recent history. See
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.

htf_trend/adx are recorded in indicators but never gate — the opening range
IS the directional thesis (see the spec's "Deliberate omissions").
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.orb_rvol.windows import (
    OR_BARS,
    TRADE_WINDOW_BARS,
    current_anchor,
    opening_range,
    relative_volume,
)

MIN_RVOL = 1.0  # paper's threshold — expectancy flips sign here
ATR_STOP_BUFFER = 0.25  # stop distance beyond the OR edge
MAX_STOP_ATR = 2.5  # reject wide stops (matches sr_zone)
MIN_CANDLES = 400  # ~4.2 days of 15m; enough for MIN_RVOL_SAMPLES at every anchor
TP1_R, TP2_R, TP3_R = 2.0, 4.0, 6.0  # wide ladder — the edge depends on runners


def _first_breakout_index(candles, anchor_index, direction, or_high, or_low):
    """Index of the FIRST bar in the trade window that closes beyond the OR
    edge in `direction`, or None if none has yet (or ever will, once the
    window has closed)."""
    start = anchor_index + OR_BARS
    end = min(len(candles), start + TRADE_WINDOW_BARS)
    for i in range(start, end):
        bar = candles[i]
        if direction == "long" and bar.close > or_high:
            return i
        if direction == "short" and bar.close < or_low:
            return i
    return None


def _indicators(session, or_high, or_low, or_direction, rvol, atr_value,
                anchor_time, adx14, htf_trend):
    out = {
        "strategy": "orb_rvol",
        "session": session,
        "or_high": or_high,
        "or_low": or_low,
        "or_direction": or_direction,
        "rvol": rvol,
        "atr": atr_value,
        "anchor_time": anchor_time,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a confirmed opening-range breakout, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    session, anchor_index = current_anchor(candles)
    if session is None:
        return None

    rng = opening_range(candles, anchor_index)
    if rng is None:
        return None
    or_high, or_low, or_direction = rng
    if or_direction is None:  # doji
        return None

    rvol = relative_volume(candles, session, anchor_index)
    if rvol is None or rvol < MIN_RVOL:
        return None

    direction = "long" if or_direction == "bullish" else "short"
    breakout_index = _first_breakout_index(
        candles, anchor_index, direction, or_high, or_low,
    )
    if breakout_index is None or breakout_index != len(candles) - 1:
        # No breakout yet, or the first one already happened on an earlier
        # bar — one trade per anchor, re-derived statelessly every call.
        return None

    bar = candles[breakout_index]
    entry = bar.close
    if direction == "long":
        stop = or_low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            return None
    else:
        stop = or_high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            return None
    if abs(entry - stop) / atr_value > MAX_STOP_ATR:
        return None

    tp1, tp2, tp3 = take_profits_from_risk(
        entry, stop, direction, r1=TP1_R, r2=TP2_R, r3=TP3_R,
    )
    return CandidateSetup(
        symbol, direction, entry, stop, tp1,
        _indicators(session, or_high, or_low, or_direction, rvol, atr_value,
                   candles[anchor_index].open_time, adx14, htf_trend),
        take_profit_2=tp2, take_profit_3=tp3,
    )
```

- [ ] **Step 4: Update the package `__init__.py`**

Replace `signals/strategies/orb_rvol/__init__.py` (mirrors `ict_fvg`):

```python
from signals.strategies.orb_rvol.detector import detect_setup

__all__ = ["detect_setup"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_detector.py -v`
Expected: PASS — 10 tests

- [ ] **Step 6: Run both orb_rvol test files together to make sure nothing regressed**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_windows.py tests/strategies/test_orb_rvol_detector.py -v`
Expected: PASS — 26 tests total

- [ ] **Step 7: Commit**

```bash
git add signals/strategies/orb_rvol/__init__.py signals/strategies/orb_rvol/detector.py tests/strategies/test_orb_rvol_detector.py
git commit -m "feat(orb_rvol): add entry/stop/target detector rules"
```

---

## Task 3: Router dispatch

**Files:**
- Modify: `signals/strategies/router.py`
- Test: `tests/strategies/test_orb_rvol_router.py`

- [ ] **Step 1: Write the failing test**

Create `tests/strategies/test_orb_rvol_router.py` (mirrors `test_cloud_mss_router.py`):

```python
"""orb_rvol must be dispatchable through the shared router."""
from signals.models import SIGNAL_STRATEGIES
from signals.strategies import detect_setup
from signals.strategies.orb_rvol.detector import MIN_CANDLES


def _candles(n):
    from signals.models import Candle
    return [Candle(i * 900_000, 100.0, 100.2, 99.8, 100.0, 10.0)
            for i in range(n)]


def test_key_is_registered():
    assert "orb_rvol" in SIGNAL_STRATEGIES


def test_router_dispatches_without_error():
    n = MIN_CANDLES
    candles = _candles(n)
    result = detect_setup(
        "orb_rvol", "BTCUSD", candles,
        [None] * n, [None] * n, [None] * n, [None] * n, [2.0] * n,
        adx14=None, htf_trend=None, h1_candles=None,
    )
    # This synthetic series has no real session anchors aligned to it in a
    # way that would produce a setup — the point of this test is that
    # dispatch itself does not raise, not that a setup fires.
    assert result is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_router.py -v`
Expected: FAIL — `AssertionError` on `test_key_is_registered` (orb_rvol not yet in `SIGNAL_STRATEGIES`), and `test_router_dispatches_without_error` falls through to the `ema_cross` default branch with a "Unknown signal_strategy" print but should still return `None` without raising. Confirm both fail/pass as expected before moving on — the registration assertion is the one that must fail here.

- [ ] **Step 3: Add `orb_rvol` dispatch to the router**

In `signals/strategies/router.py`, add the import:

```python
from signals.strategies.orb_rvol import detect_setup as detect_orb_rvol_setup
```

(Insert alphabetically among the existing `from signals.strategies.X import detect_setup as ...` lines, i.e. after the `msnr` import and before `sr_zone`.)

Add a new branch inside `detect_setup`, alongside the other single-timeframe strategies (e.g. right after the `sr_zone` branch):

```python
    if strategy == "orb_rvol":
        return detect_orb_rvol_setup(
            symbol, candles, atr14, adx14=adx14, htf_trend=htf_trend,
        )
```

- [ ] **Step 4: Add `"orb_rvol"` to `SIGNAL_STRATEGIES` in `signals/models.py`**

Change:

```python
# Every strategy the router can dispatch to.
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry", "cloud_mss", "msnr")
```

to:

```python
# Every strategy the router can dispatch to.
SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
                     "bbma_extreme", "bbma_reentry", "cloud_mss", "msnr",
                     "orb_rvol")
```

(`ADMIN_SELECTABLE_STRATEGIES` is a separate list handled in Task 4 — do not touch it here.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/strategies/test_orb_rvol_router.py -v`
Expected: PASS — 2 tests

- [ ] **Step 6: Run the full strategies test directory to check for regressions**

Run: `.venv/bin/python -m pytest tests/strategies/ -v`
Expected: PASS — all tests, including the pre-existing router tests for other strategies

- [ ] **Step 7: Commit**

```bash
git add signals/strategies/router.py signals/models.py tests/strategies/test_orb_rvol_router.py
git commit -m "feat(orb_rvol): register the strategy and wire router dispatch"
```

---

## Task 4: Admin-selectable sync — `ADMIN_SELECTABLE_STRATEGIES`, migration, admin dropdown

**Files:**
- Modify: `signals/models.py`
- Modify: `web/src/lib/supabase/admin.ts`
- Create: `supabase/migrations/20260817010000_allow_orb_rvol_strategy.sql`
- Test: `tests/core/test_strategy_choices.py` (existing — no edits, just must keep passing)

This is the three-way sync the 2026-08-17 spec amendment flagged: Python, the admin dropdown, and the Postgres CHECK constraint must all agree, or a value Python accepts gets silently rejected by the database on write.

- [ ] **Step 1: Confirm the pinning test currently passes (baseline before the change)**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: PASS — 4 tests (orb_rvol is not yet in any of the three sources, so they still agree with each other)

- [ ] **Step 2: Add `"orb_rvol"` to `ADMIN_SELECTABLE_STRATEGIES` in `signals/models.py`**

Change:

```python
ADMIN_SELECTABLE_STRATEGIES = ("ema_cross", "ict_smc", "sr_zone",
                               "bbma_reentry", "bbma_extreme")
```

to:

```python
ADMIN_SELECTABLE_STRATEGIES = ("ema_cross", "ict_smc", "sr_zone",
                               "bbma_reentry", "bbma_extreme", "orb_rvol")
```

- [ ] **Step 3: Run the pinning test to see it fail against the other two sources**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: FAIL — `test_admin_dropdown_matches_python` and `test_database_constraint_matches_python` both fail (Python now has `orb_rvol`, the other two don't yet)

- [ ] **Step 4: Add the dropdown entry to `web/src/lib/supabase/admin.ts`**

In the `SIGNAL_STRATEGIES` array (after the `bbma_extreme` entry, before the closing `] as const;`), add:

```typescript
  {
    id: "orb_rvol",
    label: "Opening Range Breakout + Relative Volume",
    description:
      "Trades the first breakout of a session's opening range (Asia/London/NY) in the range's own direction, gated on abnormal volume vs. that anchor's own history. Not yet backtested over long history — see docs/orb-rvol-backtest-results.md once available.",
  },
```

- [ ] **Step 5: Create the migration**

Create `supabase/migrations/20260817010000_allow_orb_rvol_strategy.sql` (mirrors `20260728000100_allow_bbma_strategies.sql`):

```sql
-- Allow the swing session to be switched to orb_rvol.
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
-- orb_rvol is NOT assigned to a live TRADING_SESSIONS slot by this
-- migration or the work that introduced it — it is admin-selectable only so
-- it can be tried manually, pending the long-history verdict in
-- docs/orb-rvol-backtest-results.md. See
-- docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.
--
-- Idempotent: re-creating the constraint is safe.
alter table public.bot_settings
    drop constraint if exists bot_settings_signal_strategy_check;
alter table public.bot_settings
    add constraint bot_settings_signal_strategy_check
    check (signal_strategy in ('ema_cross', 'ict_smc', 'sr_zone',
                               'bbma_reentry', 'bbma_extreme', 'orb_rvol'));
```

- [ ] **Step 6: Run the pinning test to verify all three sources agree**

Run: `.venv/bin/python -m pytest tests/core/test_strategy_choices.py -v`
Expected: PASS — 4 tests

- [ ] **Step 7: Run the full Python test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no failures

- [ ] **Step 8: Commit**

```bash
git add signals/models.py web/src/lib/supabase/admin.ts supabase/migrations/20260817010000_allow_orb_rvol_strategy.sql
git commit -m "feat(orb_rvol): make the strategy admin-selectable (Python + dropdown + DB constraint)"
```

> Note: this migration is not applied to the live database by this plan — that is a separate, deliberate operational step (running `supabase db push` or equivalent against production), out of scope here. Flag it to the user before applying.

---

## Task 5: No-setup indicators in the scan pipeline

**Files:**
- Modify: `signals/pipeline/scan.py`

`_no_setup_indicators` decides what gets logged to `ai_events` when a strategy finds nothing — every strategy needs a branch or it silently falls through to the generic EMA/RSI/MACD fallback, which would log misleading fields for a strategy that uses none of them (the exact bug `cloud_mss`'s branch comment already warns about).

- [ ] **Step 1: Add the `orb_rvol` branch**

In `signals/pipeline/scan.py`, inside `_no_setup_indicators`, add a branch. The function currently reads:

```python
def _no_setup_indicators(strategy, atr14, adx14, htf_trend,
                         ema9, ema21, rsi14, macd_hist):
    """Indicators to attach to a no-setup ai_event, or None while a required
    series is still warming up (mirrors the previous per-strategy branches)."""
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "cloud_mss"):
        if atr14[-1] is None:
            return None
        indicators = {"strategy": strategy, "atr": atr14[-1]}
        # ict_fvg intentionally omits ADX (matches prior behavior).
        if strategy != "ict_fvg" and adx14[-1] is not None:
            indicators["adx"] = adx14[-1]
        if htf_trend is not None:
            indicators["htf_trend"] = htf_trend
        return indicators
    if strategy == "ce_lwma":
        return {"strategy": "ce_lwma"}
    return _latest_indicators(ema9, ema21, rsi14, macd_hist)
```

`orb_rvol` shares the exact same "tag strategy + ATR (+ ADX/HTF if present)" shape as `ict_smc`/`ict_fvg`/`sr_zone`/`cloud_mss` — it just also isn't an anchor-dependent, opening-range-window quantity, so add it to that tuple rather than writing a new branch:

```python
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "cloud_mss", "orb_rvol"):
```

(This is a one-line change — the rest of the function body already handles it correctly: `orb_rvol` is not `"ict_fvg"`, so it does get an `adx` field when available, matching the strategy's own `_indicators()` in `detector.py` which also records `adx`/`htf_trend` when present.)

- [ ] **Step 2: Write a regression test**

Add to a new file `tests/core/test_orb_rvol_no_setup_indicators.py`:

```python
"""orb_rvol must not fall through to the generic EMA/RSI/MACD no-setup
indicators — that would log misleading fields for a strategy that uses
none of them (see cloud_mss's equivalent regression test/comment)."""
from signals.pipeline.scan import _no_setup_indicators


def test_orb_rvol_no_setup_indicators_are_strategy_tagged():
    indicators = _no_setup_indicators(
        "orb_rvol", [2.0] * 5, [25.0] * 5, "up",
        [1.0] * 5, [1.0] * 5, [50.0] * 5, [0.0] * 5,
    )
    assert indicators["strategy"] == "orb_rvol"
    assert indicators["atr"] == 2.0
    assert indicators["adx"] == 25.0
    assert indicators["htf_trend"] == "up"
    assert "ema9" not in indicators
    assert "rsi" not in indicators


def test_orb_rvol_no_setup_indicators_none_while_atr_warms_up():
    assert _no_setup_indicators(
        "orb_rvol", [None], [None], None, [None], [None], [None], [None],
    ) is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_orb_rvol_no_setup_indicators.py -v`
Expected: FAIL — `test_orb_rvol_no_setup_indicators_are_strategy_tagged` gets `ema9`/`rsi` keys instead (falls through to the generic branch)

- [ ] **Step 4: Make the one-line change from Step 1**

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_orb_rvol_no_setup_indicators.py -v`
Expected: PASS — 2 tests

- [ ] **Step 6: Run the full pipeline test directory to check for regressions**

Run: `.venv/bin/python -m pytest tests/core/ -q`
Expected: PASS — no failures

- [ ] **Step 7: Commit**

```bash
git add signals/pipeline/scan.py tests/core/test_orb_rvol_no_setup_indicators.py
git commit -m "feat(orb_rvol): tag no-setup ai_events with strategy-specific indicators"
```

---

## Task 6: LLM confirmation prompt — no-setup reason, indicator formatting, strategy line

**Files:**
- Modify: `signals/pipeline/composer.py`
- Modify: `tests/core/test_composer.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_composer.py`:

```python
def test_build_messages_orb_rvol_does_not_crash_on_missing_ema9():
    """orb_rvol indicators have no ema9/ema21/rsi/macd_hist keys — the
    generic EMA fallback in _format_indicators must not be reached for it."""
    setup = CandidateSetup(
        symbol="BTCUSD", direction="long", entry=64500.0,
        stop_loss=64100.0, take_profit=65300.0,
        indicators={
            "strategy": "orb_rvol", "session": "London", "or_high": 64400.0,
            "or_low": 64200.0, "or_direction": "bullish", "rvol": 2.4,
            "atr": 120.0, "anchor_time": 1_700_000_000_000,
        },
    )
    user_content = build_messages(setup, strategy="orb_rvol")[1]["content"]
    assert "opening range" in user_content.lower()
    assert "rvol" in user_content.lower() or "RVOL" in user_content


def test_confirm_setup_orb_rvol_calls_llm_instead_of_fail_closed_rejecting():
    """Regression guard, same shape as the cloud_mss one: a broken
    _format_indicators branch would make every orb_rvol candidate crash
    inside build_messages, which confirm_setup silently turns into a
    fail-closed reject without ever calling the LLM."""
    setup = CandidateSetup(
        symbol="BTCUSD", direction="long", entry=64500.0,
        stop_loss=64100.0, take_profit=65300.0,
        indicators={
            "strategy": "orb_rvol", "session": "London", "or_high": 64400.0,
            "or_low": 64200.0, "or_direction": "bullish", "rvol": 2.4,
            "atr": 120.0, "anchor_time": 1_700_000_000_000,
        },
    )
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 65, "rationale": "ok"}')
    result = confirm_setup(setup, llm, strategy="orb_rvol")
    assert llm.last_messages is not None
    assert result.verdict == "confirm"


def test_no_setup_rationale_orb_rvol():
    from signals.pipeline.composer import no_setup_rationale

    rationale = no_setup_rationale(
        "BTCUSD", "15m",
        {"strategy": "orb_rvol", "atr": 120.0},
        strategy="orb_rvol",
    )
    assert "opening range" in rationale.lower() or "opening-range" in rationale.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -k orb_rvol -v`
Expected: FAIL — all three (no `orb_rvol` branch exists yet in any of `_no_setup_reason`, `_format_indicators`, or `build_messages`)

- [ ] **Step 3: Add the `orb_rvol` branch to `_no_setup_reason`**

In `signals/pipeline/composer.py`, inside `_no_setup_reason`, add (after the `cloud_mss` branch, before the `bbma_extreme`/`bbma_reentry` one):

```python
    if strategy == "orb_rvol":
        return (
            f"The rules engine found no valid opening-range breakout (need "
            f"a session opening range with abnormally high relative volume, "
            f"followed by the first breakout in the range's own direction, "
            f"on the {chart})."
        )
```

- [ ] **Step 4: Add the `orb_rvol` branch to `_format_indicators`**

In the same file, inside `_format_indicators`, add (after the `cloud_mss` branch, before the `bbma_extreme`/`bbma_reentry` one):

```python
    if active == "orb_rvol":
        parts = []
        for key, label in (
            ("session", "session"),
            ("or_high", "OR high"),
            ("or_low", "OR low"),
            ("or_direction", "OR direction"),
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
        return ", ".join(parts) if parts else "no opening-range reading"
```

- [ ] **Step 5: Add the `orb_rvol` branch to `build_messages`**

In the same file, inside `build_messages`, add (after the `cloud_mss` `elif`, before the `bbma_extreme` one):

```python
    elif active == "orb_rvol":
        session = ind.get("session") or "session"
        strategy_line = (
            f"- Strategy: Opening Range Breakout + Relative Volume "
            f"({session} open; first breakout in the range's own direction, "
            f"gated on abnormal volume; wide 2R/4R/6R targets)\n"
        )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -k orb_rvol -v`
Expected: PASS — 3 tests

- [ ] **Step 7: Run the full composer test file to check for regressions**

Run: `.venv/bin/python -m pytest tests/core/test_composer.py -v`
Expected: PASS — all tests

- [ ] **Step 8: Commit**

```bash
git add signals/pipeline/composer.py tests/core/test_composer.py
git commit -m "feat(orb_rvol): wire the LLM confirmation prompt and no-setup rationale"
```

---

## Task 7: RAG playbook chunks

**Files:**
- Modify: `signals/rag/playbook.py`
- Test: `tests/rag/test_rag.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/rag/test_rag.py`:

```python
def test_playbook_covers_orb_rvol():
    chunks = [c for c in PLAYBOOK_CHUNKS if c["strategy"] == "orb_rvol"]
    assert len(chunks) == 2
    titles = {c["title"].lower() for c in chunks}
    assert any("confirm" in t for t in titles)
    assert any("reject" in t for t in titles)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/rag/test_rag.py::test_playbook_covers_orb_rvol -v`
Expected: FAIL — `assert 0 == 2`

- [ ] **Step 3: Add the two chunks**

In `signals/rag/playbook.py`, add to the `PLAYBOOK_CHUNKS` tuple (after the `msnr` chunks, before the closing `)`):

```python
    {
        "strategy": "orb_rvol",
        "title": "15m Opening Range Breakout confirm gate",
        "body": (
            "orb_rvol: trades the first breakout of a session opening range "
            "(Asia 00:00 / London 07:00 / NY 13:30 UTC, first 30 minutes), "
            "in the direction the range itself moved -- a bullish range only "
            "permits longs, bearish only shorts, a doji range no trade. "
            "Fires only when the opening range traded on relative volume "
            ">= 1.0x its own anchor's recent history; this filter is the "
            "entire source of the strategy's edge (SSRN 4729284) -- plain "
            "ORB without it underperforms buy-and-hold. Stop sits at the "
            "opposite edge of the range plus an ATR buffer; wide 2R/4R/6R "
            "targets since the edge depends on runners. Confirm when "
            "direction, RVOL and the breakout close all agree."
        ),
    },
    {
        "strategy": "orb_rvol",
        "title": "15m Opening Range Breakout reject cues",
        "body": (
            "Reject orb_rvol when relative volume is at or below its own "
            "anchor's recent average (the headline gate), when the proposed "
            "direction contradicts the opening range's own bullish/bearish "
            "read, when the range itself was a doji, or when the stop is "
            "farther than 2.5 ATR from entry. Do not reject solely for "
            "missing higher-timeframe agreement -- this strategy takes no "
            "HTF gate by design (the opening range is its own thesis)."
        ),
    },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/rag/test_rag.py -v`
Expected: PASS — all tests, including the new one and the pre-existing `test_playbook_covers_all_strategies`

- [ ] **Step 5: Commit**

```bash
git add signals/rag/playbook.py tests/rag/test_rag.py
git commit -m "feat(orb_rvol): add RAG playbook confirm-gate and reject-cue chunks"
```

---

## Task 8: Backtest registration — quick dev-loop check

**Files:**
- Modify: `signals/analysis/backtest.py`

This wires `orb_rvol` into `signals/analysis/backtest.py`'s existing `main()` loop (live-API data, ~720 bars) for fast iteration during development, and adds the extended-history pagination helper the spec calls for so `orb_rvol` specifically gets closer to the ~90-opens-per-symbol sample RVOL needs, without changing any other strategy's behavior in that file. The DECISIVE long-history verdict is Task 9, against verified Binance archives.

- [ ] **Step 1: Add `"15m"` to `TF_MINUTES` and register `orb_rvol` in `STRATEGY_TIMEFRAMES`**

In `signals/analysis/backtest.py`, change:

```python
TF_MINUTES = {"5m": 5, "1h": 60, "4h": 240}
```

to:

```python
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
```

Change:

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

to:

```python
STRATEGY_TIMEFRAMES = {
    "ict_fvg": "5m",
    "ema_cross": "1h",
    "ict_smc": "1h",
    "sr_zone": "1h",
    "bbma_extreme": "1h",
    "bbma_reentry": "1h",
    "orb_rvol": "15m",
}
```

Leave `CONFLUENCE_TIMEFRAMES` untouched — `orb_rvol` deliberately has no entry there (no HTF gate), so `main()`'s `CONFLUENCE_TIMEFRAMES.get("orb_rvol")` correctly returns `None`.

- [ ] **Step 2: Add the extended-history pagination helper**

`orb_rvol`'s `detect_setup` uses the *router* signature (`symbol, candles, atr14, adx14=None, htf_trend=None`), same as `sr_zone`/`ict_smc` — but `main()` currently calls the generic `backtest_strategy(strategy, symbol, candles, ...)`, which re-derives `ema9`/`rsi`/etc. internally and calls through the router. That already works for `orb_rvol` with no changes (the router dispatch from Task 3 handles it) — the only gap is candle depth. Add this helper near the top of `signals/analysis/backtest.py`, after the `TF_MINUTES` definition:

```python
from datetime import datetime, timezone


def fetch_extended_history(symbol, timeframe, total_bars, *, session=None):
    """Page `fetch_candles` backward via `start_time` to assemble more
    history than a single request returns.

    Kraken caps OHLC at ~720 bars/request and offers no deeper history;
    Yahoo (gold) caps intraday depth too. This pages forward from
    `now - total_bars * interval`, using each batch's newest `open_time` as
    the next page's `start_time`, de-duplicating by `open_time`, and
    stopping once a page returns nothing new. Bounded by what the provider
    actually has — takes what is available rather than failing.
    """
    from signals.clients.market import fetch_candles

    minutes = TF_MINUTES.get(timeframe)
    if minutes is None:
        raise ValueError(f"unknown timeframe {timeframe!r}")
    interval_ms = minutes * 60_000
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cursor = now_ms - total_bars * interval_ms

    session = session or __import__("requests").Session()
    seen: dict[int, object] = {}
    while cursor < now_ms:
        page = fetch_candles(symbol, timeframe, 720, start_time=cursor,
                             session=session)
        new = [c for c in page if c.open_time not in seen]
        if not new:
            break
        for c in new:
            seen[c.open_time] = c
        cursor = max(c.open_time for c in new) + interval_ms

    candles = sorted(seen.values(), key=lambda c: c.open_time)
    return candles[-total_bars:] if len(candles) > total_bars else candles
```

- [ ] **Step 3: Use the extended helper for `orb_rvol` specifically in `main()`**

In `main()`, the existing per-strategy candle fetch is:

```python
        for symbol in DEFAULT_SYMBOLS:
            try:
                candles = fetch_candles(
                    symbol, timeframe, DEFAULT_CANDLE_LIMIT, session=session,
                )[:-1]  # drop the still-forming last bar
```

Change it to use the extended helper only for `orb_rvol`, leaving every other strategy's behavior in this file completely unchanged:

```python
        for symbol in DEFAULT_SYMBOLS:
            try:
                if strategy == "orb_rvol":
                    candles = fetch_extended_history(
                        symbol, timeframe, 3000, session=session,
                    )[:-1]
                else:
                    candles = fetch_candles(
                        symbol, timeframe, DEFAULT_CANDLE_LIMIT, session=session,
                    )[:-1]  # drop the still-forming last bar
```

- [ ] **Step 4: Verify the module still imports cleanly and existing behavior is unchanged**

Run: `.venv/bin/python -c "from signals.analysis.backtest import STRATEGY_TIMEFRAMES, fetch_extended_history; print(STRATEGY_TIMEFRAMES)"`
Expected: prints the dict including `'orb_rvol': '15m'`, no errors

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no failures (this file has no dedicated test suite; the check here is that nothing else that imports from `signals.analysis.backtest` broke)

- [ ] **Step 5: Commit**

```bash
git add signals/analysis/backtest.py
git commit -m "feat(orb_rvol): register for the quick backtest.py check and add extended-history pagination"
```

---

## Task 9: Long-history verdict — `scripts/orb_rvol_report.py`

**Files:**
- Create: `scripts/orb_rvol_report.py`

This is the actual gate. Modeled directly on `scripts/bbma_history_report.py`, against the same SHA256-verified Binance monthly archives.

- [ ] **Step 1: Write the script**

Create `scripts/orb_rvol_report.py`:

```python
"""orb_rvol backtested over the full verified Binance history (~8.9 years).

Same data and harness as scripts/bbma_history_report.py: SHA256-verified
monthly archives (scripts/history_provenance.py -- run that first if you have
not), replayed through backtest_windowed so a setup only counts here if it
would have fired live.

Binance lists no gold or GBP, so XAUUSD and GBPUSD are not covered here -- see
the "Extended backtest history" section of
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md for their
shorter, live-API-paginated check instead (signals.analysis.backtest.main
with STRATEGY_TIMEFRAMES["orb_rvol"]).

WINDOW is MIN_CANDLES (400), not the 200 bbma_history_report.py uses: the
detector's own guard clause requires 400 candles just to evaluate, so a
narrower window would silently report zero trades instead of a verdict.

Usage: .venv/bin/python -m scripts.orb_rvol_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.strategies.orb_rvol.detector import MIN_CANDLES, detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "15m"
WINDOW = MIN_CANDLES
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled_gross, pooled_net = [], []

    print("orb_rvol over the full verified Binance history. Scale-out model: "
          "1/3 at each of TP1/TP2/TP3 (2R/4R/6R), fixed stop as published.")
    print(f"{WINDOW}-bar rolling window (matches MIN_CANDLES -- the "
          "detector's own floor). No HTF gate (orb_rvol takes none by "
          "design).\n")
    print(f"{'symbol':7} {'years':>6} {'bars':>7} {'trades':>7} {'tp1%':>6} "
          f"{'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>9}")
    print("-" * 70)

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = [None] * len(candles)

        out = backtest_windowed(detect_setup, symbol, candles, atr14, trends,
                                window=WINDOW, max_hold=MAX_HOLD)
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

- [ ] **Step 2: Verify the script imports and parses cleanly**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/orb_rvol_report.py').read())"`
Expected: no output, no error (syntax check without running the actual multi-year download)

Run: `.venv/bin/python -c "from scripts.orb_rvol_report import main; print('ok')"`
Expected: `ok` (import check — confirms `signals.analysis.backtest.backtest_windowed`, `signals.analysis.history.load_history`, and `signals.strategies.orb_rvol.detector` all resolve)

- [ ] **Step 3: Commit**

```bash
git add scripts/orb_rvol_report.py
git commit -m "feat(orb_rvol): add the long-history backtest report script"
```

---

## Task 10: Run the full suite, run the verdict, record the result

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md` (append a pointer, not a rewrite)
- Create: `docs/orb-rvol-backtest-results.md`

- [ ] **Step 1: Run the complete Python test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — every test, including all `orb_rvol` tests added in Tasks 1–7 and no regressions anywhere else

- [ ] **Step 2: Run data provenance verification (first time only, or if the cache is stale)**

Run: `.venv/bin/python -m scripts.history_provenance`
Expected: prints SHA256 verification results and known-market-event checks, all passing. This may take several minutes on first run (downloads and verifies ~107 monthly archives per symbol/timeframe pair already cached by prior strategies' reports; `orb_rvol_report.py` additionally needs the 15m archives, which is a new interval not previously downloaded for BTCUSDT/ETHUSDT — expect a longer first run while those download).

- [ ] **Step 3: Run the long-history report and capture its output**

Run: `.venv/bin/python -m scripts.orb_rvol_report | tee /tmp/orb_rvol_report_output.txt`
Expected: a table (BTCUSD row, ETHUSD row) followed by a POOLED summary line with `net=`, `t=`, and a 95% CI. This is a real historical backtest over ~8.87 years of 15m data — expect it to take noticeably longer than the 1h/4h bbma report (15m has ~4x the bar count of 1h over the same span), plausibly several minutes once archives are cached.

- [ ] **Step 4: Write `docs/orb-rvol-backtest-results.md`**

Using the actual numbers from Step 3's output (not placeholder numbers — copy the real printed table and POOLED line), write the results doc following the same shape as `docs/cloud-mss-backtest-results.md` and `docs/bbma-backtest-results.md`:

- A headline stating plainly whether `orb_rvol` is net profitable at the measured net expectancy and t-statistic — **write the honest answer, whichever direction it comes out**, matching this repo's established practice of publishing losing results as plainly as winning ones.
- The full per-symbol table and pooled statistics, verbatim from the report's output.
- A comparison line against the other five strategies' net-per-trade numbers already on record (`cloud_mss` −0.046R, `bbma_reentry` −0.137R at 15m-equivalent scope / +0.120R at 1h/4h, `bbma_extreme` −0.019R to −0.153R, `sr_zone` −0.415R, `sr_limit` −0.015R), so the new number reads in context rather than in isolation.
- The caveat this repo consistently states for BBMA-style crypto-only long-history runs: `XAUUSD`/`GBPUSD` are not covered by the Binance-archive test, and remain on the much shorter live-API-paginated sample from Task 8's `fetch_extended_history` path if that was also run.
- A verdict section stating explicitly: `orb_rvol` remains admin-selectable only, `TRADING_SESSIONS` is unchanged, and promoting it to a live session slot is a separate decision for the user to make with these numbers in hand — mirroring exactly how this repo already decided on `cloud_mss` (shipped despite a loss, with the number stated) and `bbma_reentry` (promoted to a paper trial on a genuine edge). Do not make that promotion decision as part of this task.

- [ ] **Step 5: Add a pointer from the spec to the results doc**

In `docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md`, at the very top (right after the title, before "## Goal"), add:

```markdown
> **Implemented 2026-08-17.** See `docs/orb-rvol-backtest-results.md` for the
> long-history verdict and `docs/superpowers/plans/2026-08-17-orb-rvol-strategy.md`
> for the implementation plan.
```

- [ ] **Step 6: Commit**

```bash
git add docs/orb-rvol-backtest-results.md docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md
git commit -m "docs(orb-rvol): record the long-history backtest verdict"
```

---

## Self-Review Notes

**Spec coverage:** Every section of the spec maps to a task — Detector contract & Algorithm → Tasks 1–2; File layout → Tasks 1–2; Integration table → Tasks 3–7 (one task per file group, matching the table's grouping); Extended backtest history → Task 8; Long-history verdict (2026-08-17 addition) → Task 9; the spec's "Out of scope" items (live session assignment, time-based exit, cross-sectional ranking, htf_trend veto A/B) are correctly left undone by this plan.

**Placeholder scan:** No TBD/TODO markers. Task 10's results-doc step is necessarily written against real output the plan cannot pre-compute (an actual 8.87-year backtest run), so it specifies exactly what to capture and how to structure the writeup rather than pre-filling numbers — that is data collection, not an unresolved design decision.

**Type/signature consistency:** `detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None)` is identical across windows.py's consumers (Task 2), router.py's dispatch (Task 3), the router test (Task 3), and `backtest_windowed`'s call convention (Task 9) — checked against `sr_zone`'s identical signature as the template. `MIN_CANDLES`, `MIN_RVOL_SAMPLES`, `OR_BARS`, `TRADE_WINDOW_BARS`, `RVOL_LOOKBACK` are defined once each (`detector.py` or `windows.py`) and imported everywhere else they're used, never redefined with a different value.
