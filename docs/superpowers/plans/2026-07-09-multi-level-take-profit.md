# Multi-Level Take-Profit (TP1/TP2/TP3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every signal's single take-profit level with three staged
targets (TP1 = 1R, TP2 = 2R, TP3 = 3R), track them as a progressive state
machine (`open` → `tp1_hit` → `tp2_hit` → `tp3_hit`, or → `sl_hit` from any
point), and send a Telegram alert the moment each level is crossed.

**Architecture:** A DB migration adds `take_profit_1/2/3` (replacing
`take_profit`) plus `tp1_hit_at`/`tp2_hit_at` to `signals` (same rename on
`ai_events`, which logs the same setup shape). Both detectors compute all
three levels from shared R-multiple constants. `outcome_tracker.check_outcome`
walks a signal's candles and returns an *ordered list* of newly-crossed
events instead of a single outcome string; `track_open_signals` applies each
event — PATCHing status/timestamps and firing one Telegram alert per level —
and only returns terminal events (`tp3_hit`/`sl_hit`/`expired`) to the
caller, since that's what the engine-run summary already expects. The
frontend mirrors the same rename across types, status pills, and price
displays.

**Tech Stack:** Python (signals engine, pytest), Next.js/TypeScript (web
dashboard, vitest), Supabase/Postgres (schema.sql, PostgREST).

**Spec:** `docs/superpowers/specs/2026-07-09-multi-level-take-profit-design.md`

**Scope note:** The spec covered the `signals` table end-to-end. Writing this
plan surfaced that `CandidateSetup`/`Signal`/`NoSignalReport` — and the
`ai_events` table that logs them — carry the same single `take_profit` field
today, so this plan also renames it there for consistency (same decision,
wider blast radius: nothing new to decide, just more files that reference the
same field). It also drops the separately-planned `tp3_hit_at` column: TP3
is always a terminal event, and `closed_at` + `status='tp3_hit'` already
captures exactly that — a dedicated timestamp would just duplicate it.

---

## File map

| File | Change |
|---|---|
| `supabase/schema.sql` | `signals`/`ai_events`: `take_profit`→`take_profit_1/2/3`, add `tp1_hit_at`/`tp2_hit_at`, widen status check/index, update `get_signal_stats()` |
| `signals/models.py` | `TP1_R`/`TP2_R`/`TP3_R` constants; `CandidateSetup`/`Signal`/`NoSignalReport` field rename |
| `signals/strategies/ema_cross/detector.py` | Compute 3 TP levels |
| `signals/strategies/ict_smc/detector.py` | Compute 3 TP levels |
| `signals/composer.py` | LLM prompt shows 3 TP levels |
| `signals/storage.py` | `list_open_signals` broadens + selects `status`; new `mark_tp_level`; `list_closed_signals` filter/select update |
| `signals/outcome_tracker.py` | `check_outcome` returns ordered event list; `track_open_signals` applies each event + alerts |
| `signals/telegram_client.py` | `format_alert`/`format_no_signal_alert` show 3 TPs; new `format_tp_level_alert`/`send_tp_level_alert`; `format_outcome_alert` says "TP3 HIT" |
| `signals/run.py` | `_log_ai_event` + call sites, `NoSignalReport` construction, `OUTCOME_LABELS` |
| `signals/calibration.py` | `_r_multiple`/`_bucket_stats` use `take_profit_3`/`tp3_hit` |
| `tests/test_setup_detector.py`, `test_ict_detector.py`, `test_composer.py`, `test_storage.py`, `test_outcome.py`, `test_telegram.py`, `test_pipeline.py`, `test_calibration.py` | Updated fixtures/assertions for the new shape |
| `web/src/lib/signals.ts` | Types, `parseRow`, `parseStatus`, `getDailyPnLStats` |
| `web/src/components/dashboard/SignalsGrid.tsx` | `StatusPill`, `riskReward`, price cells (card + modal) |
| `web/src/components/shared/TradeTicket.tsx` | `StatusBadge`, `riskReward`, price cells |
| `web/src/lib/supabase/admin.ts` | `AiEvent` type + `mapAiEventRows` |
| `web/src/app/admin/ai/responses/page.tsx` | Display 3 TPs |
| `web/src/components/landing/Hero.tsx` | Sample signal fixture |
| `web/src/lib/signals.test.ts`, `SignalsGrid.test.tsx`, `TradeTicket.test.tsx` | Updated fixtures/assertions |

**Reference R-multiples used throughout** (entry=100, stop=98, risk=2, long):
TP1=102, TP2=104 (matches today's only target), TP3=106. Short mirrors with
minus signs.

**Before starting:** `web/AGENTS.md` warns this project's Next.js build may
differ from training-data assumptions. None of the frontend tasks below use
new Next.js APIs (only type/JSX edits to existing client components), so no
doc lookup is needed — flagging this so whoever executes Tasks 20–24 doesn't
skip it if they *do* end up touching routing/server-component conventions.

---

### Task 1: Database migration

**Files:**
- Modify: `supabase/schema.sql`

- [ ] **Step 1: Replace the `signals` table's `take_profit` column**

In `supabase/schema.sql`, find the initial `create table if not exists public.signals` block and change:

```sql
    take_profit double precision not null,
```
to:
```sql
    take_profit_1 double precision not null,
    take_profit_2 double precision not null,
    take_profit_3 double precision not null,
```

- [ ] **Step 2: Add a migration block for existing installs**

Immediately after the `signals_created_at_idx` index (right before the
"Outcome tracking" comment block), insert:

```sql
-- Multi-level take-profit: three staged targets instead of one. Existing
-- rows already have entry/stop_loss (the risk distance) and the old single
-- take_profit (which was always entry ± 2×risk), so backfill computes
-- TP1/TP3 from that same risk distance instead of leaving them null.
alter table public.signals add column if not exists take_profit_1 double precision;
alter table public.signals add column if not exists take_profit_2 double precision;
alter table public.signals add column if not exists take_profit_3 double precision;

update public.signals
set
    take_profit_2 = coalesce(take_profit_2, take_profit),
    take_profit_1 = coalesce(take_profit_1,
        case when direction = 'long'
            then entry + (entry - stop_loss)
            else entry - (stop_loss - entry)
        end),
    take_profit_3 = coalesce(take_profit_3,
        case when direction = 'long'
            then entry + 3 * (entry - stop_loss)
            else entry - 3 * (stop_loss - entry)
        end)
where take_profit_1 is null or take_profit_2 is null or take_profit_3 is null;

alter table public.signals alter column take_profit_1 set not null;
alter table public.signals alter column take_profit_2 set not null;
alter table public.signals alter column take_profit_3 set not null;

alter table public.signals drop column if exists take_profit;
```

- [ ] **Step 3: Add the per-level hit timestamps and widen the status check**

Find this existing block:
```sql
alter table public.signals
    add column if not exists status text not null default 'open'
        check (status in ('open', 'tp_hit', 'sl_hit'));
alter table public.signals
    add column if not exists closed_at timestamptz;

-- Existing installs: widen the status check to allow 'expired'.
alter table public.signals drop constraint if exists signals_status_check;
alter table public.signals add constraint signals_status_check
    check (status in ('open', 'tp_hit', 'sl_hit', 'expired'));

create index if not exists signals_status_idx
    on public.signals (status)
    where status = 'open';
```

Replace the last three statements (from the `-- Existing installs` comment
onward) with:

```sql
-- TP1/TP2 are non-terminal — the signal keeps being tracked until it
-- reaches TP3 or the stop, or expires. tp3_hit replaces the old tp_hit as
-- the terminal full-win state; tp1_hit_at/tp2_hit_at persist independently
-- of `status` so a trade that later ends in sl_hit still shows it reached
-- TP1/TP2 first.
alter table public.signals
    add column if not exists tp1_hit_at timestamptz;
alter table public.signals
    add column if not exists tp2_hit_at timestamptz;

alter table public.signals drop constraint if exists signals_status_check;
alter table public.signals add constraint signals_status_check
    check (status in ('open', 'tp1_hit', 'tp2_hit', 'tp3_hit', 'sl_hit', 'expired'));

drop index if exists signals_status_idx;
create index if not exists signals_status_idx
    on public.signals (status)
    where status in ('open', 'tp1_hit', 'tp2_hit');
```

- [ ] **Step 4: Update `get_signal_stats()`**

Find:
```sql
        count(*) filter (where status = 'tp_hit')::int as tp_hits,
```
Replace with:
```sql
        count(*) filter (where status = 'tp3_hit')::int as tp_hits,
```

- [ ] **Step 5: Rename `take_profit` on `ai_events` the same way**

Find the `ai_events` table definition:
```sql
create table if not exists public.ai_events (
    id uuid primary key,
    symbol text not null,
    timeframe text not null,
    kind text not null check (kind in ('confirm', 'reject', 'no_setup')),
    direction text null check (direction in ('long', 'short')),
    entry double precision null,
    stop_loss double precision null,
    take_profit double precision null,
    confidence integer null check (confidence between 0 and 100),
    rationale text not null,
    indicators jsonb not null,
    news_headlines jsonb not null default '[]'::jsonb,
    created_at timestamptz not null
);
```
Replace the `take_profit` line with:
```sql
    take_profit_1 double precision null,
    take_profit_2 double precision null,
    take_profit_3 double precision null,
```

Then, immediately after the `create table` statement (before the
`ai_events_created_at_idx` index), insert:
```sql
-- Existing installs: same take_profit -> take_profit_1/2/3 rename as
-- public.signals. ai_events is an audit log, not a financial record, so
-- unlike signals this only carries the old value forward into
-- take_profit_2 (its historical meaning) rather than deriving TP1/TP3 —
-- pre-migration rows simply show those as null.
alter table public.ai_events add column if not exists take_profit_1 double precision;
alter table public.ai_events add column if not exists take_profit_2 double precision;
alter table public.ai_events add column if not exists take_profit_3 double precision;
update public.ai_events set take_profit_2 = coalesce(take_profit_2, take_profit)
    where take_profit_2 is null;
alter table public.ai_events drop column if exists take_profit;
```

- [ ] **Step 6: Commit**

```bash
git add supabase/schema.sql
git commit -m "$(cat <<'EOF'
Add multi-level take-profit columns to signals/ai_events schema

Replaces the single take_profit column with take_profit_1/2/3 and adds
tp1_hit_at/tp2_hit_at for tracking progressive TP hits.
EOF
)"
```

*(This SQL isn't run automatically — note in your PR/handoff that it needs to
be applied via the Supabase SQL Editor before the updated engine or frontend
is deployed, exactly like every other change in this file.)*

---

### Task 2: `signals/models.py` — TP constants and dataclass fields

**Files:**
- Modify: `signals/models.py`

- [ ] **Step 1: Add the shared R-multiple constants**

Near the top of `signals/models.py`, after the imports, add:

```python
# Shared by both detectors: fixed R-multiples off entry/stop distance.
# TP2 matches the engine's original (single-target) 2.0R behavior.
TP1_R = 1.0
TP2_R = 2.0
TP3_R = 3.0
```

- [ ] **Step 2: Update `CandidateSetup`**

Replace:
```python
@dataclass(frozen=True)
class CandidateSetup:
    symbol: str
    direction: str  # "long" | "short"
    entry: float
    stop_loss: float
    take_profit: float
    indicators: dict  # {"ema9":, "ema21":, "rsi":, "macd_hist":}
```
with:
```python
@dataclass(frozen=True)
class CandidateSetup:
    symbol: str
    direction: str  # "long" | "short"
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    indicators: dict  # {"ema9":, "ema21":, "rsi":, "macd_hist":}
```

- [ ] **Step 3: Update `NoSignalReport`**

Replace:
```python
    direction: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: int | None = None
```
(inside `NoSignalReport`) with:
```python
    direction: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    take_profit_3: float | None = None
    confidence: int | None = None
```

- [ ] **Step 4: Update `Signal` and `make_signal`**

Replace:
```python
@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    timeframe: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    confidence: int
    rationale: str
    indicators: dict
    news_headlines: list
    created_at: str
```
with:
```python
@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    timeframe: str
    direction: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    confidence: int
    rationale: str
    indicators: dict
    news_headlines: list
    created_at: str
```

Replace:
```python
def make_signal(setup: CandidateSetup, confirmation: Confirmation,
                headlines: list, timeframe: str = "1h") -> Signal:
    return Signal(
        id=str(uuid.uuid4()),
        symbol=setup.symbol,
        timeframe=timeframe,
        direction=setup.direction,
        entry=setup.entry,
        stop_loss=setup.stop_loss,
        take_profit=setup.take_profit,
        confidence=confirmation.confidence,
        rationale=confirmation.rationale,
        indicators=setup.indicators,
        news_headlines=list(headlines),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
```
with:
```python
def make_signal(setup: CandidateSetup, confirmation: Confirmation,
                headlines: list, timeframe: str = "1h") -> Signal:
    return Signal(
        id=str(uuid.uuid4()),
        symbol=setup.symbol,
        timeframe=timeframe,
        direction=setup.direction,
        entry=setup.entry,
        stop_loss=setup.stop_loss,
        take_profit_1=setup.take_profit_1,
        take_profit_2=setup.take_profit_2,
        take_profit_3=setup.take_profit_3,
        confidence=confirmation.confidence,
        rationale=confirmation.rationale,
        indicators=setup.indicators,
        news_headlines=list(headlines),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 5: Commit**

This file has no dedicated test module (it's exercised by every other
test file) — the rest of this plan's tasks are what verify it. Commit now
so the rename lands as one reviewable unit:

```bash
git add signals/models.py
git commit -m "$(cat <<'EOF'
Replace single take_profit with take_profit_1/2/3 in signal dataclasses

Adds shared TP1_R/TP2_R/TP3_R constants; downstream detectors, storage,
and telegram code are updated in following commits.
EOF
)"
```

*(This commit will not pass the test suite on its own — every consumer of
`.take_profit` breaks until Tasks 3–19 land. That's expected for a
same-day rename spread across bite-sized commits; run the full suite only
after Task 19.)*

---

### Task 3: `ema_cross` detector — compute 3 TP levels

**Files:**
- Modify: `signals/strategies/ema_cross/detector.py`
- Test: `tests/test_setup_detector.py`

- [ ] **Step 1: Update the failing assertions first**

In `tests/test_setup_detector.py`, replace:
```python
    # swing low = 99.0 (price 100 - low_offset 1), stop = 99 - 0.5*2 = 98
    assert setup.stop_loss == 98.0
    # risk = 2.0 → TP = 100 + 2*2 = 104
    assert setup.take_profit == 104.0
    assert setup.indicators["rsi"] == 55.0
```
with:
```python
    # swing low = 99.0 (price 100 - low_offset 1), stop = 99 - 0.5*2 = 98
    assert setup.stop_loss == 98.0
    # risk = entry(100) - stop(98) = 2.0
    assert setup.take_profit_1 == 102.0  # 1R
    assert setup.take_profit_2 == 104.0  # 2R
    assert setup.take_profit_3 == 106.0  # 3R
    assert setup.indicators["rsi"] == 55.0
```

And replace:
```python
    # swing high = 101.0, stop = 101 + 0.5*2 = 102, risk = 2 → TP = 96
    assert setup.stop_loss == 102.0
    assert setup.take_profit == 96.0
```
with:
```python
    # swing high = 101.0, stop = 101 + 0.5*2 = 102, risk = 2
    assert setup.stop_loss == 102.0
    assert setup.take_profit_1 == 98.0   # 1R
    assert setup.take_profit_2 == 96.0   # 2R
    assert setup.take_profit_3 == 94.0   # 3R
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_setup_detector.py -v`
Expected: FAIL — `AttributeError: 'CandidateSetup' object has no attribute 'take_profit_1'`

- [ ] **Step 3: Implement in the detector**

In `signals/strategies/ema_cross/detector.py`, change the import line:
```python
from signals.models import CandidateSetup
```
to:
```python
from signals.models import CandidateSetup, TP1_R, TP2_R, TP3_R
```

Remove the now-unused `RISK_REWARD = 2.0` line.

Replace:
```python
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr14[-1]
        if stop >= entry:
            return None
        take_profit = entry + RISK_REWARD * (entry - stop)
        return CandidateSetup(symbol, "long", entry, stop, take_profit, indicators)
```
with:
```python
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr14[-1]
        if stop >= entry:
            return None
        risk = entry - stop
        return CandidateSetup(
            symbol, "long", entry, stop,
            entry + TP1_R * risk, entry + TP2_R * risk, entry + TP3_R * risk,
            indicators,
        )
```

Replace:
```python
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr14[-1]
        if stop <= entry:
            return None
        take_profit = entry - RISK_REWARD * (stop - entry)
        return CandidateSetup(symbol, "short", entry, stop, take_profit, indicators)
```
with:
```python
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr14[-1]
        if stop <= entry:
            return None
        risk = stop - entry
        return CandidateSetup(
            symbol, "short", entry, stop,
            entry - TP1_R * risk, entry - TP2_R * risk, entry - TP3_R * risk,
            indicators,
        )
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_setup_detector.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/ema_cross/detector.py tests/test_setup_detector.py
git commit -m "$(cat <<'EOF'
Compute 3 TP levels in the EMA-cross detector

TP1/TP2/TP3 = entry ± 1R/2R/3R off the same stop distance used today.
EOF
)"
```

---

### Task 4: `ict_smc` detector — compute 3 TP levels

**Files:**
- Modify: `signals/strategies/ict_smc/detector.py`
- Test: `tests/test_ict_detector.py`

- [ ] **Step 1: Update the failing assertion first**

In `tests/test_ict_detector.py`, replace:
```python
    assert setup.stop_loss < setup.entry < setup.take_profit
```
with:
```python
    assert setup.stop_loss < setup.entry
    assert setup.entry < setup.take_profit_1 < setup.take_profit_2 < setup.take_profit_3
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_ict_detector.py -v`
Expected: FAIL — `AttributeError: 'CandidateSetup' object has no attribute 'take_profit_1'`

- [ ] **Step 3: Implement in the detector**

In `signals/strategies/ict_smc/detector.py`, change the import line:
```python
from signals.models import Candle, CandidateSetup
```
to:
```python
from signals.models import Candle, CandidateSetup, TP1_R, TP2_R, TP3_R
```

Remove the now-unused `RISK_REWARD = 2.0` line.

In the bullish branch, replace:
```python
        stop = bar.low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            continue
        take_profit = entry + RISK_REWARD * (entry - stop)
        indicators = {
            "strategy": "ict_smc",
            "structure": "bullish_choch",
            "sweep_level": swing_low,
            "choch_level": swing_high,
            "sweep_low": bar.low,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "long", entry, stop, take_profit, indicators,
        )
```
with:
```python
        stop = bar.low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            continue
        risk = entry - stop
        indicators = {
            "strategy": "ict_smc",
            "structure": "bullish_choch",
            "sweep_level": swing_low,
            "choch_level": swing_high,
            "sweep_low": bar.low,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "long", entry, stop,
            entry + TP1_R * risk, entry + TP2_R * risk, entry + TP3_R * risk,
            indicators,
        )
```

In the bearish branch, replace:
```python
        stop = bar.high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            continue
        take_profit = entry - RISK_REWARD * (stop - entry)
        indicators = {
            "strategy": "ict_smc",
            "structure": "bearish_choch",
            "sweep_level": swing_high,
            "choch_level": swing_low,
            "sweep_high": bar.high,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "short", entry, stop, take_profit, indicators,
        )
```
with:
```python
        stop = bar.high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            continue
        risk = stop - entry
        indicators = {
            "strategy": "ict_smc",
            "structure": "bearish_choch",
            "sweep_level": swing_high,
            "choch_level": swing_low,
            "sweep_high": bar.high,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "short", entry, stop,
            entry - TP1_R * risk, entry - TP2_R * risk, entry - TP3_R * risk,
            indicators,
        )
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_ict_detector.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/ict_smc/detector.py tests/test_ict_detector.py
git commit -m "Compute 3 TP levels in the ICT/SMC detector"
```

---

### Task 5: `signals/composer.py` — show 3 TP levels to the LLM

**Files:**
- Modify: `signals/composer.py`
- Test: `tests/test_composer.py`

- [ ] **Step 1: Update fixtures and add a new assertion**

In `tests/test_composer.py`, replace the `SETUP` fixture:
```python
SETUP = CandidateSetup(
    symbol="BTCUSDT",
    direction="long",
    entry=100.0,
    stop_loss=98.0,
    take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)
```
with:
```python
SETUP = CandidateSetup(
    symbol="BTCUSDT",
    direction="long",
    entry=100.0,
    stop_loss=98.0,
    take_profit_1=102.0,
    take_profit_2=104.0,
    take_profit_3=106.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)
```

Replace the second fixture inside `test_build_messages_includes_adx_and_htf_trend_when_present`:
```python
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0,
                    "macd_hist": 0.5, "adx": 27.3, "htf_trend": "up"},
    )
```
with:
```python
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
        take_profit_3=106.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0,
                    "macd_hist": 0.5, "adx": 27.3, "htf_trend": "up"},
    )
```

Add a new test, after `test_build_messages_includes_setup_and_news`:
```python
def test_build_messages_includes_all_three_tp_levels():
    user_content = build_messages(SETUP, HEADLINES)[1]["content"]
    assert "Take profit 1: 102.0" in user_content
    assert "Take profit 2: 104.0" in user_content
    assert "Take profit 3: 106.0" in user_content
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_composer.py -v`
Expected: FAIL — `TypeError: CandidateSetup.__init__() got an unexpected keyword argument 'take_profit'` (fixture) and the new test errors with `AttributeError`.

- [ ] **Step 3: Implement in composer.py**

In `signals/composer.py`, inside `build_messages`, replace:
```python
    user_content = (
        f"Candidate setup:\n"
        f"{strategy_line}"
        f"- Symbol: {setup.symbol}\n"
        f"- Direction: {setup.direction}\n"
        f"- Entry: {setup.entry}\n"
        f"- Stop loss: {setup.stop_loss}\n"
        f"- Take profit: {setup.take_profit}\n"
        f"- Context: {_format_indicators(strategy, ind)}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
```
with:
```python
    user_content = (
        f"Candidate setup:\n"
        f"{strategy_line}"
        f"- Symbol: {setup.symbol}\n"
        f"- Direction: {setup.direction}\n"
        f"- Entry: {setup.entry}\n"
        f"- Stop loss: {setup.stop_loss}\n"
        f"- Take profit 1: {setup.take_profit_1}\n"
        f"- Take profit 2: {setup.take_profit_2}\n"
        f"- Take profit 3: {setup.take_profit_3}\n"
        f"- Context: {_format_indicators(strategy, ind)}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_composer.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/composer.py tests/test_composer.py
git commit -m "Show all three TP levels in the LLM confirmation prompt"
```

---

### Task 6: `signals/storage.py` — broaden open-signal tracking, add `mark_tp_level`

**Files:**
- Modify: `signals/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Update fixtures and assertions first**

In `tests/test_storage.py`, replace the `_signal()` fixture:
```python
def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])
```
with:
```python
def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
        take_profit_3=106.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])
```

Replace:
```python
def test_list_open_signals_selects_timeframe():
    session = FakeGetSession(payload=[])
    from signals.storage import list_open_signals

    list_open_signals("https://abc.supabase.co", "key", session=session)
    assert "timeframe" in session.last_url
```
with:
```python
def test_list_open_signals_selects_timeframe():
    session = FakeGetSession(payload=[])
    from signals.storage import list_open_signals

    list_open_signals("https://abc.supabase.co", "key", session=session)
    assert "timeframe" in session.last_url


def test_list_open_signals_queries_all_non_terminal_statuses():
    session = FakeGetSession(payload=[])
    from signals.storage import list_open_signals

    list_open_signals("https://abc.supabase.co", "key", session=session)
    assert "status=in.(open,tp1_hit,tp2_hit)" in session.last_url
    assert "status" in session.last_url.split("select=")[1]  # status is selected too
```

Replace:
```python
def test_list_closed_signals_filters_terminal_statuses():
    from signals.storage import list_closed_signals

    session = FakeGetSession(payload=[
        {"symbol": "BTCUSDT", "status": "tp_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ])
    rows = list_closed_signals("https://abc.supabase.co", "key", session=session)

    assert rows == [
        {"symbol": "BTCUSDT", "status": "tp_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ]
    assert "status=in.(tp_hit,sl_hit,expired)" in session.last_url
    assert session.last_headers["apikey"] == "key"
```
with:
```python
def test_list_closed_signals_filters_terminal_statuses():
    from signals.storage import list_closed_signals

    session = FakeGetSession(payload=[
        {"symbol": "BTCUSDT", "status": "tp3_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ])
    rows = list_closed_signals("https://abc.supabase.co", "key", session=session)

    assert rows == [
        {"symbol": "BTCUSDT", "status": "tp3_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ]
    assert "status=in.(tp3_hit,sl_hit,expired)" in session.last_url
    assert session.last_headers["apikey"] == "key"
```

Add a new test near `test_close_signal_patches_status_and_closed_at`:
```python
def test_mark_tp_level_patches_status_and_level_timestamp():
    from signals.storage import mark_tp_level

    session = FakeSession()
    mark_tp_level("sig-1", 1, "tp1_hit", "2026-07-07T13:00:00+00:00",
                  "https://abc.supabase.co", "key", session=session)
    assert session.last_method == "PATCH"
    assert "id=eq.sig-1" in session.last_url
    assert session.last_json == {
        "status": "tp1_hit",
        "tp1_hit_at": "2026-07-07T13:00:00+00:00",
    }


def test_mark_tp_level_raises_on_http_error():
    from signals.storage import mark_tp_level

    with pytest.raises(RuntimeError):
        mark_tp_level("sig-1", 2, "tp2_hit", "t", "https://abc.supabase.co",
                      "key", session=FakeSession(status=500))
```

No top-level import changes are needed: this file's established convention
(see `test_list_open_signals_selects_timeframe`, `test_latest_signal_filters_by_timeframe`,
etc. above) is a local `from signals.storage import <name>` inside each test
function rather than one growing top-level import list — the two new tests
follow that same pattern.

- [ ] **Step 2: Run to confirm the new/changed tests fail**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'mark_tp_level'` and the status-filter assertions fail against the old `status=eq.open` query.

- [ ] **Step 3: Implement in storage.py**

In `signals/storage.py`, replace `list_open_signals`:
```python
def list_open_signals(supabase_url: str, service_key: str, session=None):
    """All signals with status 'open' (oldest first) as raw dicts.
    Raises on any failure — including the status column not existing yet."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=eq.open"
        "&select=id,symbol,timeframe,direction,entry,stop_loss,take_profit,created_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
```
with:
```python
def list_open_signals(supabase_url: str, service_key: str, session=None):
    """Every signal still being tracked — status 'open', 'tp1_hit', or
    'tp2_hit' (oldest first) — as raw dicts. `status` is selected so
    check_outcome knows which levels are already hit when resuming.
    Raises on any failure — including the status column not existing yet."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=in.(open,tp1_hit,tp2_hit)"
        "&select=id,symbol,timeframe,direction,entry,stop_loss,"
        "take_profit_1,take_profit_2,take_profit_3,status,created_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
```

Immediately after `close_signal`, add:
```python
def mark_tp_level(signal_id: str, level: int, status: str, hit_at: str,
                  supabase_url: str, service_key: str, session=None) -> None:
    """Patch a non-terminal TP1/TP2 hit: advances `status` and stamps that
    level's tpN_hit_at, leaving closed_at untouched — the signal is still
    running toward the next level. Raises on failure so callers can retry."""
    session = session or requests.Session()
    response = session.patch(
        f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"status": status, f"tp{level}_hit_at": hit_at},
        timeout=15,
    )
    response.raise_for_status()
```

Replace `list_closed_signals`:
```python
def list_closed_signals(supabase_url: str, service_key: str, session=None):
    """Every signal that has reached a terminal status (tp_hit/sl_hit/
    expired), for calibration reporting — win rate and expectancy can only
    be computed once an outcome is known. Raises on any failure."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=in.(tp_hit,sl_hit,expired)"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "confidence,status,indicators,created_at,closed_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
```
with:
```python
def list_closed_signals(supabase_url: str, service_key: str, session=None):
    """Every signal that has reached a terminal status (tp3_hit/sl_hit/
    expired), for calibration reporting — win rate and expectancy can only
    be computed once an outcome is known. Raises on any failure."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=in.(tp3_hit,sl_hit,expired)"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit_1,"
        "take_profit_2,take_profit_3,"
        "confidence,status,indicators,created_at,closed_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/storage.py tests/test_storage.py
git commit -m "$(cat <<'EOF'
Track tp1_hit/tp2_hit as open signals; add mark_tp_level

list_open_signals now selects status and covers tp1_hit/tp2_hit, not
just open. list_closed_signals filters on tp3_hit instead of tp_hit.
EOF
)"
```

---

### Task 7: `signals/outcome_tracker.py` — multi-level outcome state machine

This is the core rewrite. `check_outcome` returns an **ordered list of newly
crossed events** (e.g. `["tp1_hit", "tp2_hit"]`, `["sl_hit"]`, or `[]`)
instead of a single string. `track_open_signals` applies each event via
`mark_tp_level` (non-terminal) or `close_signal` (terminal), fires the
matching Telegram alert, and returns only terminal events — matching what
`run.py`'s engine-summary loop already expects.

**Files:**
- Modify: `signals/outcome_tracker.py`
- Modify: `signals/telegram_client.py` (new `send_tp_level_alert` — implemented in Task 8, but referenced here; do Task 8's Step 3 first if executing out of order)
- Test: `tests/test_outcome.py`

- [ ] **Step 1: Rewrite `tests/test_outcome.py`'s fixtures and `check_outcome` tests**

Replace the whole top section, from `NOW = ...` through `test_first_hit_wins_across_candles`, with:

```python
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def _row(direction="long", entry=100.0, stop=95.0, tp1=102.0, tp2=105.0,
         tp3=110.0, status="open", created=NOW):
    return {
        "id": "sig-1",
        "symbol": "BTCUSDT",
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
        "status": status,
        "created_at": created.isoformat(),
    }


def _candle(hours_after=1, high=105.0, low=99.0):
    open_time = int((NOW + timedelta(hours=hours_after)).timestamp() * 1000)
    return Candle(open_time=open_time, open=100.0, high=high, low=low,
                  close=100.0, volume=1.0)


def test_long_tp1_hit():
    assert check_outcome(_row(), [_candle(high=103.0)]) == ["tp1_hit"]


def test_long_tp1_and_tp2_hit_in_one_candle():
    assert check_outcome(_row(), [_candle(high=106.0)]) == ["tp1_hit", "tp2_hit"]


def test_long_all_three_tps_hit_in_one_candle():
    assert check_outcome(_row(), [_candle(high=111.0)]) == [
        "tp1_hit", "tp2_hit", "tp3_hit",
    ]


def test_long_sl_hit():
    assert check_outcome(_row(), [_candle(low=94.0)]) == ["sl_hit"]


def test_short_tp1_hit():
    row = _row(direction="short", stop=105.0, tp1=98.0, tp2=95.0, tp3=90.0)
    assert check_outcome(row, [_candle(low=97.0)]) == ["tp1_hit"]


def test_short_sl_hit():
    row = _row(direction="short", stop=105.0, tp1=98.0, tp2=95.0, tp3=90.0)
    assert check_outcome(row, [_candle(high=106.0)]) == ["sl_hit"]


def test_still_open_when_no_level_reached():
    assert check_outcome(_row(), [_candle(high=101.0, low=99.0)]) == []


def test_candle_spanning_stop_and_unhit_tp_counts_as_stop():
    # Stop wins on a same-candle tie — no TP is awarded from that candle.
    assert check_outcome(_row(), [_candle(high=111.0, low=94.0)]) == ["sl_hit"]


def test_candles_before_creation_are_ignored():
    old_candle = _candle(hours_after=-2, high=120.0, low=90.0)
    assert check_outcome(_row(), [old_candle]) == []


def test_resumes_from_already_hit_level():
    # tp1_hit was recorded on a previous run — only tp2 is new this time.
    row = _row(status="tp1_hit")
    assert check_outcome(row, [_candle(high=106.0)]) == ["tp2_hit"]


def test_tp1_then_later_sl_preserves_tp1_progress():
    row = _row()
    candles = [_candle(hours_after=1, high=103.0), _candle(hours_after=2, low=94.0)]
    assert check_outcome(row, candles) == ["tp1_hit", "sl_hit"]


def test_stops_evaluating_once_terminal_within_one_call():
    # sl_hit is terminal — a later candle reaching a TP must not also fire.
    row = _row()
    candles = [
        _candle(hours_after=1, low=94.0),
        _candle(hours_after=2, high=111.0),
    ]
    assert check_outcome(row, candles) == ["sl_hit"]
```

- [ ] **Step 2: Run to confirm the `check_outcome` tests fail**

Run: `python -m pytest tests/test_outcome.py -v`
Expected: FAIL — old `check_outcome` returns a string, not a list, and the
`_row` fixture no longer has `take_profit`.

- [ ] **Step 3: Rewrite `check_outcome`**

In `signals/outcome_tracker.py`, replace:
```python
def check_outcome(signal_row: dict, candles: list) -> str | None:
    """First outcome reached by candles fully after the signal's creation:
    'tp_hit', 'sl_hit', or None while still open.

    Only candles that OPENED at/after created_at count, so price movement
    from before the signal existed can never close it. When one candle
    spans both levels, the stop wins — the conservative read.
    """
    created_ms = datetime.fromisoformat(signal_row["created_at"]).timestamp() * 1000
    is_long = signal_row["direction"] == "long"
    stop = signal_row["stop_loss"]
    target = signal_row["take_profit"]
    for candle in candles:
        if candle.open_time < created_ms:
            continue
        if is_long:
            if candle.low <= stop:
                return "sl_hit"
            if candle.high >= target:
                return "tp_hit"
        else:
            if candle.high >= stop:
                return "sl_hit"
            if candle.low <= target:
                return "tp_hit"
    return None
```
with:
```python
# Maps a signal's current `status` to how many TP levels are already
# confirmed hit — check_outcome only reports levels beyond this.
_LEVELS_ALREADY_HIT = {"open": 0, "tp1_hit": 1, "tp2_hit": 2}


def check_outcome(signal_row: dict, candles: list) -> list[str]:
    """Ordered list of newly-crossed events since signal_row's current
    status: any of "tp1_hit", "tp2_hit", "tp3_hit" (in order), or
    "sl_hit" — empty while nothing new has happened.

    Only candles that OPENED at/after created_at count, so price movement
    from before the signal existed can never close it. Within one candle,
    the stop is checked before any unhit TP level — when a single candle
    spans both, the stop wins (the conservative read) and no TP from that
    candle is recorded, even if an earlier candle in this same call already
    confirmed one (that earlier event stays in the returned list). A candle
    that clears more than one unhit TP at once (a fast move between engine
    polls) reports all of them. Processing stops the moment a terminal
    event (tp3_hit or sl_hit) is recorded.
    """
    created_ms = datetime.fromisoformat(signal_row["created_at"]).timestamp() * 1000
    is_long = signal_row["direction"] == "long"
    stop = signal_row["stop_loss"]
    targets = [signal_row["take_profit_1"], signal_row["take_profit_2"],
               signal_row["take_profit_3"]]
    hit = _LEVELS_ALREADY_HIT.get(signal_row["status"], 0)

    events: list[str] = []
    for candle in candles:
        if candle.open_time < created_ms:
            continue
        if hit == 3:
            break
        stop_touched = candle.low <= stop if is_long else candle.high >= stop
        if stop_touched:
            events.append("sl_hit")
            return events
        while hit < 3:
            target = targets[hit]
            reached = candle.high >= target if is_long else candle.low <= target
            if not reached:
                break
            hit += 1
            events.append(f"tp{hit}_hit")
    return events
```

- [ ] **Step 4: Run to confirm the `check_outcome` tests pass**

Run: `python -m pytest tests/test_outcome.py -v -k "not track"`
Expected: PASS for all `check_outcome`-only tests (the `track_open_signals`
tests still fail — that's Steps 5–8).

- [ ] **Step 5: Rewrite the `track_open_signals` tests**

Replace every occurrence of `"take_profit": 110.0,` (in `_live_row`) with:
```python
        "take_profit_1": 102.0,
        "take_profit_2": 105.0,
        "take_profit_3": 110.0,
```

Replace `_row(direction=..., entry=..., stop=..., target=...)` usage in
`test_format_outcome_alert_long_tp` and `test_format_outcome_alert_short_sl_is_negative`:
```python
def test_format_outcome_alert_long_tp():
    text = format_outcome_alert(_row(), "tp_hit")
    assert "TP HIT BTCUSDT" in text
    assert "LONG +10.00%" in text
    assert "Entry 100 → 110" in text


def test_format_outcome_alert_short_sl_is_negative():
    row = _row(direction="short", stop=105.0, target=90.0)
    text = format_outcome_alert(row, "sl_hit")
    assert "SL HIT BTCUSDT" in text
    assert "SHORT -5.00%" in text
```
with:
```python
def test_format_outcome_alert_long_tp3():
    text = format_outcome_alert(_row(), "tp3_hit")
    assert "TP3 HIT BTCUSDT" in text
    assert "LONG +10.00%" in text
    assert "Entry 100 → 110" in text


def test_format_outcome_alert_short_sl_is_negative():
    row = _row(direction="short", stop=105.0, tp1=98.0, tp2=95.0, tp3=90.0)
    text = format_outcome_alert(row, "sl_hit")
    assert "SL HIT BTCUSDT" in text
    assert "SHORT -5.00%" in text
```
(`format_outcome_alert` is implemented in Task 8 — this file's tests for it
are updated here since they share the `_row` fixture; they'll pass once
Task 8 lands.)

Update `_track`'s monkeypatch list to also stub `mark_tp_level` and the new
`send_tp_level_alert`:
```python
def _track(monkeypatch, rows, cfg=None, prefetched=None,
           fetched_candles=None):
    """Run track_open_signals with storage/telegram/binance stubbed out.
    Returns (closed_pairs, recorded_fetches, recorded_closes, alerts,
    level_marks, level_alerts)."""
    fetches, closes, alerts, level_marks, level_alerts = [], [], [], [], []

    monkeypatch.setattr(outcome_tracker, "list_open_signals",
                        lambda url, key, session=None: rows)

    def fake_fetch(symbol, interval, limit, start_time=None, session=None):
        fetches.append({"symbol": symbol, "limit": limit,
                        "start_time": start_time})
        return fetched_candles if fetched_candles is not None else []

    monkeypatch.setattr(outcome_tracker, "fetch_candles", fake_fetch)
    monkeypatch.setattr(
        outcome_tracker, "close_signal",
        lambda sig_id, status, closed_at, url, key, session=None:
        closes.append((sig_id, status)))
    monkeypatch.setattr(
        outcome_tracker, "mark_tp_level",
        lambda sig_id, level, status, hit_at, url, key, session=None:
        level_marks.append((sig_id, status)))
    monkeypatch.setattr(
        outcome_tracker, "send_outcome_alert",
        lambda row, outcome, token, chat_id: alerts.append((row, outcome)))
    monkeypatch.setattr(
        outcome_tracker, "send_tp_level_alert",
        lambda row, level, token, chat_id: level_alerts.append((row["id"], level)))

    closed = track_open_signals(cfg or _config(), prefetched=prefetched)
    return closed, fetches, closes, alerts, level_marks, level_alerts
```

Update every call site of `_track(...)` in this file to unpack the two new
return values — e.g. change:
```python
    closed, fetches, closes, _ = _track(
        monkeypatch, [row], fetched_candles=hit_candles)
```
to:
```python
    closed, fetches, closes, _, _, _ = _track(
        monkeypatch, [row], fetched_candles=hit_candles)
```
Apply this same `_, _, _` pattern (adding two more placeholders) to every
existing `_track(...)` call in the file — there are eleven of them
(`test_track_fetches_history_from_signal_creation` through
`test_track_scalp_signals_expire_faster_than_swing`). Where a test currently
unpacks `alerts` as the 4th value, keep that binding name and just add two
trailing `_`.

Since every `_live_row`/`test_track_*` fixture's default outcome now hits
**both** TP1 and TP2 en route to TP3 (candles start flat at 100 with
high=105/low=99 by default, and the new fixture's `take_profit_1=102.0` sits
inside that range), update the assertions that expect a single
`"tp_hit"` result to expect `"tp3_hit"` instead, and update
`_candles_from`'s default `high=105.0` callers that were relying on it
clearing the *old* single TP of 110.0 — those already pass `high=111.0`
explicitly, so no change needed there. Specifically:

- `test_track_fetches_history_from_signal_creation`: `closes == [("sig-9d", "tp_hit")]` → `closes == [("sig-9d", "tp3_hit")]`; same for the `closed` assertion.
- `test_track_uses_prefetched_candles_that_cover_creation`: `closes == [(row["id"], "tp_hit")]` → `"tp3_hit"`.
- `test_track_refetches_when_prefetched_starts_too_late`: same rename.
- `test_track_prefers_real_outcome_over_expiry`: `closes == [(row["id"], "tp_hit")]` → `"tp3_hit"`; `alerts == [(row, "tp_hit")]` → `alerts == [(row, "tp3_hit")]`.
- `test_track_fetches_candles_in_the_rows_own_timeframe`: `closes == [("scalp-1", "tp_hit")]` → `"tp3_hit"`.

Add new tests after `test_track_prefers_real_outcome_over_expiry`:

```python
def test_track_marks_tp1_without_closing_the_signal(monkeypatch):
    # Candle clears TP1 (102) but not TP2 (105) or TP3 (110) — the signal
    # stays open, tracked next run, and gets a non-terminal alert.
    row = _live_row(days_old=1)
    candles = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=1), hours=24,
        high=103.0, low=99.0)

    closed, _, closes, alerts, level_marks, level_alerts = _track(
        monkeypatch, [row], cfg=_config(telegram=True),
        fetched_candles=candles)

    assert closed == []
    assert closes == []  # close_signal (terminal) never called
    assert level_marks == [(row["id"], "tp1_hit")]
    assert level_alerts == [(row["id"], 1)]
    assert alerts == []  # send_outcome_alert (terminal) never called


def test_track_applies_multiple_levels_in_one_run(monkeypatch):
    # A single run's candles clear TP1 and TP2 but not TP3 — both level
    # marks and alerts fire, in order, and the signal still isn't closed.
    row = _live_row(days_old=1)
    candles = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=1), hours=24,
        high=106.0, low=99.0)

    closed, _, closes, _, level_marks, level_alerts = _track(
        monkeypatch, [row], cfg=_config(telegram=True),
        fetched_candles=candles)

    assert closed == []
    assert closes == []
    assert level_marks == [(row["id"], "tp1_hit"), (row["id"], "tp2_hit")]
    assert level_alerts == [(row["id"], 1), (row["id"], 2)]


def test_track_closes_on_tp3(monkeypatch):
    row = _live_row(days_old=1)
    candles = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=1), hours=24,
        high=111.0, low=99.0)

    closed, _, closes, alerts, level_marks, level_alerts = _track(
        monkeypatch, [row], cfg=_config(telegram=True),
        fetched_candles=candles)

    assert closes == [(row["id"], "tp3_hit")]
    assert [(r["id"], o) for r, o in closed] == [(row["id"], "tp3_hit")]
    assert alerts == [(row, "tp3_hit")]
    # tp1/tp2 were crossed en route to tp3 in the same run — still marked.
    assert level_marks == [(row["id"], "tp1_hit"), (row["id"], "tp2_hit")]
    assert level_alerts == [(row["id"], 1), (row["id"], 2)]


def test_track_resumes_from_tp1_hit_status(monkeypatch):
    # Signal already progressed to tp1_hit on a prior run; this run's
    # candles clear tp2 but not tp3 — only the new level is marked.
    row = _live_row(days_old=1, status="tp1_hit")
    candles = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=1), hours=24,
        high=106.0, low=99.0)

    closed, _, closes, _, level_marks, level_alerts = _track(
        monkeypatch, [row], fetched_candles=candles)

    assert closed == []
    assert level_marks == [(row["id"], "tp2_hit")]
    assert level_alerts == [(row["id"], 2)]
```

- [ ] **Step 6: Run to confirm the new/updated `track_open_signals` tests fail**

Run: `python -m pytest tests/test_outcome.py -v -k track`
Expected: FAIL — `track_open_signals` still returns/handles single-string
outcomes and there's no `mark_tp_level`/`send_tp_level_alert` to monkeypatch
on the `outcome_tracker` module yet.

- [ ] **Step 7: Rewrite `track_open_signals`**

In `signals/outcome_tracker.py`, update the imports:
```python
from signals.storage import close_signal, list_open_signals
from signals.telegram_client import send_outcome_alert
```
to:
```python
from signals.storage import close_signal, list_open_signals, mark_tp_level
from signals.telegram_client import send_outcome_alert, send_tp_level_alert
```

Replace the whole `track_open_signals` function body from `now = datetime.now(timezone.utc)` to the end with:

```python
    now = datetime.now(timezone.utc)
    closed = []
    for row in open_rows:
        symbol = row["symbol"]
        timeframe = row.get("timeframe") or "1h"
        session_cfg = _SESSION_BY_TIMEFRAME.get(timeframe)
        max_open_days = (session_cfg.max_open_days if session_cfg
                         else _DEFAULT_MAX_OPEN_DAYS)
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + timedelta(days=max_open_days)
        candles = candles_covering(symbol, timeframe, created_ms)
        if candles is None:
            continue
        # Hits only count inside the expiry window: a level touched weeks
        # later is not the trade the engine proposed.
        expiry_ms = expires_at.timestamp() * 1000
        events = check_outcome(
            row, [c for c in candles if c.open_time < expiry_ms])
        if not events and now >= expires_at:
            events = ["expired"]
        if not events:
            continue

        now_iso = now.isoformat()
        for event in events:
            if event in ("tp1_hit", "tp2_hit"):
                level = int(event[2])
                try:
                    mark_tp_level(row["id"], level, event, now_iso,
                                 cfg.supabase_url, cfg.supabase_service_key,
                                 session=session)
                except Exception as exc:
                    print(f"[{symbol}] failed to mark {event} "
                          f"({type(exc).__name__}), will retry next run")
                    break
                print(f"[{symbol}] {event.upper().replace('_', ' ')} — "
                      f"{row['direction']} from {row['entry']}")
                if cfg.telegram_bot_token and cfg.telegram_channel_id:
                    try:
                        send_tp_level_alert(row, level, cfg.telegram_bot_token,
                                            cfg.telegram_channel_id)
                        print(f"[{symbol}] Telegram {event} alert sent")
                    except Exception as exc:
                        print(f"[{symbol}] Telegram {event} alert failed "
                              f"({type(exc).__name__}), continuing")
                continue

            # Terminal: tp3_hit, sl_hit, expired.
            try:
                close_signal(row["id"], event, now_iso,
                            cfg.supabase_url, cfg.supabase_service_key,
                            session=session)
            except Exception as exc:
                print(f"[{symbol}] failed to mark {event} "
                      f"({type(exc).__name__}), will retry next run")
                break
            print(f"[{symbol}] {event.upper().replace('_', ' ')} — "
                  f"{row['direction']} from {row['entry']}")
            closed.append((row, event))
            if event in ("tp3_hit", "sl_hit") and (
                    cfg.telegram_bot_token and cfg.telegram_channel_id):
                try:
                    send_outcome_alert(row, event, cfg.telegram_bot_token,
                                       cfg.telegram_channel_id)
                    print(f"[{symbol}] Telegram outcome alert sent")
                except Exception as exc:
                    print(f"[{symbol}] Telegram outcome alert failed "
                          f"({type(exc).__name__}), continuing")
    return closed
```

Also update the function's docstring (directly above `now = datetime...`,
i.e. the existing `"""Close every open signal..."""` docstring) to:
```python
    """Advance every open/tp1_hit/tp2_hit signal against fresh candles.
    Non-terminal TP1/TP2 hits are stamped and alerted but the signal stays
    open; terminal events (tp3_hit/sl_hit/expired) close it. Returns the
    closed rows as (row, status) pairs — terminal outcomes only, matching
    what the engine-run summary expects. Never raises — outcome tracking
    must not break a scan run.

    `prefetched` maps (symbol, timeframe) -> closed candles already fetched
    by the scan; a signal's history is refetched from its created_at only
    when the scan candles don't reach back that far."""
```

- [ ] **Step 8: Run to confirm all of `test_outcome.py` passes**

Run: `python -m pytest tests/test_outcome.py -v`
Expected: PASS (all tests) — this also requires Task 8's
`send_tp_level_alert`/updated `format_outcome_alert` to exist, so if
executing tasks strictly in order, come back to re-run this after Task 8.

- [ ] **Step 9: Commit**

```bash
git add signals/outcome_tracker.py tests/test_outcome.py
git commit -m "$(cat <<'EOF'
Rewrite outcome tracking as a multi-level TP1/TP2/TP3 state machine

check_outcome now returns an ordered list of newly-crossed events instead
of a single outcome string. track_open_signals applies each event (mark
non-terminal TP1/TP2, close on tp3_hit/sl_hit/expired) and alerts per
level, returning only terminal events to match the engine-run summary.
EOF
)"
```

---

### Task 8: `signals/telegram_client.py` — per-level alerts

**Files:**
- Modify: `signals/telegram_client.py`
- Test: `tests/test_telegram.py`

- [ ] **Step 1: Update fixtures and write the new failing tests first**

In `tests/test_telegram.py`, replace the `_signal()` fixture:
```python
def _signal(direction="long", confidence=80, rationale="Looks good."):
    setup = CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=108240.0,
        stop_loss=106900.0, take_profit=110920.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", confidence, rationale)
    return make_signal(setup, confirmation, ["headline one"])
```
with:
```python
def _signal(direction="long", confidence=80, rationale="Looks good."):
    setup = CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=108240.0,
        stop_loss=106900.0, take_profit_1=109580.0, take_profit_2=110920.0,
        take_profit_3=112260.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", confidence, rationale)
    return make_signal(setup, confirmation, ["headline one"])
```

Replace:
```python
def test_format_alert_contains_trade_details():
    text = format_alert(_signal())
    assert "<b>LONG BTCUSDT</b>" in text
    assert "(1h)" in text
    assert "Entry 108240 | SL 106900 | TP 110920" in text
    assert "Confidence 80%" in text
    assert "Looks good." in text
    assert text.startswith("<b>")
```
with:
```python
def test_format_alert_contains_trade_details():
    text = format_alert(_signal())
    assert "<b>LONG BTCUSDT</b>" in text
    assert "(1h)" in text
    assert "Entry 108240 | SL 106900" in text
    assert "TP1 109580 | TP2 110920 | TP3 112260" in text
    assert "Confidence 80%" in text
    assert "Looks good." in text
    assert text.startswith("<b>")
```

Replace the `_setup()` helper:
```python
def _setup(direction="long"):
    return CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 1.0, "ema21": 1.0, "rsi": 50.0, "macd_hist": 0.1},
    )
```
with:
```python
def _setup(direction="long"):
    return CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=100.0,
        stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
        take_profit_3=106.0,
        indicators={"ema9": 1.0, "ema21": 1.0, "rsi": 50.0, "macd_hist": 0.1},
    )
```

Replace the `other_setup` inline construction inside
`test_already_signaled_uses_prefetched_map_without_querying`:
```python
    other_setup = CandidateSetup(
        symbol="ETHUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0, indicators={})
```
with:
```python
    other_setup = CandidateSetup(
        symbol="ETHUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
        take_profit_3=106.0, indicators={})
```

Replace `_no_signal_report`:
```python
def _no_signal_report(kind="no_setup", rationale="No crossover yet."):
    return NoSignalReport(
        symbol="BTCUSDT",
        timeframe="1h",
        kind=kind,
        rationale=rationale,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
        direction="long" if kind == "rejected" else None,
        entry=100.0 if kind == "rejected" else None,
        stop_loss=98.0 if kind == "rejected" else None,
        take_profit=104.0 if kind == "rejected" else None,
        confidence=25 if kind == "rejected" else None,
    )
```
with:
```python
def _no_signal_report(kind="no_setup", rationale="No crossover yet."):
    is_rejected = kind == "rejected"
    return NoSignalReport(
        symbol="BTCUSDT",
        timeframe="1h",
        kind=kind,
        rationale=rationale,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
        direction="long" if is_rejected else None,
        entry=100.0 if is_rejected else None,
        stop_loss=98.0 if is_rejected else None,
        take_profit_1=102.0 if is_rejected else None,
        take_profit_2=104.0 if is_rejected else None,
        take_profit_3=106.0 if is_rejected else None,
        confidence=25 if is_rejected else None,
    )
```

Add a new assertion to `test_format_no_signal_alert_for_rejected`:
```python
def test_format_no_signal_alert_for_rejected():
    text = format_no_signal_alert(_no_signal_report(kind="rejected"))
    assert "<b>REJECTED BTCUSDT</b>" in text
    assert "LONG candidate @ 100" in text
    assert "TP1 102 | TP2 104 | TP3 106" in text
    assert "Confidence 25%" in text
```

Add new tests at the end of the file, for the new TP-level alert:
```python
def test_format_tp_level_alert_long():
    from signals.telegram_client import format_tp_level_alert
    text = format_tp_level_alert(_row_for_alert(), 1)
    assert "TP1 HIT BTCUSDT" in text
    assert "LONG @ 102" in text
    assert "running to TP2" in text


def test_format_tp_level_alert_short():
    from signals.telegram_client import format_tp_level_alert
    row = _row_for_alert(direction="short", tp1=98.0, tp2=95.0)
    text = format_tp_level_alert(row, 2)
    assert "TP2 HIT BTCUSDT" in text
    assert "SHORT @ 95" in text
    assert "running to TP3" in text


def test_send_tp_level_alert_posts_to_bot_api():
    from signals.telegram_client import send_tp_level_alert
    session = FakeSession()
    send_tp_level_alert(_row_for_alert(), 1, "bot-token", "chat-42", session=session)
    assert session.last_url == "https://api.telegram.org/botbot-token/sendMessage"
    assert "TP1 HIT BTCUSDT" in session.last_json["text"]


def _row_for_alert(direction="long", entry=100.0, tp1=102.0, tp2=104.0):
    return {
        "symbol": "BTCUSDT",
        "direction": direction,
        "entry": entry,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
    }
```

Finally, update `test_format_outcome_alert_long_tp`/
`test_format_outcome_alert_short_sl_is_negative` — these live in
`tests/test_outcome.py` (Task 7, Step 5), not this file; no change needed
here.

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: FAIL — fixtures error on the old `take_profit` kwarg, and
`format_tp_level_alert`/`send_tp_level_alert` don't exist yet.

- [ ] **Step 3: Implement in telegram_client.py**

Replace `format_alert`:
```python
def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal."""
    return (
        f"<b>{signal.direction.upper()} {html.escape(signal.symbol)}</b>"
        f" ({html.escape(signal.timeframe)})\n"
        f"Entry {signal.entry:g} | SL {signal.stop_loss:g}"
        f" | TP {signal.take_profit:g}\n"
        f"Confidence {signal.confidence}%\n"
        f"{html.escape(signal.rationale)}"
    )
```
with:
```python
def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal."""
    return (
        f"<b>{signal.direction.upper()} {html.escape(signal.symbol)}</b>"
        f" ({html.escape(signal.timeframe)})\n"
        f"Entry {signal.entry:g} | SL {signal.stop_loss:g}\n"
        f"TP1 {signal.take_profit_1:g} | TP2 {signal.take_profit_2:g}"
        f" | TP3 {signal.take_profit_3:g}\n"
        f"Confidence {signal.confidence}%\n"
        f"{html.escape(signal.rationale)}"
    )
```

In `format_no_signal_alert`, replace the rejected branch's `trade_line`:
```python
        trade_line = (
            f"{html.escape(report.direction.upper())} candidate"
            f" @ {report.entry:g} | SL {report.stop_loss:g}"
            f" | TP {report.take_profit:g}\n"
            f"Confidence {report.confidence}%"
        )
```
with:
```python
        trade_line = (
            f"{html.escape(report.direction.upper())} candidate"
            f" @ {report.entry:g} | SL {report.stop_loss:g}\n"
            f"TP1 {report.take_profit_1:g} | TP2 {report.take_profit_2:g}"
            f" | TP3 {report.take_profit_3:g}\n"
            f"Confidence {report.confidence}%"
        )
```

Replace `format_outcome_alert`:
```python
def format_outcome_alert(signal_row: dict, outcome: str) -> str:
    """Telegram HTML-mode message for a signal that hit its TP or SL."""
    entry = signal_row["entry"]
    is_tp = outcome == "tp_hit"
    exit_price = signal_row["take_profit"] if is_tp else signal_row["stop_loss"]
    move = (exit_price - entry) / entry * 100
    if signal_row["direction"] == "short":
        move = -move
    header = "\U0001F3AF TP HIT" if is_tp else "\U0001F6D1 SL HIT"
    return (
        f"<b>{header} {html.escape(signal_row['symbol'])}</b>"
        f" — {html.escape(signal_row['direction'].upper())} {move:+.2f}%\n"
        f"Entry {entry:g} → {exit_price:g}"
    )
```
with:
```python
def format_outcome_alert(signal_row: dict, outcome: str) -> str:
    """Telegram HTML-mode message for a signal that hit its final target
    (TP3) or its stop."""
    entry = signal_row["entry"]
    is_tp = outcome == "tp3_hit"
    exit_price = signal_row["take_profit_3"] if is_tp else signal_row["stop_loss"]
    move = (exit_price - entry) / entry * 100
    if signal_row["direction"] == "short":
        move = -move
    header = "\U0001F3AF TP3 HIT" if is_tp else "\U0001F6D1 SL HIT"
    return (
        f"<b>{header} {html.escape(signal_row['symbol'])}</b>"
        f" — {html.escape(signal_row['direction'].upper())} {move:+.2f}%\n"
        f"Entry {entry:g} → {exit_price:g}"
    )
```

Immediately after `send_outcome_alert`, add:
```python
def format_tp_level_alert(signal_row: dict, level: int) -> str:
    """Telegram HTML-mode message for a non-terminal TP1/TP2 hit — the
    trade is still running toward the next level."""
    price = signal_row[f"take_profit_{level}"]
    return (
        f"<b>\U0001F3AF TP{level} HIT {html.escape(signal_row['symbol'])}</b>"
        f" — {html.escape(signal_row['direction'].upper())} @ {price:g}"
        f" (running to TP{level + 1})"
    )


def send_tp_level_alert(signal_row: dict, level: int, bot_token: str,
                        chat_id: str, session=None) -> None:
    """Send one TP1/TP2-hit alert (non-terminal)."""
    send_message(format_tp_level_alert(signal_row, level), bot_token, chat_id,
                 session=session)
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Re-run `test_outcome.py` now that Task 7 depends on this**

Run: `python -m pytest tests/test_outcome.py -v`
Expected: PASS (all tests) — confirms Task 7's Step 9 commit point is safe.

- [ ] **Step 6: Commit**

```bash
git add signals/telegram_client.py tests/test_telegram.py
git commit -m "$(cat <<'EOF'
Show 3 TP levels in Telegram alerts; add per-level TP1/TP2 alert

format_alert and the rejected-setup alert now list TP1/TP2/TP3. The
terminal outcome alert says "TP3 HIT" instead of "TP HIT". New
format_tp_level_alert/send_tp_level_alert cover non-terminal TP1/TP2 hits.
EOF
)"
```

---

### Task 9: `signals/run.py` — pass 3 TP levels through ai_events logging

**Files:**
- Modify: `signals/run.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Update the failing fixtures first**

In `tests/test_pipeline.py`, replace:
```python
SETUP = CandidateSetup(
    symbol="BTCUSDT", direction="long", entry=100.0,
    stop_loss=98.0, take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)
```
with:
```python
SETUP = CandidateSetup(
    symbol="BTCUSDT", direction="long", entry=100.0,
    stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
    take_profit_3=106.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)
```

And replace:
```python
    other_setup = CandidateSetup(
        symbol="ETHUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0, indicators={})
```
with:
```python
    other_setup = CandidateSetup(
        symbol="ETHUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit_1=102.0, take_profit_2=104.0,
        take_profit_3=106.0, indicators={})
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `TypeError: CandidateSetup.__init__() got an unexpected
keyword argument 'take_profit'`

- [ ] **Step 3: Implement in run.py**

Replace `_log_ai_event`'s signature and body:
```python
def _log_ai_event(kind: str, symbol: str, cfg, *, timeframe: str,
                  rationale: str, indicators: dict, headlines: list,
                  direction=None, entry=None, stop_loss=None, take_profit=None,
                  confidence=None, session=None) -> None:
    """Best-effort insert into ai_events; never raises."""
    event = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "kind": kind,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence": confidence,
        "rationale": rationale,
        "indicators": indicators,
        "news_headlines": list(headlines),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
```
with:
```python
def _log_ai_event(kind: str, symbol: str, cfg, *, timeframe: str,
                  rationale: str, indicators: dict, headlines: list,
                  direction=None, entry=None, stop_loss=None,
                  take_profit_1=None, take_profit_2=None, take_profit_3=None,
                  confidence=None, session=None) -> None:
    """Best-effort insert into ai_events; never raises."""
    event = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "kind": kind,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "take_profit_3": take_profit_3,
        "confidence": confidence,
        "rationale": rationale,
        "indicators": indicators,
        "news_headlines": list(headlines),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
```

Replace the "reject" call site:
```python
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=timeframe,
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            headlines=headlines,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
            session=session,
        )
```
with:
```python
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=timeframe,
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            headlines=headlines,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit_1=setup.take_profit_1,
            take_profit_2=setup.take_profit_2,
            take_profit_3=setup.take_profit_3,
            confidence=confirmation.confidence,
            session=session,
        )
```

Replace the `NoSignalReport(... kind="rejected" ...)` construction right
after it:
```python
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=timeframe,
            kind="rejected",
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
        ), candles=candles)
```
with:
```python
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=timeframe,
            kind="rejected",
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit_1=setup.take_profit_1,
            take_profit_2=setup.take_profit_2,
            take_profit_3=setup.take_profit_3,
            confidence=confirmation.confidence,
        ), candles=candles)
```

Replace the "confirm" call site:
```python
    _log_ai_event(
        "confirm",
        symbol,
        cfg,
        timeframe=timeframe,
        rationale=signal.rationale,
        indicators=signal.indicators,
        headlines=signal.news_headlines,
        direction=signal.direction,
        entry=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        confidence=signal.confidence,
        session=session,
        )
```
with:
```python
    _log_ai_event(
        "confirm",
        symbol,
        cfg,
        timeframe=timeframe,
        rationale=signal.rationale,
        indicators=signal.indicators,
        headlines=signal.news_headlines,
        direction=signal.direction,
        entry=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit_1=signal.take_profit_1,
        take_profit_2=signal.take_profit_2,
        take_profit_3=signal.take_profit_3,
        confidence=signal.confidence,
        session=session,
        )
```

Replace `OUTCOME_LABELS`:
```python
OUTCOME_LABELS = {"tp_hit": "TP HIT", "sl_hit": "SL HIT", "expired": "EXPIRED"}
```
with:
```python
OUTCOME_LABELS = {"tp3_hit": "TP3 HIT", "sl_hit": "SL HIT", "expired": "EXPIRED"}
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_pipeline.py tests/test_telegram.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/run.py tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
Pass take_profit_1/2/3 through ai_events logging and rename OUTCOME_LABELS

_log_ai_event, its reject/confirm call sites, and the rejected
NoSignalReport now carry all three TP levels. OUTCOME_LABELS' tp_hit
entry becomes tp3_hit to match the renamed terminal status.
EOF
)"
```

---

### Task 10: `signals/calibration.py` — win/R-multiple math on `tp3_hit`

**Files:**
- Modify: `signals/calibration.py`
- Test: `tests/test_calibration.py`

- [ ] **Step 1: Update the fixture and every `status="tp_hit"` first**

In `tests/test_calibration.py`, replace the `_row` fixture:
```python
def _row(**overrides):
    row = {
        "symbol": "BTCUSDT", "timeframe": "1h", "direction": "long",
        "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
        "confidence": 80, "status": "tp_hit", "indicators": {},
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row
```
with:
```python
def _row(**overrides):
    row = {
        "symbol": "BTCUSDT", "timeframe": "1h", "direction": "long",
        "entry": 100.0, "stop_loss": 98.0, "take_profit_3": 104.0,
        "confidence": 80, "status": "tp3_hit", "indicators": {},
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row
```

Then replace every remaining `status="tp_hit"` in this file (in
`test_r_multiple_tp_hit_uses_reward_risk_ratio`,
`test_r_multiple_short_direction_uses_absolute_distances`,
`test_bucket_stats_counts_and_win_rate`,
`test_summarize_by_groups_rows`, and
`test_calibration_report_has_all_groupings`) with `status="tp3_hit"`, and
replace the `take_profit=96.0` kwarg in
`test_r_multiple_short_direction_uses_absolute_distances` with
`take_profit_3=96.0`.

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: FAIL — `_r_multiple`/`_bucket_stats` still read `row["take_profit"]`
and compare against `"tp_hit"`, which no `_row()` fixture produces anymore.

- [ ] **Step 3: Implement in calibration.py**

Replace:
```python
def _r_multiple(row: dict) -> float:
    """Realized R-multiple for one closed signal: +reward/risk on tp_hit,
    -1 on sl_hit, 0 (unknown/neutral) on expired — outcome_tracker records
    no exit price for expired signals, so their true P&L is unknown."""
    status = row["status"]
    if status == "sl_hit":
        return -1.0
    if status == "expired":
        return 0.0
    entry, stop, target = row["entry"], row["stop_loss"], row["take_profit"]
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    return abs(target - entry) / risk


def _bucket_stats(rows: list) -> dict:
    wins = sum(1 for r in rows if r["status"] == "tp_hit")
    losses = sum(1 for r in rows if r["status"] == "sl_hit")
```
with:
```python
def _r_multiple(row: dict) -> float:
    """Realized R-multiple for one closed signal: +reward/risk on tp3_hit
    (the final target), -1 on sl_hit, 0 (unknown/neutral) on expired —
    outcome_tracker records no exit price for expired signals, so their
    true P&L is unknown."""
    status = row["status"]
    if status == "sl_hit":
        return -1.0
    if status == "expired":
        return 0.0
    entry, stop, target = row["entry"], row["stop_loss"], row["take_profit_3"]
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    return abs(target - entry) / risk


def _bucket_stats(rows: list) -> dict:
    wins = sum(1 for r in rows if r["status"] == "tp3_hit")
    losses = sum(1 for r in rows if r["status"] == "sl_hit")
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add signals/calibration.py tests/test_calibration.py
git commit -m "Score calibration report wins/R-multiple against tp3_hit"
```

---

### Task 11: Full Python test suite checkpoint

**Files:** none (verification only)

- [ ] **Step 1: Run the entire Python suite**

Run: `python -m pytest -v`
Expected: PASS — every test in `tests/` (all 9 files touched above, plus
any untouched ones) is green. If anything still references the old
`take_profit`/`tp_hit` shape, it will fail here; fix it before moving to
the frontend.

- [ ] **Step 2: No commit** — this is a verification checkpoint, not a code change.

---

### Task 12: `web/src/lib/signals.ts` — types, parsing, daily P&L

**Files:**
- Modify: `web/src/lib/signals.ts`
- Test: `web/src/lib/signals.test.ts`

- [ ] **Step 1: Update the fixture and add failing assertions first**

In `web/src/lib/signals.test.ts`, replace the `ROW` fixture's
`take_profit` line:
```ts
  take_profit: 110920.0,
```
with:
```ts
  take_profit_1: 109580.0,
  take_profit_2: 110920.0,
  take_profit_3: 112260.0,
```

Replace the assertion in `"maps PostgREST rows to camelCase signals"`:
```ts
    expect(s.takeProfit).toBe(110920.0);
```
with:
```ts
    expect(s.takeProfit1).toBe(109580.0);
    expect(s.takeProfit2).toBe(110920.0);
    expect(s.takeProfit3).toBe(112260.0);
```

Add a new test after `"keeps the expired status instead of treating it as open"`:
```ts
  it("keeps tp1_hit/tp2_hit status instead of treating it as open", async () => {
    mockFetch([{ ...ROW, status: "tp1_hit" }]);
    const signals = await getSignals();
    expect(signals[0].status).toBe("tp1_hit");
  });
```

- [ ] **Step 2: Run to confirm it fails**

Run: `cd web && npx vitest run src/lib/signals.test.ts`
Expected: FAIL — `s.takeProfit1` is `undefined` (still mapped from
`row.take_profit`, which no longer exists on the fixture).

- [ ] **Step 3: Implement in signals.ts**

Replace:
```ts
export type SignalStatus = "open" | "tp_hit" | "sl_hit" | "expired";

export type Signal = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  rationale: string;
  indicators: { ema9: number; ema21: number; rsi: number; macdHist: number };
  newsHeadlines: string[];
  createdAt: string;
  status: SignalStatus;
};
```
with:
```ts
export type SignalStatus =
  | "open"
  | "tp1_hit"
  | "tp2_hit"
  | "tp3_hit"
  | "sl_hit"
  | "expired";

export type Signal = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  takeProfit3: number;
  confidence: number;
  rationale: string;
  indicators: { ema9: number; ema21: number; rsi: number; macdHist: number };
  newsHeadlines: string[];
  createdAt: string;
  status: SignalStatus;
};
```

Replace the `SignalRow` type's take-profit field:
```ts
  take_profit: number;
```
with:
```ts
  take_profit_1: number;
  take_profit_2: number;
  take_profit_3: number;
```

Replace `parseStatus`:
```ts
function parseStatus(value: string | undefined): SignalStatus {
  if (value === "tp_hit" || value === "sl_hit" || value === "expired") {
    return value;
  }
  return "open";
}
```
with:
```ts
function parseStatus(value: string | undefined): SignalStatus {
  if (
    value === "tp1_hit" ||
    value === "tp2_hit" ||
    value === "tp3_hit" ||
    value === "sl_hit" ||
    value === "expired"
  ) {
    return value;
  }
  return "open";
}
```

In `parseRow`, replace:
```ts
    takeProfit: row.take_profit,
```
with:
```ts
    takeProfit1: row.take_profit_1,
    takeProfit2: row.take_profit_2,
    takeProfit3: row.take_profit_3,
```

In `getDailyPnLStats`, replace:
```ts
    const status = parseStatus(r.status);
    if (status !== "tp_hit" && status !== "sl_hit") continue;
```
with:
```ts
    const status = parseStatus(r.status);
    if (status !== "tp3_hit" && status !== "sl_hit") continue;
```
and replace:
```ts
    if (status === "tp_hit") stats.wins++;
    if (status === "sl_hit") stats.losses++;
```
with:
```ts
    if (status === "tp3_hit") stats.wins++;
    if (status === "sl_hit") stats.losses++;
```

- [ ] **Step 4: Run to confirm it passes**

Run: `cd web && npx vitest run src/lib/signals.test.ts`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/signals.ts web/src/lib/signals.test.ts
git commit -m "$(cat <<'EOF'
Replace Signal.takeProfit with takeProfit1/2/3; add tp1_hit/tp2_hit status

parseStatus now recognizes the two new non-terminal statuses.
getDailyPnLStats counts wins on tp3_hit instead of tp_hit.
EOF
)"
```

---

### Task 13: `SignalsGrid.tsx` — status pill and price cells

**Files:**
- Modify: `web/src/components/dashboard/SignalsGrid.tsx`
- Test: `web/src/components/dashboard/SignalsGrid.test.tsx`

- [ ] **Step 1: Update the fixture and write failing assertions first**

In `web/src/components/dashboard/SignalsGrid.test.tsx`, replace the
`SIGNAL` fixture's take-profit line:
```ts
  takeProfit: 110920,
```
with:
```ts
  takeProfit1: 109580,
  takeProfit2: 110920,
  takeProfit3: 112260,
```

Replace the price assertions in `"renders signal cards with key prices"`:
```ts
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
```
with:
```ts
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("109,580")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("112,260")).toBeDefined();
```

Replace:
```ts
  it("shows closed status on cards", () => {
    render(<SignalsGrid signals={[{ ...SIGNAL, status: "tp_hit" }]} />);
    expect(screen.getByText("TP hit")).toBeDefined();
  });
```
with:
```ts
  it("shows closed status on cards", () => {
    render(<SignalsGrid signals={[{ ...SIGNAL, status: "tp3_hit" }]} />);
    expect(screen.getByText("TP3 hit")).toBeDefined();
  });

  it("shows running status for tp1_hit and tp2_hit", () => {
    const { rerender } = render(
      <SignalsGrid signals={[{ ...SIGNAL, status: "tp1_hit" }]} />,
    );
    expect(screen.getByText("TP1 hit")).toBeDefined();
    rerender(<SignalsGrid signals={[{ ...SIGNAL, status: "tp2_hit" }]} />);
    expect(screen.getByText("TP2 hit")).toBeDefined();
  });
```

Replace the loop in `"does not gray out open, tp_hit, or expired cards"`:
```ts
  it("does not gray out open, tp_hit, or expired cards", () => {
    for (const status of ["open", "tp_hit", "expired"] as const) {
```
with:
```ts
  it("does not gray out open, tp1_hit, tp2_hit, tp3_hit, or expired cards", () => {
    for (const status of [
      "open", "tp1_hit", "tp2_hit", "tp3_hit", "expired",
    ] as const) {
```

- [ ] **Step 2: Run to confirm it fails**

Run: `cd web && npx vitest run src/components/dashboard/SignalsGrid.test.tsx`
Expected: FAIL — the card only ever renders one "Target" price (mapped
from the now-nonexistent `takeProfit`), and `"TP3 hit"`/`"TP1 hit"`/`"TP2
hit"` text doesn't exist yet.

- [ ] **Step 3: Implement in SignalsGrid.tsx**

Replace `riskReward`:
```tsx
function riskReward(signal: Signal): string {
  const risk = Math.abs(signal.entry - signal.stopLoss);
  if (risk === 0) return "—";
  const reward = Math.abs(signal.takeProfit - signal.entry);
  return `${(reward / risk).toFixed(1)}R`;
}
```
with:
```tsx
function riskReward(signal: Signal): string {
  const risk = Math.abs(signal.entry - signal.stopLoss);
  if (risk === 0) return "—";
  const reward = Math.abs(signal.takeProfit3 - signal.entry);
  return `${(reward / risk).toFixed(1)}R`;
}
```

Replace `StatusPill`:
```tsx
function StatusPill({ status }: { status: Signal["status"] }) {
  if (status === "open") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide text-slate">
        Open
      </span>
    );
  }
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  const isWin = status === "tp_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP hit" : "SL hit"}
    </span>
  );
}
```
with:
```tsx
function StatusPill({ status }: { status: Signal["status"] }) {
  if (status === "open") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide text-slate">
        Open
      </span>
    );
  }
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  if (status === "tp1_hit" || status === "tp2_hit") {
    return (
      <span className="inline-flex items-center rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-accent">
        {status === "tp1_hit" ? "TP1 hit" : "TP2 hit"}
      </span>
    );
  }
  const isWin = status === "tp3_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP3 hit" : "SL hit"}
    </span>
  );
}
```

In `SignalCard`, replace the price grid:
```tsx
      <div className="relative grid grid-cols-3 gap-3 border-t border-line/50 px-6 py-4 bg-slate/5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Entry</p>
          <p className="font-mono text-sm font-bold text-ink">
            {formatPrice(signal.entry)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Stop Loss</p>
          <p className="font-mono text-sm font-bold text-short drop-shadow-sm">
            {formatPrice(signal.stopLoss)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Target</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit)}
          </p>
        </div>
      </div>
```
with:
```tsx
      <div className="relative grid grid-cols-5 gap-3 border-t border-line/50 px-6 py-4 bg-slate/5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Entry</p>
          <p className="font-mono text-sm font-bold text-ink">
            {formatPrice(signal.entry)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Stop Loss</p>
          <p className="font-mono text-sm font-bold text-short drop-shadow-sm">
            {formatPrice(signal.stopLoss)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">TP1</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit1)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">TP2</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit2)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">TP3</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit3)}
          </p>
        </div>
      </div>
```

In `SignalDetailModal`, replace the detail grid:
```tsx
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DetailRow label="Entry" value={formatPrice(signal.entry)} />
            <DetailRow label="Stop loss" value={formatPrice(signal.stopLoss)} tone="short" />
            <DetailRow label="Take profit" value={formatPrice(signal.takeProfit)} tone="long" />
            <DetailRow label="Risk / reward" value={riskReward(signal)} tone="accent" />
          </div>
```
with:
```tsx
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <DetailRow label="Entry" value={formatPrice(signal.entry)} />
            <DetailRow label="Stop loss" value={formatPrice(signal.stopLoss)} tone="short" />
            <DetailRow label="Risk / reward (TP3)" value={riskReward(signal)} tone="accent" />
            <DetailRow label="Take profit 1" value={formatPrice(signal.takeProfit1)} tone="long" />
            <DetailRow label="Take profit 2" value={formatPrice(signal.takeProfit2)} tone="long" />
            <DetailRow label="Take profit 3" value={formatPrice(signal.takeProfit3)} tone="long" />
          </div>
```

- [ ] **Step 4: Run to confirm it passes**

Run: `cd web && npx vitest run src/components/dashboard/SignalsGrid.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/components/dashboard/SignalsGrid.tsx web/src/components/dashboard/SignalsGrid.test.tsx
git commit -m "$(cat <<'EOF'
Show TP1/TP2/TP3 on signal cards; add running-status pills

StatusPill now distinguishes tp1_hit/tp2_hit (still running) from the
terminal tp3_hit/sl_hit/expired states.
EOF
)"
```

---

### Task 14: `TradeTicket.tsx` — same treatment for the compact card

**Files:**
- Modify: `web/src/components/shared/TradeTicket.tsx`
- Test: `web/src/components/shared/TradeTicket.test.tsx`

- [ ] **Step 1: Update the fixture and write failing assertions first**

In `web/src/components/shared/TradeTicket.test.tsx`, replace:
```ts
  takeProfit: 110920,
```
with:
```ts
  takeProfit1: 109580,
  takeProfit2: 110920,
  takeProfit3: 112260,
```

Replace the price assertions in `"renders symbol, direction, prices, confidence, and rationale"`:
```ts
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
```
with:
```ts
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("109,580")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("112,260")).toBeDefined();
```

Replace:
```ts
  it("shows a status badge only for closed signals", () => {
    const { rerender } = render(<TradeTicket signal={SIGNAL} />);
    expect(screen.queryByText("TP hit")).toBeNull();
    expect(screen.queryByText("SL hit")).toBeNull();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "tp_hit" }} />);
    expect(screen.getByText("TP hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "sl_hit" }} />);
    expect(screen.getByText("SL hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "expired" }} />);
    expect(screen.getByText("Expired")).toBeDefined();
  });
```
with:
```ts
  it("shows a status badge only for closed signals", () => {
    const { rerender } = render(<TradeTicket signal={SIGNAL} />);
    expect(screen.queryByText("TP3 hit")).toBeNull();
    expect(screen.queryByText("SL hit")).toBeNull();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "tp1_hit" }} />);
    expect(screen.getByText("TP1 hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "tp2_hit" }} />);
    expect(screen.getByText("TP2 hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "tp3_hit" }} />);
    expect(screen.getByText("TP3 hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "sl_hit" }} />);
    expect(screen.getByText("SL hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "expired" }} />);
    expect(screen.getByText("Expired")).toBeDefined();
  });
```

- [ ] **Step 2: Run to confirm it fails**

Run: `cd web && npx vitest run src/components/shared/TradeTicket.test.tsx`
Expected: FAIL — same shape as Task 13's Step 2.

- [ ] **Step 3: Implement in TradeTicket.tsx**

Replace `StatusBadge`:
```tsx
function StatusBadge({ status }: { status: Signal["status"] }) {
  if (status === "open") return null;
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  const isWin = status === "tp_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP hit" : "SL hit"}
    </span>
  );
}
```
with:
```tsx
function StatusBadge({ status }: { status: Signal["status"] }) {
  if (status === "open") return null;
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  if (status === "tp1_hit" || status === "tp2_hit") {
    return (
      <span className="inline-flex items-center rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-accent">
        {status === "tp1_hit" ? "TP1 hit" : "TP2 hit"}
      </span>
    );
  }
  const isWin = status === "tp3_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP3 hit" : "SL hit"}
    </span>
  );
}
```

Replace the price grid:
```tsx
      <div className="grid grid-cols-3 gap-4 px-5 py-5">
        <PriceCell label="Entry" value={signal.entry} />
        <PriceCell label="Stop loss" value={signal.stopLoss} tone="short" />
        <PriceCell label="Take profit" value={signal.takeProfit} tone="long" />
      </div>
```
with:
```tsx
      <div className="grid grid-cols-5 gap-4 px-5 py-5">
        <PriceCell label="Entry" value={signal.entry} />
        <PriceCell label="Stop loss" value={signal.stopLoss} tone="short" />
        <PriceCell label="TP1" value={signal.takeProfit1} tone="long" />
        <PriceCell label="TP2" value={signal.takeProfit2} tone="long" />
        <PriceCell label="TP3" value={signal.takeProfit3} tone="long" />
      </div>
```

- [ ] **Step 4: Run to confirm it passes**

Run: `cd web && npx vitest run src/components/shared/TradeTicket.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/components/shared/TradeTicket.tsx web/src/components/shared/TradeTicket.test.tsx
git commit -m "Show TP1/TP2/TP3 and running-status badges in TradeTicket"
```

---

### Task 15: `web/src/lib/supabase/admin.ts` — AI events viewer types

**Files:**
- Modify: `web/src/lib/supabase/admin.ts`

*(No dedicated test file covers this module today — it's exercised only
through `admin/ai/responses/page.tsx`, which Task 16 updates. This task is a
direct implementation change with no separate TDD cycle, matching this
file's existing untested surface.)*

- [ ] **Step 1: Update the `AiEvent` type**

Replace:
```ts
export type AiEvent = {
  id: string;
  symbol: string;
  timeframe: string;
  kind: "confirm" | "reject" | "no_setup";
  direction: "long" | "short" | null;
  entry: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  confidence: number | null;
  rationale: string;
  indicators: unknown;
  newsHeadlines: unknown;
  createdAt: string;
};
```
with:
```ts
export type AiEvent = {
  id: string;
  symbol: string;
  timeframe: string;
  kind: "confirm" | "reject" | "no_setup";
  direction: "long" | "short" | null;
  entry: number | null;
  stopLoss: number | null;
  takeProfit1: number | null;
  takeProfit2: number | null;
  takeProfit3: number | null;
  confidence: number | null;
  rationale: string;
  indicators: unknown;
  newsHeadlines: unknown;
  createdAt: string;
};
```

- [ ] **Step 2: Update the `AiEventRow` type**

Replace:
```ts
  take_profit: number | null;
```
with:
```ts
  take_profit_1: number | null;
  take_profit_2: number | null;
  take_profit_3: number | null;
```

- [ ] **Step 3: Update `mapAiEventRows`**

Replace:
```ts
      takeProfit: typeof r.take_profit === "number" ? r.take_profit : null,
```
with:
```ts
      takeProfit1: typeof r.take_profit_1 === "number" ? r.take_profit_1 : null,
      takeProfit2: typeof r.take_profit_2 === "number" ? r.take_profit_2 : null,
      takeProfit3: typeof r.take_profit_3 === "number" ? r.take_profit_3 : null,
```

- [ ] **Step 4: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: errors only in `web/src/app/admin/ai/responses/page.tsx` (fixed
in Task 16) — no errors remaining in `admin.ts` itself.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/supabase/admin.ts
git commit -m "Replace AiEvent.takeProfit with takeProfit1/2/3"
```

---

### Task 16: `admin/ai/responses/page.tsx` — display 3 TP levels

**Files:**
- Modify: `web/src/app/admin/ai/responses/page.tsx`

*(No dedicated test file for this server page; verified via type-check and
manual dev-server check in Task 18.)*

- [ ] **Step 1: Update the trade-line display**

Replace:
```tsx
                {e.entry != null &&
                e.stopLoss != null &&
                e.takeProfit != null ? (
                  <p className="mt-3 font-mono text-xs text-slate">
                    Entry {e.entry} | SL {e.stopLoss} | TP {e.takeProfit}
                  </p>
                ) : null}
```
with:
```tsx
                {e.entry != null &&
                e.stopLoss != null &&
                e.takeProfit1 != null &&
                e.takeProfit2 != null &&
                e.takeProfit3 != null ? (
                  <p className="mt-3 font-mono text-xs text-slate">
                    Entry {e.entry} | SL {e.stopLoss} | TP1 {e.takeProfit1} | TP2{" "}
                    {e.takeProfit2} | TP3 {e.takeProfit3}
                  </p>
                ) : null}
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors referencing `admin/ai/responses/page.tsx` or `admin.ts`.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/admin/ai/responses/page.tsx
git commit -m "Show TP1/TP2/TP3 in the admin AI responses viewer"
```

---

### Task 17: `Hero.tsx` — sample signal fixture

**Files:**
- Modify: `web/src/components/landing/Hero.tsx`

- [ ] **Step 1: Update `SAMPLE_SIGNAL`**

Replace:
```ts
  takeProfit: 110920,
```
with:
```ts
  takeProfit1: 109580,
  takeProfit2: 110920,
  takeProfit3: 112260,
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors in `Hero.tsx`.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/landing/Hero.tsx
git commit -m "Update landing page sample signal for takeProfit1/2/3"
```

---

### Task 18: Full frontend checkpoint

**Files:** none (verification only)

- [ ] **Step 1: Full type-check**

Run: `cd web && npx tsc --noEmit`
Expected: zero errors anywhere in `web/src`.

- [ ] **Step 2: Full frontend test suite**

Run: `cd web && npx vitest run`
Expected: PASS — every test file, including the three touched above and
any untouched ones (`StatsBar.test.tsx`, etc.), is green.

- [ ] **Step 3: Manual smoke check in the dev server**

Run: `cd web && npm run dev`, then open `/dashboard` in a browser (or
`/admin/ai/responses` if you have admin access configured). Confirm:
- Signal cards show 5 price cells (Entry, Stop Loss, TP1, TP2, TP3), not 3.
- The status pill reads "Open" for open signals — there's no live data yet
  with `tp1_hit`/`tp2_hit`/`tp3_hit`, but you can sanity-check the pill
  logic by temporarily editing a row's `status` in the Supabase table editor
  and refreshing.
- Clicking a card opens the detail modal with the same TP1/TP2/TP3 rows.

Stop the dev server when done (`Ctrl+C`).

- [ ] **Step 4: No commit** — this is a verification checkpoint.

---

### Task 19: Apply the Supabase migration and verify end-to-end

**Files:** none (deployment step)

- [ ] **Step 1: Run the updated `supabase/schema.sql` in the Supabase SQL Editor**

Open the project's Supabase Dashboard → SQL Editor → paste the full
contents of `supabase/schema.sql` → Run. Confirm no errors — the file is
idempotent (every statement uses `if not exists` / `drop ... if exists` /
`or replace`), so this is safe to run against the existing database with
its 14 live rows.

- [ ] **Step 2: Verify the migration**

Run a quick sanity query in the SQL Editor:
```sql
select id, status, take_profit_1, take_profit_2, take_profit_3,
       tp1_hit_at, tp2_hit_at
from public.signals
order by created_at desc
limit 5;
```
Expected: `take_profit_1/2/3` are populated (backfilled) for every existing
row, `take_profit` no longer appears as a column, and `tp1_hit_at`/
`tp2_hit_at` are `null` for all of them (none had partial TP progress under
the old single-TP schema).

- [ ] **Step 3: Run one engine cycle against the live (or a staging) Supabase project**

Run: `python -m signals.run`
Expected: the run completes without error; any newly confirmed signal in
the log output shows `TP1`/`TP2`/`TP3` prices, not a single `TP`.

- [ ] **Step 4: No commit** — this is a deployment/verification step, not a
code change.

---

## Post-plan note for the executor

Tasks 1–11 (Python) and 12–18 (frontend) are independent after Task 2/Task
12 land — the Python and frontend halves don't block each other and could
run as two parallel subagent tracks if using subagent-driven-development,
as long as Task 2 (models.py) finishes before Tasks 3–11, and Task 12
(signals.ts) finishes before Tasks 13–17. Task 19 (migration + live
verification) must come last, after both halves are committed.
