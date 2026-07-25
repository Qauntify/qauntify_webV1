# scan_symbol Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slim `signals/run.py`'s `scan_symbol` from ~283 lines to ~90 by extracting three module-private helpers — with zero behavior change.

**Architecture:** This is a REFACTOR, not new behavior. The regression guard is the **existing** test suite: after every extraction, `.venv/bin/python -m pytest tests/ -q` must pass with **no test-file edits**. That green suite is the proof behavior is unchanged.

**Tech Stack:** Python 3.12, pytest.

---

## Refactor discipline (read first)

- Do NOT edit any test file. The existing tests (esp. `tests/core/test_pipeline.py`, ~30 cases) define the behavior being preserved.
- After each task, run the FULL suite and confirm it is still green before committing.
- Preserve every existing `print(...)` line and its exact wording — several are load-bearing for the run summary / logs. Keep them where the plan shows.
- Use `.venv/bin/python -m pytest` (the `.venv/bin/pip`/`pytest` shims are broken here).

---

## Task 1: Extract `_reject` helper

**Files:** Modify `signals/run.py`

Unifies the three no-signal paths (no-setup, LLM-rejected, below-threshold) that each build a `NoSignalReport` and call `_log_ai_event` with the same fields.

- [ ] **Step 1: Add the helper**

In `signals/run.py`, add this function immediately after `_log_ai_event` (which ends around line 259):

```python
def _reject(symbol, cfg, *, timeframe, report_kind, event_kind, rationale,
            indicators, candles, setup=None, confidence=None, session=None):
    """Log a no-setup/reject ai_event and return the matching ScanResult.

    Trade fields (direction/entry/stop_loss/take_profit) come from `setup` when
    present, else None. `report_kind` is the NoSignalReport kind ("no_setup" /
    "rejected"); `event_kind` is the ai_events kind ("no_setup" / "reject").
    """
    direction = setup.direction if setup is not None else None
    entry = setup.entry if setup is not None else None
    stop_loss = setup.stop_loss if setup is not None else None
    take_profit = setup.take_profit if setup is not None else None
    _log_ai_event(
        event_kind, symbol, cfg, timeframe=timeframe, rationale=rationale,
        indicators=indicators, headlines=[], direction=direction, entry=entry,
        stop_loss=stop_loss, take_profit=take_profit, confidence=confidence,
        session=session,
    )
    return ScanResult(no_signal=NoSignalReport(
        symbol=symbol, timeframe=timeframe, kind=report_kind, rationale=rationale,
        indicators=indicators, direction=direction, entry=entry,
        stop_loss=stop_loss, take_profit=take_profit, confidence=confidence,
    ), candles=candles)
```

- [ ] **Step 2: Rewire the no-setup path**

In `scan_symbol`, the block that currently starts with `rationale = no_setup_rationale(...)` and ends with the `return ScanResult(no_signal=NoSignalReport(... kind="no_setup" ...), candles=candles)` (around [run.py:385–405]) — replace the `_log_ai_event("no_setup", ...)` call + the `print(...)` + the `return ScanResult(no_signal=NoSignalReport(...))` with:

```python
        rationale = no_setup_rationale(
            symbol, timeframe, indicators, strategy=strategy,
        )
        print(f"[{symbol}] no-signal analysis: {rationale}")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="no_setup",
            event_kind="no_setup", rationale=rationale, indicators=indicators,
            candles=candles, session=session,
        )
```

(Keep the `no_setup_rationale(...)` computation and the `print`. `setup` is None here → trade fields None, matching today.)

- [ ] **Step 3: Rewire the LLM-rejected path**

Replace the `if confirmation.verdict != "confirm":` block's `_log_ai_event("reject", ...)` + `print` + `return ScanResult(no_signal=NoSignalReport(... kind="rejected" ...))` ([run.py:431–459]) with:

```python
    if confirmation.verdict != "confirm":
        print(f"[{symbol}] rejected by LLM: {confirmation.rationale}")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="rejected",
            event_kind="reject", rationale=confirmation.rationale,
            indicators=setup.indicators, candles=candles, setup=setup,
            confidence=confirmation.confidence, session=session,
        )
```

- [ ] **Step 4: Rewire the below-store-threshold path**

Replace the `if confirmation.confidence < min_store_confidence:` block ([run.py:461–494]) with:

```python
    if confirmation.confidence < min_store_confidence:
        rationale = (
            f"Confidence {confirmation.confidence} below store threshold "
            f"{min_store_confidence}: {confirmation.rationale}"
        )
        print(f"[{symbol}] confirm below store threshold "
              f"({confirmation.confidence} < {min_store_confidence})")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="rejected",
            event_kind="reject", rationale=rationale,
            indicators=setup.indicators, candles=candles, setup=setup,
            confidence=confirmation.confidence, session=session,
        )
```

(The storage-failure `except` block at [run.py:502–523] is left exactly as-is — it uses `signal.*` and returns `ScanResult(candles=candles)` with no report.)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, unchanged. If anything fails, the extraction diverged from behavior — fix the helper/call sites, do not touch the tests.

- [ ] **Step 6: Commit**

```bash
git add signals/run.py
git commit -m "refactor(run): extract _reject helper for no-signal paths"
```

---

## Task 2: Extract `_no_setup_indicators`

**Files:** Modify `signals/run.py`

- [ ] **Step 1: Add the helper**

In `signals/run.py`, add after `_reject`:

```python
def _no_setup_indicators(strategy, atr14, adx14, htf_trend,
                         ema9, ema21, rsi14, macd_hist):
    """Indicators to attach to a no-setup ai_event, or None while a required
    series is still warming up (mirrors the previous per-strategy branches)."""
    if strategy in ("ict_smc", "ict_fvg", "sr_zone"):
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

- [ ] **Step 2: Replace the if/elif chain in `scan_symbol`**

In the `if setup is None:` branch, replace the whole per-strategy `if strategy == "ict_smc": ... elif ... else: indicators = _latest_indicators(...)` chain ([run.py:348–384]) — including its `return ScanResult(candles=candles)` warm-up early-returns — with:

```python
        indicators = _no_setup_indicators(
            strategy, atr14, adx14, htf_trend, ema9, ema21, rsi14, macd_hist,
        )
        if indicators is None:
            return ScanResult(candles=candles)
```

Leave the `if not log_no_setup: return ScanResult(candles=candles)` guard that precedes this (around [run.py:344]) in place, and the subsequent `no_setup_rationale` + `_reject` from Task 1 unchanged.

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, unchanged. (In particular `test_scan_symbol_no_setup_*` and `test_scan_symbol_computes_and_passes_adx_to_detect_setup` must stay green.)

- [ ] **Step 4: Commit**

```bash
git add signals/run.py
git commit -m "refactor(run): extract _no_setup_indicators"
```

---

## Task 3: Extract `_load_market_data`

**Files:** Modify `signals/run.py`

Pulls the candle fetch + indicator computation + H1/HTF fetch into one function. **Behavior subtlety to preserve:** the initial candle-fetch failure returns `ScanResult()` (no candles), but the H1/HTF failures return `ScanResult(candles=candles)` (candles fetched, kept for reuse). The helper therefore returns a `(MarketData | None, candles | None)` pair so the caller can reproduce both exactly.

- [ ] **Step 1: Add the imports + type + helper**

At the top of `signals/run.py`, add `NamedTuple` to the typing/collections imports (add `from typing import NamedTuple` if no typing import exists yet). Then add, after `_no_setup_indicators`:

```python
class MarketData(NamedTuple):
    candles: list
    ema9: list
    ema21: list
    rsi14: list
    macd_hist: list
    atr14: list
    adx14: list
    htf_trend: object
    h1_candles: object


def _load_market_data(symbol, timeframe, strategy, cfg, *,
                      confluence_timeframe=None, session=None):
    """Fetch closed candles + indicators (+ H1 for ce_lwma / HTF trend for
    confluence). Returns (MarketData, candles) on success, (None, None) when the
    initial candle fetch fails, or (None, candles) when a required H1/HTF fetch
    fails after candles were already fetched."""
    candle_limit = max(cfg.candle_limit, 220) if strategy == "ce_lwma" else cfg.candle_limit
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, timeframe, candle_limit, session=session)
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return None, None

    candles = candles[:-1]
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)
    adx14 = adx(highs, lows, closes, 14)
    htf_trend = None
    h1_candles = None
    if strategy == "ce_lwma":
        try:
            h1_raw = with_retry(
                lambda: fetch_candles(symbol, "1h", max(cfg.candle_limit, 80),
                                      session=session)
            )
            h1_candles = h1_raw[:-1]
        except Exception as exc:
            print(f"[{symbol}] H1 CE data unavailable ({type(exc).__name__}), "
                  "skipping")
            return None, candles
    elif confluence_timeframe:
        try:
            htf_trend = _fetch_htf_trend(symbol, confluence_timeframe, cfg,
                                         session=session)
        except Exception as exc:
            print(f"[{symbol}] HTF confluence required but unavailable "
                  f"({type(exc).__name__}), skipping")
            return None, candles

    return MarketData(candles=candles, ema9=ema9, ema21=ema21, rsi14=rsi14,
                      macd_hist=macd_hist, atr14=atr14, adx14=adx14,
                      htf_trend=htf_trend, h1_candles=h1_candles), candles
```

- [ ] **Step 2: Replace the load block in `scan_symbol`**

Replace everything in `scan_symbol` from the `# CE+LWMA needs 200 M15 bars...` comment + `candle_limit = ...` line through the end of the `elif confluence_timeframe:` block ([run.py:290–334]) — i.e. the fetch, `candles = candles[:-1]`, the six indicator computations, and the H1/HTF fetch — with:

```python
    market, candles = _load_market_data(
        symbol, timeframe, strategy, cfg,
        confluence_timeframe=confluence_timeframe, session=session,
    )
    if market is None:
        return ScanResult(candles=candles)
    candles = market.candles
    ema9, ema21 = market.ema9, market.ema21
    rsi14, macd_hist = market.rsi14, market.macd_hist
    atr14, adx14 = market.atr14, market.adx14
    htf_trend, h1_candles = market.htf_trend, market.h1_candles
```

(`candles` bound from the pair covers the failure cases: `None` → `ScanResult()`, or the fetched list on H1/HTF failure → `ScanResult(candles=candles)` — exactly as before. On success it is rebound to `market.candles`, the same list.)

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, unchanged. In particular `test_scan_symbol_binance_failure_returns_none`, `test_scan_symbol_returns_candles_for_reuse`, `test_scan_symbol_drops_forming_candle`, `test_scan_symbol_passes_htf_trend_when_confluence_timeframe_given`, and `test_scan_symbol_skips_htf_fetch_without_confluence_timeframe` must stay green.

- [ ] **Step 4: Commit**

```bash
git add signals/run.py
git commit -m "refactor(run): extract _load_market_data"
```

---

## Definition of Done

- `scan_symbol` reads as a clean sequence (~90 lines); `_reject`, `_no_setup_indicators`, `_load_market_data` carry the extracted logic.
- `.venv/bin/python -m pytest tests/` is fully green with **zero test-file edits** across all three tasks.
- No behavior change: no-setup/reject/below-threshold/storage-fail paths, warm-up early-returns, candle-for-reuse on partial data failure, and every `print` are all preserved.
