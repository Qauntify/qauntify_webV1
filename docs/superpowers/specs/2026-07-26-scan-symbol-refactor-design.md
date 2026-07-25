# Refactor scan_symbol (behavior-preserving)

## Goal

Make `signals/run.py`'s `scan_symbol` (~283 lines, mixed concerns) readable
top-to-bottom by extracting three helpers, with **zero behavior change**.

## Acceptance criterion

**Every existing test in `tests/core/test_pipeline.py` (and the rest of the
suite) passes completely unchanged.** No test file is edited. That green suite
is the proof that behavior is identical — it already covers the no-setup,
confirmed, LLM-rejected, below-threshold, storage-failure, HTF, ADX, forming-bar,
threading, and main-parallelism paths.

## Decisions (approved)

- Pure internal refactor of `scan_symbol` + three new module-private helpers in
  `run.py`. No public-signature change to `scan_symbol` itself.
- **Not** in scope (separate follow-ups): the Strategy registry, the
  `print()` → `logging` swap, and a `fetch_closed_candles` wrapper in
  `market_client`.

## Architecture

### `_reject(...)` — unify the no-signal paths

Today three paths each hand-build a `NoSignalReport` **and** call `_log_ai_event`
with the same nine fields: no-setup ([run.py:388–405]), LLM-rejected
([run.py:431–459]), and below-store-threshold ([run.py:461–494]). Extract:

```
_reject(symbol, cfg, *, timeframe, report_kind, event_kind, rationale,
        indicators, candles, setup=None, confidence=None, session=None)
    -> ScanResult
```

It calls `_log_ai_event(event_kind, …)` then returns
`ScanResult(no_signal=NoSignalReport(kind=report_kind, …), candles=candles)`.
Trade fields (`direction`/`entry`/`stop_loss`/`take_profit`) come from `setup`
when present, else `None`. Note the existing naming: the `rejected` report uses
event kind `"reject"`; `no_setup` uses the same string for both. The
storage-failure path ([run.py:502–523]) logs a `reject` event but returns
`ScanResult(candles=candles)` with no report — kept as a thin inline discard
(or a `report=None` variant of the helper).

### `_no_setup_indicators(strategy, atr14, adx14, htf_trend, ema9, ema21, rsi14, macd_hist)`

The per-strategy `if/elif` chain at [run.py:340–405] that picks which indicators
to attach to a no-setup event moves into one function returning the indicators
dict, or `None` when a required series (e.g. `atr14[-1]`) is still warming up
(preserving the current early-returns).

### `_load_market_data(symbol, timeframe, strategy, cfg, *, confluence_timeframe, session)`

The fetch-candles (with the `ce_lwma` 220-bar bump) + drop-forming-bar + compute
EMA/RSI/MACD/ATR/ADX + optional H1 (ce_lwma) / HTF-trend (confluence) block
([run.py:290–334]) moves into one function returning a small bundle
(`candles`, `ema9`, `ema21`, `rsi14`, `macd_hist`, `atr14`, `adx14`,
`htf_trend`, `h1_candles`), or `None` on any data-fetch failure (preserving the
current "skip on data unavailable" returns). A lightweight dataclass or a
`NamedTuple` (`MarketData`) carries the bundle.

### `scan_symbol` after

Reads as a sequence: recency guard → `_load_market_data` → `detect_setup` →
(no setup → `_reject`) → `already_signaled` guard → RAG + `confirm_setup` →
(reject / below-threshold → `_reject`) → `make_signal` + `attach_chart` +
`save_signal` → (store fail → discard) → confirm log → `ScanResult(signal=…)`.
Target ~90 lines.

## Testing

- Run `.venv/bin/python -m pytest tests/ -q` — the whole suite stays green with
  **no test edits**. This is both the acceptance criterion and the regression
  guard for each extraction step.
- Optionally add one focused test asserting `_reject` writes an ai_event and
  returns a `NoSignalReport` with the setup-derived fields — but the existing
  behavioral tests already cover the paths, so this is optional, not required.

## Rough build order

Extract one helper at a time, running the suite green after each:
1. `_reject` (biggest duplication win).
2. `_no_setup_indicators`.
3. `_load_market_data`.
4. Final read-through of the slimmed `scan_symbol`.
