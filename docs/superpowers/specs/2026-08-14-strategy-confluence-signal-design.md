# Cross-strategy confluence signal

## Goal

Emit a distinct, deliverable signal when two or more *independent* strategies
are simultaneously long or short the same symbol — a genuinely different,
probably higher-conviction read than any single strategy alone, and something
the system today has no way to notice.

## Why this doesn't happen today

The engine runs three sessions — `super_scalp` (5m, `ict_fvg`), `scalp` (15m,
`cloud_mss`), `swing` (1h, `msnr`) — each scanning independently
(`signals/pipeline/engine.py`). Nothing compares their output. Two strategies
can both be open long on BTCUSD right now and neither the engine, the
Telegram feed, nor a user watching the dashboard would know.

## Definition of confluence

All of the following must hold:

1. **Different strategies.** The two (or more) agreeing signals must come
   from distinct strategies (`msnr`, `cloud_mss`, `ict_fvg`). The same
   strategy firing on two timeframes (e.g. `ict_fvg` on both 5m and 1m) does
   not count — it's correlated, not independent confirmation.
2. **Same symbol, same direction.** Trivial but explicit.
3. **"Agreement" = currently open, any timeframe.** At the moment a new setup
   confirms, check whether a different-strategy signal is already open
   (`status in (open, tp1_hit, tp2_hit)`, `shadow=false`) on the same
   symbol+direction. They do not need to have been detected in the same scan
   cycle — one can have opened days before the other.
4. **Scope: the three main sessions only.** `super_scalp` / `scalp` / `swing`.
   Auxiliary sessions (`xau_scalp` 1m, `war_room`, `bbma`) are out of scope
   for v1 — `war_room` in particular runs its own separate LLM-debate
   pipeline and would need its own wiring.
5. **At most one open confluence signal per symbol at a time.** While a
   confluence signal from a given symbol is still open, a newly-confirmed
   third (or fourth) strategy agreeing does not spawn another one.

## Architecture

A new, focused module — `signals/pipeline/confluence.py` — runs once per
engine cycle, called from `signals/pipeline/engine.py::main()` right after
the three-session scan loop finishes and before the outcome-tracking pass
(`track_open_signals`). It is given the setups confirmed *this run*.

`main()`'s per-session loop already branches on `result.signal is not None`
to call `maybe_send_alert`; it needs to additionally collect those
`Signal` objects into a list (the existing `outcomes` list only holds
summary strings, not the strategy tag or full signal, so it isn't enough on
its own) and pass that list to the confluence pass after the loop.

This keeps `scan_symbol` (already 400+ lines) untouched, and avoids adding
a new cron/workflow — it rides the same cadence and process as the rest of
the engine.

## Detection logic

For each setup confirmed this run:

1. Query open signals for the same symbol + direction, `shadow=false`,
   excluding: the strategy that just fired, and `timeframe='confluence'`
   rows.
2. If any result is from a **different** strategy → confluence.
3. Check no confluence signal is already open for this symbol (query
   `timeframe='confluence'`, `status in (open, tp1_hit, tp2_hit)`,
   `symbol=eq.<symbol>`). If one exists, skip — rule 5 above.
4. Otherwise, build and store a confluence signal (below).

Pseudocode:

```python
def detect_confluence(newly_confirmed: list[ConfirmedSetup], cfg, session):
    for setup in newly_confirmed:
        others = open_signals_same_direction(
            setup.symbol, setup.direction, exclude_strategy=setup.strategy,
            exclude_timeframe="confluence", cfg=cfg, session=session,
        )
        if not others:
            continue
        if confluence_already_open(setup.symbol, cfg, session=session):
            continue
        publish_confluence_signal(setup, others[0], cfg, session=session)
```

## Signal construction

- **Entry / stop / take-profits / confidence:** copied directly from the
  setup that just triggered the check (the "newest contributor"). No new
  LLM call, no blending across contributors' levels.
- **`timeframe`:** `"confluence"`.
- **`indicators`** gains a `confluence_of` field, e.g.
  `["msnr@1h", "cloud_mss@15m"]`, and the rationale text names both
  strategies explicitly (e.g. *"cloud_mss (15m) confirms long, agreeing with
  an already-open msnr (1h) long — confluence signal."*).
- **`indicators["source_timeframe"]`** is also set to the triggering setup's
  *real* interval (e.g. `"15m"`) — required by outcome tracking, see below.
- **Chart:** reuse the triggering setup's own candles via the existing
  `attach_chart`.

## New session registration

Add one entry to `AUXILIARY_SESSIONS` in `signals/models.py`, mirroring the
existing `war_room` ("floor") / `bbma` pattern exactly:

```python
TradingSession(
    name="confluence", timeframe="confluence",
    max_open_days=14,  # matches swing's window — see Risks
    strategy=None,
),
```

This single registration is what makes the existing outcome tracker, expiry
logic, and one-open-per-symbol/timeframe dedup machinery apply to confluence
signals for free — no new tracking code.

## Data model

**Zero migrations.** No new columns. `timeframe="confluence"` plus the
`confluence_of` / `source_timeframe` keys inside the existing `indicators`
JSON is enough — the same technique `war_room` and `bbma` already use to
carry strategy-specific data without schema changes.

## Delivery & outcome tracking

- Stored via the existing `save_signal` (`shadow=false` — a real,
  user-visible signal).
- Delivered via the existing `maybe_send_alert`. The Telegram template needs
  a small formatting addition so a confluence alert is visually distinct
  (e.g. a "🔥 CONFLUENCE" prefix naming both contributing strategies) —
  everything else about the send path is unchanged.
- **Outcome tracking requires one targeted change**, not a free ride.
  `signals/outcomes/tracker.py::track_open_signals` fetches candles via
  `fetch_candles(symbol, row["timeframe"], ...)` to check TP/SL —
  `fetch_candles` only understands real broker intervals (1m/5m/15m/1h/4h/
  1d), so `"confluence"` fails there, exactly like `"floor"`/`"bbma"` already
  silently fail on that call (caught, logged, skipped — those two rely
  instead on the separate realtime MT5-tick watcher to settle, which
  confluence has no equivalent of). Without a fix, a confluence signal would
  never settle — not TP, not SL, not even expiry, since the failed fetch
  causes an early `continue` that skips the expiry check too.

  **Fix:** when `row["timeframe"] == "confluence"`, fetch candles using
  `row["indicators"]["source_timeframe"]` (the real interval stored at
  creation, above) instead of the literal `"confluence"` string, both for
  the TP/SL check and for `bar_ms` precision. The registered `confluence`
  session's `max_open_days=14` still governs expiry. This is a small,
  targeted addition to `track_open_signals` (and, for consistency,
  `backfill_missing_outcome_charts`, which has the identical call) — not
  purely additive like the rest of this design, but there is no working
  alternative.
- `/track-record`, `/signals`, and the admin scans page pick it up
  automatically **if** they don't hard-filter to a known timeframe list.
  This needs an explicit check early in implementation, not an assumption —
  several places in the codebase key behavior off timeframe strings
  (`SESSION_SYMBOLS`, dedup queries, session clock helpers).

## Error handling

The confluence pass is wrapped in try/except at its single call site in
`engine.py::main()`, matching the existing pattern for paper trials and
chart backfill: a failure here must never block the three real sessions'
signals from delivering. Logged and continued, never raised.

## Implementation sketch

| File | Change |
|---|---|
| `signals/models.py` | Add `confluence` to `AUXILIARY_SESSIONS` |
| `signals/pipeline/confluence.py` | New: detection + signal construction |
| `signals/persistence/signals.py` | New query: open signals by symbol+direction, excluding a strategy/timeframe |
| `signals/pipeline/engine.py` | Call `confluence.detect_confluence(...)` after the session loop, wrapped in try/except |
| `signals/clients/telegram.py` | Confluence badge/formatting in `format_alert`/`format_caption` |
| `signals/outcomes/tracker.py` | Use `indicators["source_timeframe"]` instead of the literal row timeframe when fetching candles for a `confluence` row (both `track_open_signals` and `backfill_missing_outcome_charts`) |
| `web/src/lib/signals.ts`, `web/src/lib/track-record.ts` | Verify (and fix if needed) that a `confluence` timeframe isn't silently dropped or mis-grouped |
| `tests/core/test_confluence.py` | New: matching logic + one engine-level integration test |

## Testing

- Different-strategy requirement is enforced (same-strategy-different-timeframe
  does not trigger).
- Direction must match; opposite-direction open signals are ignored.
- Shadow rows and existing `confluence` rows are excluded from the "others"
  query.
- The one-open-confluence-per-symbol guard prevents duplicate emission while
  one is still open.
- Engine-level test: two strategies confirm (in the same run or across two
  separate runs) → exactly one confluence signal is created, with the
  correct `confluence_of` tag and copied levels.
- A forced exception inside the confluence pass does not prevent the
  session loop's own signals from being stored/delivered.

## Risks

- **Shared expiry window.** All confluence signals use one `max_open_days`
  (14, matching swing) regardless of which session actually triggered them.
  A confluence signal triggered by a 5m `ict_fvg` setup keeps a 14-day
  expiry even though 5m setups are normally scoped to 1 day. This is an
  accepted v1 simplification — the signal will usually close on its own
  TP/SL well before 14 days regardless.
- **Web read-path assumptions.** As noted above, several read paths may key
  off a known timeframe set. Must be checked, not assumed, before shipping.
- **Rare in practice.** With only two of three sessions overlapping on any
  given symbol at a time (in expectation), confluence events may be
  infrequent — this is a real trade-off of requiring genuinely independent
  strategies rather than a looser definition.
- **Strategy tag reliability — verified.** Detection depends on
  `indicators["strategy"]` being set on every stored signal from all three
  sessions. Confirmed directly in each detector: `msnr/detector.py:120`,
  `cloud_mss/detector.py:79`, and `ict_fvg/detector.py:180` all set it
  explicitly.

## Out of scope (v1)

- Auxiliary sessions (`xau_scalp`, `war_room`, `bbma`) as confluence
  contributors.
- Blended/averaged entry-stop levels across contributors.
- Position-size or risk-multiplier suggestions tied to confluence.
- Any change to the three main sessions' own detection, confirmation, or
  delivery logic — confluence is purely additive.
