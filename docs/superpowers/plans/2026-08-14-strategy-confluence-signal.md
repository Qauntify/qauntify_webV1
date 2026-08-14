# Cross-Strategy Confluence Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a distinct, deliverable "confluence" signal when 2+ independent strategies (from the three main sessions) are simultaneously open on the same symbol + direction.

**Architecture:** A new module, `signals/pipeline/confluence.py`, runs once per engine cycle after the three-session scan loop. It queries for an already-open signal from a different strategy on the same symbol+direction, and if found (and no confluence signal is already open for that symbol), publishes a new signal that copies the triggering setup's own entry/stop/TPs, tagged `timeframe="confluence"`. Zero schema changes — everything rides in the existing `indicators` JSON, the same technique `war_room`/`bbma` already use.

**Tech Stack:** Python 3 / pytest, Supabase (PostgREST), existing signals pipeline conventions.

**Spec:** `docs/superpowers/specs/2026-08-14-strategy-confluence-signal-design.md`

---

## Before you start

This plan modifies the live signals engine (`signals/pipeline/engine.py`) and the outcome tracker (`signals/outcomes/tracker.py`), both of which run in production on every scheduled scan. Every new code path added here is wrapped in try/except at its call site so a bug in confluence detection can never block the three real sessions' own signal delivery — preserve that property in every task, don't just take it on faith from the spec.

Run the full test suite after every task, not just the new tests — `.venv/bin/python -m pytest tests/ -q --ignore=tests/ml` (the `tests/ml` skip is pre-existing on this machine, unrelated to this work).

---

## Task 1: Persistence — query open signals from other strategies

**Files:**
- Modify: `signals/persistence/signals.py`
- Test: `tests/core/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_storage.py` (near the other `open_symbols_for_timeframe`-style tests):

```python
def test_open_signals_same_direction_excludes_matching_strategy():
    from signals.persistence.signals import open_signals_same_direction

    session = FakeGetSession(payload=[
        {"timeframe": "1h", "indicators": {"strategy": "msnr"}},
        {"timeframe": "15m", "indicators": {"strategy": "cloud_mss"}},
    ])

    result = open_signals_same_direction(
        "BTCUSD", "long", exclude_strategy="cloud_mss",
        supabase_url="https://abc.supabase.co", service_key="key",
        session=session,
    )

    assert result == [{"timeframe": "1h", "indicators": {"strategy": "msnr"}}]
    assert "symbol=eq.BTCUSD" in session.last_url
    assert "direction=eq.long" in session.last_url
    assert "timeframe=neq.confluence" in session.last_url
    assert "shadow=is.false" in session.last_url


def test_open_signals_same_direction_empty_when_only_same_strategy_open():
    from signals.persistence.signals import open_signals_same_direction

    session = FakeGetSession(payload=[
        {"timeframe": "5m", "indicators": {"strategy": "ict_fvg"}},
    ])

    result = open_signals_same_direction(
        "XAUUSD", "short", exclude_strategy="ict_fvg",
        supabase_url="https://abc.supabase.co", service_key="key",
        session=session,
    )

    assert result == []


def test_has_open_confluence_signal_true_when_row_exists():
    from signals.persistence.signals import has_open_confluence_signal

    session = FakeGetSession(payload=[{"id": "sig-1"}])

    assert has_open_confluence_signal(
        "BTCUSD", "https://abc.supabase.co", "key", session=session,
    ) is True
    assert "timeframe=eq.confluence" in session.last_url


def test_has_open_confluence_signal_false_when_none_open():
    from signals.persistence.signals import has_open_confluence_signal

    session = FakeGetSession(payload=[])

    assert has_open_confluence_signal(
        "BTCUSD", "https://abc.supabase.co", "key", session=session,
    ) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_storage.py -k "confluence" -v`
Expected: FAIL — `ImportError: cannot import name 'open_signals_same_direction'`

- [ ] **Step 3: Implement**

Add to `signals/persistence/signals.py` (it already imports `quote` from `urllib.parse` and `requests` at the top — no new imports needed):

```python
def open_signals_same_direction(symbol: str, direction: str, *,
                                exclude_strategy: str,
                                supabase_url: str, service_key: str,
                                session=None) -> list:
    """Open (non-shadow) signals for `symbol`+`direction` from a strategy
    other than `exclude_strategy` -- the confluence pass's "does an
    independent strategy already agree" check.

    `timeframe=neq.confluence` keeps an already-published confluence row
    from ever counting toward a later confluence check (no chaining). The
    strategy filter itself happens in Python: PostgREST can't easily filter
    JSONB `indicators->>strategy` alongside these other conditions in one
    readable query here.
    """
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{quote(symbol)}&direction=eq.{quote(direction)}"
        "&status=in.(open,tp1_hit,tp2_hit)&shadow=is.false"
        "&timeframe=neq.confluence"
        "&select=timeframe,indicators"
        "&order=created_at.desc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return [
        row for row in rows
        if (row.get("indicators") or {}).get("strategy") != exclude_strategy
    ]


def has_open_confluence_signal(symbol: str, supabase_url: str,
                               service_key: str, session=None) -> bool:
    """Whether `symbol` already has an open confluence signal -- guards
    against publishing a second one while the first is still live."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{quote(symbol)}&timeframe=eq.confluence"
        "&status=in.(open,tp1_hit,tp2_hit)&shadow=is.false"
        "&select=id&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return bool(response.json())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_storage.py -k "confluence" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add signals/persistence/signals.py tests/core/test_storage.py
git commit -m "feat(confluence): add open-signal queries for the confluence check"
```

---

## Task 2: Register the confluence session

**Files:**
- Modify: `signals/models.py:194-209` (the `AUXILIARY_SESSIONS` tuple)
- Test: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_pipeline.py`, right after `test_trading_sessions_define_all_three_streams`:

```python
def test_confluence_session_is_registered():
    from signals.models import ALL_SESSIONS, AUXILIARY_SESSIONS

    by_name = {s.name: s for s in AUXILIARY_SESSIONS}
    assert "confluence" in by_name
    assert by_name["confluence"].timeframe == "confluence"
    assert by_name["confluence"].max_open_days == 14
    assert by_name["confluence"] in ALL_SESSIONS
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_pipeline.py -k confluence_session -v`
Expected: FAIL — `AssertionError: assert 'confluence' in {...}`

- [ ] **Step 3: Implement**

In `signals/models.py`, change:

```python
AUXILIARY_SESSIONS = (
    TradingSession(
        name="xau_scalp", timeframe="1m", max_open_days=1, max_open_hours=4,
        strategy="ict_fvg",
    ),
    TradingSession(
        name="war_room", timeframe="floor", max_open_days=2,
        strategy="cloud_mss",
    ),
    # Taught BBMA live lane from QauntifyBBMA.mq5 (no AI gate). Distinct
    # timeframe so it never shares the Swing (1h) tab or open-signal lock.
    TradingSession(
        name="bbma", timeframe="bbma", max_open_days=14,
        strategy="bbma_reentry",
    ),
)
```

to:

```python
AUXILIARY_SESSIONS = (
    TradingSession(
        name="xau_scalp", timeframe="1m", max_open_days=1, max_open_hours=4,
        strategy="ict_fvg",
    ),
    TradingSession(
        name="war_room", timeframe="floor", max_open_days=2,
        strategy="cloud_mss",
    ),
    # Taught BBMA live lane from QauntifyBBMA.mq5 (no AI gate). Distinct
    # timeframe so it never shares the Swing (1h) tab or open-signal lock.
    TradingSession(
        name="bbma", timeframe="bbma", max_open_days=14,
        strategy="bbma_reentry",
    ),
    # Cross-strategy confirmation: fires when 2+ independent strategies from
    # the three main sessions are simultaneously open on the same
    # symbol+direction. Its own entry/SL/TP are copied from whichever setup
    # triggered it (see signals/pipeline/confluence.py), so 14 days --
    # matching swing, the longest of the three -- is a safe upper bound
    # regardless of which session triggered it. The real underlying interval
    # is stashed in indicators["source_timeframe"] for outcome tracking; see
    # docs/superpowers/specs/2026-08-14-strategy-confluence-signal-design.md.
    TradingSession(
        name="confluence", timeframe="confluence", max_open_days=14,
        strategy=None,
    ),
)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_pipeline.py -k confluence_session -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add signals/models.py tests/core/test_pipeline.py
git commit -m "feat(confluence): register the confluence auxiliary session"
```

---

## Task 3: Build the confluence detection module

**Files:**
- Create: `signals/pipeline/confluence.py`
- Test: `tests/core/test_confluence.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_confluence.py`:

```python
from signals.config import Config
from signals.models import BotSettings, Candle, CandidateSetup, Confirmation, make_signal
from signals.pipeline import confluence as confluence_module


def _config():
    return Config(
        sealion_api_key="sk-test",
        supabase_url="https://abc.supabase.co",
        supabase_service_key="service-key",
    )


def _settings():
    return BotSettings()


def _signal(symbol="BTCUSD", direction="long", strategy="cloud_mss",
           timeframe="15m", confidence=70):
    setup = CandidateSetup(
        symbol=symbol, direction=direction, entry=100.0, stop_loss=98.0,
        take_profit=104.0, indicators={"strategy": strategy},
    )
    confirmation = Confirmation("confirm", confidence, "looks good")
    return make_signal(setup, confirmation, [], timeframe=timeframe)


def test_detect_confluence_publishes_when_different_strategy_already_open(monkeypatch):
    signal = _signal(strategy="cloud_mss", timeframe="15m")
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "1h", "indicators": {"strategy": "msnr"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: False)
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))
    sent = []
    monkeypatch.setattr(confluence_module, "maybe_send_alert",
                        lambda sig, *a, **k: sent.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert len(published) == 1
    confluence = published[0]
    assert confluence.timeframe == "confluence"
    assert confluence.indicators["confluence_of"] == ["cloud_mss@15m", "msnr@1h"]
    assert confluence.indicators["source_timeframe"] == "15m"
    assert confluence.entry == signal.entry
    assert confluence.stop_loss == signal.stop_loss
    assert confluence.confidence == signal.confidence
    assert saved == [confluence]
    assert sent == [confluence]


def test_detect_confluence_skips_when_no_other_strategy_open(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    monkeypatch.setattr(confluence_module, "open_signals_same_direction",
                        lambda *a, **k: [])
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert published == []
    assert saved == []


def test_detect_confluence_skips_when_confluence_already_open(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "1h", "indicators": {"strategy": "msnr"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: True)
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert published == []
    assert saved == []


def test_detect_confluence_attaches_chart_when_candles_available(monkeypatch):
    signal = _signal(symbol="ETHUSD", timeframe="1h")
    candles = [Candle(open_time=0, open=100, high=101, low=99,
                      close=100, volume=1.0)]
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "5m", "indicators": {"strategy": "ict_fvg"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: False)
    monkeypatch.setattr(confluence_module, "save_signal", lambda *a, **k: None)
    monkeypatch.setattr(confluence_module, "maybe_send_alert", lambda *a, **k: None)

    charted = []

    def fake_attach(sig, candles_arg, **kwargs):
        charted.append((sig, candles_arg))
        return sig

    monkeypatch.setattr(confluence_module, "attach_chart", fake_attach)

    confluence_module.detect_confluence(
        [signal], {("ETHUSD", "1h"): candles}, _settings(), _config())

    assert len(charted) == 1
    assert charted[0][1] == candles


def test_detect_confluence_skips_signal_with_no_strategy_tag(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    # Simulate a signal whose indicators never got a strategy tag -- must not
    # crash, must not query, must not publish.
    from dataclasses import replace
    untagged = replace(signal, indicators={})

    called = []
    monkeypatch.setattr(confluence_module, "open_signals_same_direction",
                        lambda *a, **k: called.append(1) or [])

    published = confluence_module.detect_confluence(
        [untagged], {}, _settings(), _config())

    assert published == []
    assert called == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_confluence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.pipeline.confluence'`

- [ ] **Step 3: Implement**

Create `signals/pipeline/confluence.py`:

```python
"""Detects when 2+ independent strategies are simultaneously open on the
same symbol + direction, and publishes a distinct 'confluence' signal.

The caller (engine.main()) wraps the single call into this module in
try/except -- a confluence-detection failure must never block the three
real sessions' own signal delivery, which has already completed by the
time this runs.
"""
from signals.chart.pipeline import attach_chart
from signals.models import CandidateSetup, Confirmation, Signal, make_signal
from signals.persistence.signals import (
    has_open_confluence_signal,
    open_signals_same_direction,
    save_signal,
)
from signals.pipeline.deliver import maybe_send_alert

CONFLUENCE_TIMEFRAME = "confluence"


def _build_confluence_signal(signal: Signal, other: dict) -> Signal:
    """A new Signal reusing `signal`'s own levels, tagged with both
    contributing strategies. `other` is one row from
    `open_signals_same_direction` (has `timeframe` and `indicators`)."""
    strategy = signal.indicators.get("strategy", "unknown")
    other_strategy = (other.get("indicators") or {}).get("strategy", "unknown")
    tag_new = f"{strategy}@{signal.timeframe}"
    tag_other = f"{other_strategy}@{other.get('timeframe')}"

    indicators = dict(signal.indicators)
    indicators["confluence_of"] = [tag_new, tag_other]
    # Outcome tracking needs the real interval -- "confluence" itself is not
    # a fetchable broker interval. See track_open_signals in
    # signals/outcomes/tracker.py.
    indicators["source_timeframe"] = signal.timeframe

    setup = CandidateSetup(
        symbol=signal.symbol, direction=signal.direction, entry=signal.entry,
        stop_loss=signal.stop_loss, take_profit=signal.take_profit,
        take_profit_2=signal.take_profit_2, take_profit_3=signal.take_profit_3,
        indicators=indicators,
    )
    rationale = (
        f"{tag_new} confirms {signal.direction}, agreeing with an "
        f"already-open {tag_other} {signal.direction} — confluence signal."
    )
    confirmation = Confirmation("confirm", signal.confidence, rationale)
    return make_signal(setup, confirmation, [], timeframe=CONFLUENCE_TIMEFRAME)


def detect_confluence(newly_confirmed: list, candles_by_symbol: dict,
                      settings, cfg, session=None) -> list:
    """For each signal confirmed this run, check whether a different
    strategy is already open on the same symbol+direction; if so, and no
    confluence signal is already open for that symbol, publish one.

    Returns the list of confluence Signal objects published this run, so the
    caller can fold them into the run summary.
    """
    published = []
    for signal in newly_confirmed:
        strategy = signal.indicators.get("strategy")
        if not strategy:
            continue
        others = open_signals_same_direction(
            signal.symbol, signal.direction, exclude_strategy=strategy,
            supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
            session=session,
        )
        if not others:
            continue
        if has_open_confluence_signal(
            signal.symbol, cfg.supabase_url, cfg.supabase_service_key,
            session=session,
        ):
            continue

        confluence = _build_confluence_signal(signal, others[0])
        candles = candles_by_symbol.get((signal.symbol, signal.timeframe))
        if candles:
            confluence = attach_chart(
                confluence, candles,
                supabase_url=cfg.supabase_url,
                service_key=cfg.supabase_service_key, session=session,
            )
        save_signal(confluence, cfg.supabase_url, cfg.supabase_service_key,
                    session=session)
        maybe_send_alert(confluence, settings, cfg)
        published.append(confluence)
    return published
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_confluence.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add signals/pipeline/confluence.py tests/core/test_confluence.py
git commit -m "feat(confluence): add confluence detection and signal construction"
```

---

## Task 4: Wire confluence detection into the engine

**Files:**
- Modify: `signals/pipeline/engine.py`
- Test: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_pipeline.py`, after `test_main_passes_scan_candles_to_outcome_tracker`:

```python
def test_main_calls_detect_confluence_with_newly_confirmed_signals(monkeypatch):
    from signals.models import CandidateSetup, Confirmation, make_signal

    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(engine_module, "load_config", _config)
    monkeypatch.setattr(engine_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(engine_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(engine_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(engine_module, "save_engine_run",
                        lambda run, url, key, session=None: None)
    monkeypatch.setattr(engine_module, "maybe_send_alert", lambda *a, **k: None)

    confirmed = make_signal(
        CandidateSetup("BTCUSDT", "long", 100.0, 98.0, 104.0,
                       {"strategy": "cloud_mss"}),
        Confirmation("confirm", 80, "ok"), [], timeframe="15m")

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe,
                  session=None, recent_events=None, recent_signals=None,
                  open_symbols=None, confluence_timeframe=None,
                  min_store_confidence=0):
        if timeframe == "15m":
            return ScanResult(signal=confirmed)
        return ScanResult()

    monkeypatch.setattr(engine_module, "scan_symbol", fake_scan)

    captured = {}

    def fake_detect(newly_confirmed, candles_by_symbol, settings_arg, cfg,
                    session=None):
        captured["signals"] = newly_confirmed
        return []

    monkeypatch.setattr(engine_module, "detect_confluence", fake_detect)

    engine_module.main()

    assert captured["signals"] == [confirmed]


def test_main_folds_published_confluence_signals_into_run_summary(monkeypatch):
    from signals.models import CandidateSetup, Confirmation, make_signal

    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(engine_module, "load_config", _config)
    monkeypatch.setattr(engine_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(engine_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(engine_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(engine_module, "scan_symbol",
                        lambda *a, **k: ScanResult())
    monkeypatch.setattr(engine_module, "maybe_send_alert", lambda *a, **k: None)

    confluence_signal = make_signal(
        CandidateSetup("BTCUSDT", "long", 100.0, 98.0, 104.0,
                       {"strategy": "cloud_mss",
                        "confluence_of": ["cloud_mss@15m", "msnr@1h"]}),
        Confirmation("confirm", 75, "confluence"), [], timeframe="confluence")
    monkeypatch.setattr(engine_module, "detect_confluence",
                        lambda *a, **k: [confluence_signal])

    runs = []
    monkeypatch.setattr(engine_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    engine_module.main()

    outcomes = runs[0]["outcomes"]
    assert any(o["timeframe"] == "confluence" and o["status"] == "CONFIRMED"
              for o in outcomes)
    assert runs[0]["stored_count"] == 1


def test_main_confluence_failure_does_not_block_run(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(engine_module, "load_config", _config)
    monkeypatch.setattr(engine_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(engine_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(engine_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(engine_module, "scan_symbol",
                        lambda *a, **k: ScanResult())

    def boom(*a, **k):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(engine_module, "detect_confluence", boom)
    runs = []
    monkeypatch.setattr(engine_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    engine_module.main()  # must not raise

    assert len(runs) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_pipeline.py -k confluence -v`
Expected: FAIL — `AttributeError: module 'signals.pipeline.engine' has no attribute 'detect_confluence'`

- [ ] **Step 3: Implement**

In `signals/pipeline/engine.py`, add the import alongside the other pipeline imports:

```python
from signals.pipeline.dedup import (
    _prefetch_open_symbols,
    _prefetch_recent_events,
    _prefetch_recent_signals,
    with_retry,
)
from signals.pipeline.confluence import detect_confluence
from signals.pipeline.deliver import maybe_send_alert
```

Change:

```python
    stored = 0
    outcomes: list[dict] = []
    candles_by_symbol: dict = {}
```

to:

```python
    stored = 0
    outcomes: list[dict] = []
    candles_by_symbol: dict = {}
    newly_confirmed_signals: list = []
```

Change:

```python
                if result.signal is not None:
                    stored += 1
                    maybe_send_alert(result.signal, settings, cfg)
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "CONFIRMED",
                        "extra": f"{result.signal.direction.upper()} {result.signal.confidence}%",
                    })
```

to:

```python
                if result.signal is not None:
                    stored += 1
                    newly_confirmed_signals.append(result.signal)
                    maybe_send_alert(result.signal, settings, cfg)
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "CONFIRMED",
                        "extra": f"{result.signal.direction.upper()} {result.signal.confidence}%",
                    })
```

Change:

```python
        # After scanning both sessions, settle open signals whose TP or SL has
        # been hit and expire stale ones (per-session window), reusing this
        # run's candles where they already cover a signal's life.
        for row, outcome in track_open_signals(cfg, prefetched=candles_by_symbol,
                                               session=db_session):
```

to:

```python
        # Cross-strategy confirmation: runs once, after every session has
        # scanned, so it sees the full picture of what just got confirmed.
        # Never allowed to block the three real sessions' delivery, which
        # has already completed by this point.
        try:
            for confluence_signal in detect_confluence(
                newly_confirmed_signals, candles_by_symbol, settings, cfg,
                session=db_session,
            ):
                stored += 1
                outcomes.append({
                    "symbol": confluence_signal.symbol,
                    "timeframe": "confluence",
                    "status": "CONFIRMED",
                    "extra": f"{confluence_signal.direction.upper()} "
                             f"{confluence_signal.confidence}% (confluence)",
                })
        except Exception as exc:
            print(f"confluence detection failed ({type(exc).__name__}), continuing")

        # After scanning both sessions, settle open signals whose TP or SL has
        # been hit and expire stale ones (per-session window), reusing this
        # run's candles where they already cover a signal's life.
        for row, outcome in track_open_signals(cfg, prefetched=candles_by_symbol,
                                               session=db_session):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_pipeline.py -v`
Expected: all pass (no regressions in the pre-existing tests, plus the 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add signals/pipeline/engine.py tests/core/test_pipeline.py
git commit -m "feat(confluence): wire detection into the engine run"
```

---

## Task 5: Telegram confluence badge

**Files:**
- Modify: `signals/clients/telegram.py`
- Test: `tests/core/test_telegram.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_telegram.py`, after `test_format_alert_short_uses_red_and_escapes_html`:

```python
def _confluence_signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=108240.0,
        stop_loss=106900.0, take_profit=110920.0,
        indicators={"strategy": "cloud_mss",
                    "confluence_of": ["cloud_mss@15m", "msnr@1h"],
                    "source_timeframe": "15m"},
    )
    confirmation = Confirmation("confirm", 75, "Two strategies agree.")
    return make_signal(setup, confirmation, [], timeframe="confluence")


def test_format_alert_shows_confluence_badge_when_tagged():
    text = format_alert(_confluence_signal())
    assert "CONFLUENCE" in text
    assert "cloud_mss@15m" in text
    assert "msnr@1h" in text


def test_format_alert_omits_confluence_badge_for_normal_signal():
    text = format_alert(_signal())
    assert "CONFLUENCE" not in text


def test_format_caption_shows_confluence_badge_when_tagged():
    text = format_caption(_confluence_signal())
    assert "CONFLUENCE" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_telegram.py -k confluence -v`
Expected: FAIL — `AssertionError: assert 'CONFLUENCE' in text` (badge doesn't exist yet)

- [ ] **Step 3: Implement**

In `signals/clients/telegram.py`, add a helper near the other small formatting helpers (`_direction_dot`, `_confidence_bar`, etc.):

```python
def _confluence_badge(signal: Signal) -> str:
    """A short banner line when `signal` is a confluence publish -- empty
    string for every ordinary signal."""
    tags = (signal.indicators or {}).get("confluence_of")
    if not tags:
        return ""
    names = " + ".join(_esc(str(t)) for t in tags)
    return f"\U0001F525 <b>CONFLUENCE</b>  {names}\n\n"
```

In `format_alert`, change:

```python
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    symbol = _esc(signal.symbol)
    timeframe = _esc(signal.timeframe)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    return (
        f"{dot} <b>{direction} SIGNAL</b>\n"
```

to:

```python
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    symbol = _esc(signal.symbol)
    timeframe = _esc(signal.timeframe)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    badge = _confluence_badge(signal)
    return (
        f"{badge}{dot} <b>{direction} SIGNAL</b>\n"
```

In `format_caption`, change:

```python
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    return (
        f"{dot} <b>{direction} SIGNAL</b>\n"
```

to:

```python
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    badge = _confluence_badge(signal)
    return (
        f"{badge}{dot} <b>{direction} SIGNAL</b>\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_telegram.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add signals/clients/telegram.py tests/core/test_telegram.py
git commit -m "feat(confluence): badge confluence alerts in Telegram formatting"
```

---

## Task 6: Fix outcome tracking for confluence rows

**Files:**
- Modify: `signals/outcomes/tracker.py`
- Modify: `signals/persistence/signals.py` (add `indicators` to the backfill select)
- Test: `tests/core/test_outcome.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_outcome.py`, after `test_track_prefetch_key_includes_timeframe`:

```python
def test_track_uses_source_timeframe_for_confluence_rows(monkeypatch):
    row = _live_row(
        days_old=1, timeframe="confluence", id="conf-1",
        indicators={"strategy": "cloud_mss", "source_timeframe": "15m"},
    )
    intervals = []

    monkeypatch.setattr(outcome_tracker, "list_open_signals",
                        lambda url, key, session=None: [row])

    def fake_fetch(symbol, interval, limit, start_time=None, session=None):
        intervals.append(interval)
        return _candles_from(
            datetime.now(timezone.utc) - timedelta(days=1), hours=24,
            high=111.0)

    monkeypatch.setattr(outcome_tracker, "fetch_candles", fake_fetch)
    closes = []

    def fake_update(sig_id, status, closed_at, url, key, session=None,
                    terminal=True, expected_status=None):
        closes.append((sig_id, status))
        return True

    monkeypatch.setattr(outcome_tracker, "update_signal_outcome", fake_update)

    track_open_signals(_config())

    # Must fetch the real interval, never the literal "confluence" string --
    # fetch_candles raises ValueError on any interval it doesn't recognize.
    assert intervals == ["15m"]
    assert closes == [("conf-1", "tp_hit")]


def test_track_confluence_row_keeps_its_own_14_day_expiry(monkeypatch):
    # source_timeframe=5m would normally expire in 1 day (super_scalp's
    # window) -- the confluence row itself must keep the registered
    # confluence session's 14-day window regardless of which session
    # triggered it.
    row = _live_row(
        days_old=10, timeframe="confluence", id="conf-2",
        indicators={"strategy": "ict_fvg", "source_timeframe": "5m"},
    )
    quiet = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=10), hours=48)

    closed, fetches, closes, _ = _track(
        monkeypatch, [row], fetched_candles=quiet)

    assert closes == []  # still open at 10 days; would be "expired" at 1 day


def test_backfill_missing_outcome_charts_uses_source_timeframe_for_confluence(monkeypatch):
    row = _chart_backfill_row(
        timeframe="confluence",
        indicators={"strategy": "msnr", "source_timeframe": "1h"},
    )
    monkeypatch.setattr(outcome_tracker, "list_signals_missing_outcome_chart",
                        lambda *a, **k: [row])
    intervals = []

    def fake_fetch(symbol, timeframe, limit, start_time=None, session=None):
        intervals.append(timeframe)
        return [Candle(open_time=0, open=100, high=103, low=98,
                       close=101, volume=0.0)]

    monkeypatch.setattr(outcome_tracker, "fetch_candles", fake_fetch)
    monkeypatch.setattr(outcome_tracker, "attach_outcome_chart",
                        lambda *a, **k: "http://x/s1-outcome.png")
    monkeypatch.setattr(outcome_tracker, "set_outcome_chart_url",
                        lambda *a, **k: None)

    outcome_tracker.backfill_missing_outcome_charts(_BackfillCfg())

    assert intervals == ["1h"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_outcome.py -k confluence -v`
Expected: FAIL — `intervals == ["confluence"]` (or the fetch raising), not `["15m"]`/`["1h"]`

- [ ] **Step 3: Implement the tracker fix**

In `signals/outcomes/tracker.py`, inside `track_open_signals`, change:

```python
    for row in open_rows:
        symbol = row["symbol"]
        timeframe = row.get("timeframe") or "1h"
        session_cfg = _SESSION_BY_TIMEFRAME.get(timeframe)
        max_open = session_cfg.max_open if session_cfg else _DEFAULT_MAX_OPEN
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + max_open
        # A limit fill needs its own entry bar in the window. Reach back two
        # bars rather than one so the fetch lands before that bar's open
        # whatever the delay between bar close and row write; _scan_start then
        # trims to the exact bar by position.
        include_entry_bar = fills_intrabar(row)
        bar_ms = TIMEFRAME_MINUTES.get(timeframe, 60) * 60_000
        from_ms = created_ms - 2 * bar_ms if include_entry_bar else created_ms
        candles = candles_covering(symbol, timeframe, from_ms)
```

to:

```python
    for row in open_rows:
        symbol = row["symbol"]
        timeframe = row.get("timeframe") or "1h"
        session_cfg = _SESSION_BY_TIMEFRAME.get(timeframe)
        max_open = session_cfg.max_open if session_cfg else _DEFAULT_MAX_OPEN
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + max_open
        # Confluence rows carry a synthetic "confluence" timeframe (so they
        # never collide with a real session's one-open-per-symbol lock), but
        # their entry/SL/TP came from a real interval stashed at creation
        # time -- candle fetches must use that real interval, or every
        # fetch_candles call raises and the row never settles (not even
        # expiry -- see the design doc's Delivery section). Expiry itself
        # still uses the registered `confluence` session's own max_open,
        # from `timeframe` above, not the source interval's.
        fetch_timeframe = timeframe
        if timeframe == "confluence":
            fetch_timeframe = (row.get("indicators") or {}).get(
                "source_timeframe", "1h")
        # A limit fill needs its own entry bar in the window. Reach back two
        # bars rather than one so the fetch lands before that bar's open
        # whatever the delay between bar close and row write; _scan_start then
        # trims to the exact bar by position.
        include_entry_bar = fills_intrabar(row)
        bar_ms = TIMEFRAME_MINUTES.get(fetch_timeframe, 60) * 60_000
        from_ms = created_ms - 2 * bar_ms if include_entry_bar else created_ms
        candles = candles_covering(symbol, fetch_timeframe, from_ms)
```

In the same file, inside `backfill_missing_outcome_charts`, change:

```python
    backfilled = 0
    for row in rows:
        symbol = row["symbol"]
        timeframe = row.get("timeframe") or "1h"
        created_ms = datetime.fromisoformat(row["created_at"]).timestamp() * 1000
        try:
            candles = fetch_candles(symbol, timeframe, HISTORY_LIMIT,
                                    start_time=int(created_ms), session=session)
```

to:

```python
    backfilled = 0
    for row in rows:
        symbol = row["symbol"]
        timeframe = row.get("timeframe") or "1h"
        fetch_timeframe = timeframe
        if timeframe == "confluence":
            fetch_timeframe = (row.get("indicators") or {}).get(
                "source_timeframe", "1h")
        created_ms = datetime.fromisoformat(row["created_at"]).timestamp() * 1000
        try:
            candles = fetch_candles(symbol, fetch_timeframe, HISTORY_LIMIT,
                                    start_time=int(created_ms), session=session)
```

- [ ] **Step 4: Add `indicators` to the backfill query's select**

`backfill_missing_outcome_charts` reads `row.get("indicators")`, but `list_signals_missing_outcome_chart` in `signals/persistence/signals.py` doesn't currently select that column -- without this, every confluence row silently falls back to the wrong interval. Change:

```python
        "&select=id,symbol,timeframe,direction,entry,stop_loss,"
        "take_profit,take_profit_1,take_profit_2,take_profit_3,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,closed_at"
        f"&order=closed_at.desc&limit={limit}",
```

to:

```python
        "&select=id,symbol,timeframe,direction,entry,stop_loss,"
        "take_profit,take_profit_1,take_profit_2,take_profit_3,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,closed_at,"
        "indicators"
        f"&order=closed_at.desc&limit={limit}",
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_outcome.py -v`
Expected: all pass (existing tests plus the 3 new ones)

- [ ] **Step 6: Commit**

```bash
git add signals/outcomes/tracker.py signals/persistence/signals.py tests/core/test_outcome.py
git commit -m "fix(confluence): settle confluence rows using their real source interval"
```

---

## Task 7: Verify web read paths

Confluence signals must not silently vanish from (or corrupt) the public track record, and must not appear on a dashboard tab that was never designed to show them.

**Files:** none modified -- verification only, plus one doc comment.

- [ ] **Step 1: Confirm `/track-record`'s query has no timeframe filter**

Run: `grep -n "timeframe" web/src/lib/track-record.ts`

Expected: the `fetchClosedRows` query (the one building `select=id,symbol,timeframe,...`) has no `&timeframe=` clause anywhere in its query string -- confirming a closed confluence signal (`shadow=is.false`, a real closed status) will be pulled into the public track record's stats automatically, including its own row in the `byTimeframe` breakdown table. If a `&timeframe=` filter has been added to that query since this plan was written, stop and re-evaluate -- it would silently exclude confluence rows from the public track record.

- [ ] **Step 2: Confirm `/signals` dashboard tabs require an explicit timeframe**

Run: `grep -n "sessionQuery\|function sessionQuery" web/src/lib/signals.ts`

Expected: `sessionQuery(timeframe?: string, ...)` only returns a `timeframe=eq.X` filter when a caller passes one; every existing tab (Super Scalp, Scalp, Swing, War Room, BBMA) passes its own fixed timeframe. Confirms that without a new tab, confluence signals will not appear in any existing `/signals` tab -- which is correct for this plan (no dedicated UI tab is in scope for v1; confluence is Telegram delivery + track-record aggregate stats only).

- [ ] **Step 3: Document the intentional scope boundary**

In `web/src/lib/signals.ts`, find the block of comments above `EXCLUDE_WAR_ROOM`/`WAR_ROOM_ONLY` (around line 132) and add one line after the existing BBMA-lane comments:

```typescript
// Confluence signals (timeframe=confluence) are Telegram + track-record
// only in v1 -- no dashboard tab queries for them yet. See
// docs/superpowers/specs/2026-08-14-strategy-confluence-signal-design.md.
```

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/signals.ts
git commit -m "docs(confluence): note the intentional no-dashboard-tab scope boundary"
```

---

## Task 8: End-to-end verification

- [ ] **Step 1: Full Python suite**

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/ml`
Expected: all pass (the `tests/ml` skip is pre-existing on this machine, unrelated to this work)

- [ ] **Step 2: Web type-check**

Run: `cd web && ./node_modules/.bin/tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Confirm the spec's testing checklist is covered**

Re-read `docs/superpowers/specs/2026-08-14-strategy-confluence-signal-design.md`'s Testing section and confirm each item maps to a test written in this plan:
- Different-strategy requirement → `test_open_signals_same_direction_excludes_matching_strategy` / `..._empty_when_only_same_strategy_open`
- Direction match (implicit in the query's `direction=eq.` filter) → covered by the same tests above (only same-symbol+direction rows are ever returned)
- Shadow/confluence-row exclusion → `shadow=is.false` and `timeframe=neq.confluence` assertions in Task 1
- One-open-confluence-per-symbol guard → `test_detect_confluence_skips_when_confluence_already_open`
- Engine-level: confluence created from two strategies agreeing → `test_main_calls_detect_confluence_with_newly_confirmed_signals` / `..._folds_published_confluence_signals_into_run_summary`
- A forced exception doesn't block the run → `test_main_confluence_failure_does_not_block_run`

If any item lacks a corresponding test, add it before moving on -- do not close this task with a gap between the spec's stated testing bar and what actually exists.

- [ ] **Step 4: Manual smoke check (optional, requires live credentials)**

If you have Supabase credentials available: manually insert two open signals for the same test symbol+direction from two different strategies (mirroring the probe pattern in `scripts/verify_shadow_rls.py` -- insert with the service-role key, clean up immediately after), then run `signals.pipeline.confluence.detect_confluence` against them directly in a Python shell and confirm a `confluence` row appears and gets a Telegram alert (or set `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHANNEL_ID` empty first if you don't want a real alert sent during the check). Delete all probe rows afterward.

---

## Verification checklist

- [ ] `.venv/bin/python -m pytest tests/ -q --ignore=tests/ml` passes
- [ ] `cd web && ./node_modules/.bin/tsc --noEmit` exits 0
- [ ] Every item in the spec's Testing section maps to an actual test
- [ ] `TRADING_SESSIONS` and the three strategy detectors are untouched -- this work is additive only to the three real sessions' own detection/confirmation/delivery
- [ ] The confluence pass in `engine.py` is wrapped in try/except and a forced failure there does not prevent `save_engine_run` from being called
