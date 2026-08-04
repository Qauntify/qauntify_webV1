"""Unit tests for the realtime tick-orchestration logic.

check_outcome_events / apply_events themselves are already covered by
tests/core/test_outcome.py — these tests only cover the orchestration around
them (cache lookup, when to fetch a chart window, when to alert vs no-op),
monkeypatched at the module level like the rest of this test suite.
"""
from signals import realtime_watcher
from signals.config import Config


def _cfg():
    return Config(
        sealion_api_key="",
        supabase_url="https://abc.supabase.co",
        supabase_service_key="service-key",
        telegram_bot_token="bot-token",
        telegram_channel_id="chat-id",
    )


def _row(symbol="BTCUSD", status="open", **overrides):
    row = {
        "id": "sig-1",
        "symbol": symbol,
        "timeframe": "1h",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "status": status,
        "created_at": "2026-08-04T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_handle_tick_is_a_fast_noop_when_symbol_has_no_open_signals(monkeypatch):
    calls = []
    monkeypatch.setattr(realtime_watcher, "check_outcome_events",
                        lambda *a, **k: calls.append("check") or [])

    watcher = realtime_watcher.RealtimeWatcher(_cfg())
    watcher.cache = {}  # nothing open for any symbol

    watcher.handle_tick("BTCUSD", 105.0, 1_700_000_000_000)

    assert calls == []


def test_handle_tick_checks_but_does_nothing_further_when_no_events(monkeypatch):
    checked = []
    fetched = []
    applied = []
    monkeypatch.setattr(realtime_watcher, "check_outcome_events",
                        lambda row, candles: checked.append(row) or [])
    monkeypatch.setattr(realtime_watcher, "fetch_candles",
                        lambda *a, **k: fetched.append(1) or [])
    monkeypatch.setattr(realtime_watcher, "apply_events",
                        lambda *a, **k: applied.append(1) or (a[0], None))

    watcher = realtime_watcher.RealtimeWatcher(_cfg())
    watcher.cache = {"BTCUSD": [_row()]}

    watcher.handle_tick("BTCUSD", 101.0, 1_700_000_000_000)

    assert len(checked) == 1
    assert fetched == []
    assert applied == []


def test_handle_tick_applies_events_and_updates_cache_when_still_open(monkeypatch):
    row = _row()
    monkeypatch.setattr(realtime_watcher, "check_outcome_events",
                        lambda r, candles: [("tp1_hit", "2026-08-04T12:00:00+00:00")])
    monkeypatch.setattr(realtime_watcher, "fetch_candles",
                        lambda *a, **k: [1, 2, 3])  # dropped-last-bar window

    updated_row = {**row, "status": "tp1_hit"}  # not closed — still open

    def fake_apply(r, events, window, cfg, session=None):
        assert r == row
        assert events == [("tp1_hit", "2026-08-04T12:00:00+00:00")]
        assert window == [1, 2]  # last (still-forming) bar dropped
        return updated_row, "tp1_hit"

    monkeypatch.setattr(realtime_watcher, "apply_events", fake_apply)

    watcher = realtime_watcher.RealtimeWatcher(_cfg())
    watcher.cache = {"BTCUSD": [row]}

    watcher.handle_tick("BTCUSD", 106.0, 1_700_000_000_000)

    assert watcher.cache["BTCUSD"] == [updated_row]


def test_handle_tick_removes_from_cache_once_terminal(monkeypatch):
    row = _row()
    monkeypatch.setattr(realtime_watcher, "check_outcome_events",
                        lambda r, candles: [("sl_hit", "2026-08-04T12:00:00+00:00")])
    monkeypatch.setattr(realtime_watcher, "fetch_candles", lambda *a, **k: [])

    closed_row = {**row, "status": "sl_hit", "closed_at": "2026-08-04T12:00:00+00:00"}
    monkeypatch.setattr(realtime_watcher, "apply_events",
                        lambda *a, **k: (closed_row, "sl_hit"))

    watcher = realtime_watcher.RealtimeWatcher(_cfg())
    watcher.cache = {"BTCUSD": [row]}

    watcher.handle_tick("BTCUSD", 94.0, 1_700_000_000_000)

    assert watcher.cache["BTCUSD"] == []


def test_refresh_cache_groups_open_rows_by_symbol(monkeypatch):
    rows = [_row(symbol="BTCUSD", id="a"), _row(symbol="ETHUSD", id="b"),
           _row(symbol="BTCUSD", id="c")]
    monkeypatch.setattr(realtime_watcher, "list_open_signals",
                        lambda url, key, session=None: rows)

    watcher = realtime_watcher.RealtimeWatcher(_cfg())
    watcher.refresh_cache()

    assert {r["id"] for r in watcher.cache["BTCUSD"]} == {"a", "c"}
    assert {r["id"] for r in watcher.cache["ETHUSD"]} == {"b"}
