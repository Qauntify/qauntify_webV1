# Multi-Level Take-Profit (TP1/TP2/TP3)

## Problem

Every signal currently carries one take-profit level (`entry ± 2.0R`). The user
wants three staged targets — TP1, TP2, TP3 — so a signal's progress toward its
full target is visible and notified as it happens, not just the final
win/loss.

## Decisions

- **TP levels**: fixed R-multiples off the existing entry/stop distance —
  TP1 = 1.0R, TP2 = 2.0R (matches today's only target, so historical stats
  stay comparable), TP3 = 3.0R.
- **No simulated position sizing**: this is an alert service, not an executed
  trade. TP1/TP2/TP3 are price milestones to track and notify on — no partial
  P&L math per level.
- **Stop-loss stays fixed** at the original level for the life of the trade —
  no breakeven move after TP1/TP2. A signal can go `tp1_hit` and later still
  end in `sl_hit`.
- **`status` is the live state machine position**: `open` → `tp1_hit` →
  `tp2_hit` → `tp3_hit` (terminal win), or → `sl_hit` (terminal loss) from any
  point, or → `expired`. `tp1_hit`/`tp2_hit` are non-terminal — the signal
  keeps being polled for the next level or a stop-out.
- **Per-level timestamps persist independently of `status`**: `tp1_hit_at`,
  `tp2_hit_at`, `tp3_hit_at` are nullable columns that, once set, are never
  cleared — even if the trade later resolves as `sl_hit`, the fact that TP1
  was reached first stays on the row.
- **Terminal full-win state is named `tp3_hit`** (not the old `tp_hit`) for
  naming consistency with `tp1_hit`/`tp2_hit`. Zero existing rows use
  `tp_hit`, so no data migration is needed — the check constraint just drops
  that value and adds the new ones.
- **Notification channel**: Telegram only — the only channel this codebase
  has. One alert per newly-crossed level, in order.

## Data model (`supabase/schema.sql`)

- Drop `take_profit`; add `take_profit_1`, `take_profit_2`, `take_profit_3`
  (`double precision not null`).
- Add `tp1_hit_at`, `tp2_hit_at`, `tp3_hit_at` (`timestamptz`, nullable).
- Widen `signals_status_check` to
  `status in ('open','tp1_hit','tp2_hit','tp3_hit','sl_hit','expired')`.
- `closed_at` is stamped only on terminal states (`tp3_hit`/`sl_hit`/
  `expired`).
- `signals_status_idx` (the "still needs polling" partial index) covers
  `status in ('open','tp1_hit','tp2_hit')`.
- `get_signal_stats()`: the win filter moves from `status = 'tp_hit'` to
  `status = 'tp3_hit'`; the JSON key stays `tp_hits` so the frontend RPC
  contract doesn't change.

## Signal generation (`signals/models.py`, both detectors)

- `ema_cross/detector.py` and `ict_smc/detector.py` each currently define
  their own `RISK_REWARD = 2.0`. Centralize `TP1_R = 1.0`, `TP2_R = 2.0`,
  `TP3_R = 3.0` as shared constants in `signals/models.py` and have both
  detectors compute all three levels from entry/stop, removing the
  duplicated constant.
- `CandidateSetup` and `Signal` dataclasses: `take_profit` field replaced by
  `take_profit_1`, `take_profit_2`, `take_profit_3`.
- `signals/composer.py` prompt building (`build_messages`) shows all three
  levels to the LLM instead of one.

## Outcome tracking (`signals/outcome_tracker.py`)

- `list_open_signals` (in `signals/storage.py`) broadens its filter to
  `status=in.(open,tp1_hit,tp2_hit)` and selects the new TP/hit-timestamp
  columns.
- `check_outcome` is rewritten to walk a signal's candles chronologically
  from `created_at`. For each candle, in order:
  1. If SL not yet hit and the candle's range reaches the stop, mark
     `sl_hit` and stop evaluating further candles for this signal (stop wins
     on a same-candle tie with a TP level — same conservative rule as
     today).
  2. Otherwise check each *unhit* TP level in ascending order (1, 2, 3). A
     single candle can cross more than one unhit level (fast move between
     engine polls) — all crossed levels are recorded from that candle.
  3. Continue to the next candle for any levels still unhit.
  Returns the ordered list of newly-crossed events for this run, e.g.
  `["tp1_hit", "tp2_hit"]` or `["sl_hit"]`.
- `track_open_signals` applies each event in order: PATCHes `status` plus the
  specific `tpN_hit_at` (and `closed_at` only when the event is terminal),
  and fires one Telegram alert per newly-crossed level.
- Expiry (`max_open_days`) logic is unchanged, now also reachable from
  `tp1_hit`/`tp2_hit` (a signal that stalls after TP1 without reaching TP2/
  TP3/SL still expires on schedule).

## Notifications (`signals/telegram_client.py`)

- New non-terminal alert: `🎯 TP1 HIT — BTCUSDT LONG (running to TP2)` (and
  the equivalent for TP2 → TP3).
- Existing terminal outcome alert (`format_outcome_alert`) is reused for
  `tp3_hit` and `sl_hit`, updated to say "TP3 HIT" instead of the generic
  "TP HIT".

## Frontend (`web/src/lib/signals.ts`, `SignalsGrid.tsx`, `TradeTicket.tsx`)

- `SignalStatus` type: `"open" | "tp1_hit" | "tp2_hit" | "tp3_hit" |
  "sl_hit" | "expired"`.
- `Signal.takeProfit` → `takeProfit1`, `takeProfit2`, `takeProfit3`;
  `parseRow`/`SignalRow` updated for the new DB column names.
- `StatusPill` (`SignalsGrid.tsx`) gets a distinct "running" treatment for
  `tp1_hit`/`tp2_hit` alongside its existing terminal win/loss/expired
  pills.
- `TradeTicket.tsx` shows three TP price rows instead of one.
- PnL calendar / stats (`DailyPnLCalendar.tsx`, `getDailyPnLStats`) only
  count terminal states (`tp3_hit`/`sl_hit`/`expired`) toward realized P&L —
  `tp1_hit`/`tp2_hit` don't affect win-rate or PnL math, per the "no
  simulated position sizing" decision.

## Testing

- `tests/test_outcome.py`, `tests/test_composer.py`,
  `web/src/lib/signals.test.ts`, `SignalsGrid.test.tsx` all assume the old
  single-TP shape and need updating alongside the implementation.
- New coverage needed: multi-level sequential hits within one polling run,
  a level hit followed later by `sl_hit`, and expiry from a `tp1_hit`/
  `tp2_hit` state.

## Out of scope

- Web push / browser notifications (no such infra exists; Telegram is the
  only channel today).
- Breakeven stop-loss movement after TP1/TP2.
- Simulated partial position sizing / per-level P&L attribution.
