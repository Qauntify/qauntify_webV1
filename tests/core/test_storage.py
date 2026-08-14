import pytest

from signals.models import BotSettings, CandidateSetup, Confirmation, make_signal
from signals.persistence.cleanup import delete_rows_older_than
from signals.persistence.events import save_debate, save_xau_scan_run
from signals.persistence.settings import fetch_bot_settings
from signals.persistence.signals import (
    list_signals_missing_outcome_chart,
    save_signal,
    update_signal_outcome,
)


def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])


def test_save_debate_posts_row_to_agent_debates():
    session = FakeSession()
    debate = {
        "signal_id": "sig-1", "symbol": "XAUUSD", "timeframe": "1h",
        "direction": "long",
        "transcript": [{"agent": "Manager", "avatar": "🧑‍💼", "message": "take it"}],
        "manager_verdict": "agree", "manager_confidence": 70,
    }
    save_debate(debate, "https://abc.supabase.co", "service-key", session=session)
    assert session.last_url == "https://abc.supabase.co/rest/v1/agent_debates"
    body = session.last_json
    assert body["symbol"] == "XAUUSD"
    assert body["manager_verdict"] == "agree"
    assert body["manager_confidence"] == 70
    assert body["transcript"][0]["agent"] == "Manager"
    assert body["signal_id"] == "sig-1"
    assert "id" in body and "created_at" in body


class FakeResponse:
    def __init__(self, status=201, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, status=201, payload=None):
        self._status = status
        self._payload = payload
        self.last_method = None
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeResponse(self._status)

    def patch(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeResponse(self._status, self._payload)

    def delete(self, url, headers=None, timeout=None):
        self.last_method = "DELETE"
        self.last_url = url
        self.last_headers = headers
        return FakeResponse(self._status)


def test_save_signal_posts_row_to_supabase():
    session = FakeSession()
    signal = _signal()

    save_signal(signal, "https://abc.supabase.co", "service-key", session=session)

    assert session.last_url == "https://abc.supabase.co/rest/v1/signals"
    assert session.last_headers["apikey"] == "service-key"
    assert session.last_headers["Authorization"] == "Bearer service-key"
    assert session.last_headers["Prefer"] == "return=minimal"
    body = session.last_json
    assert body["id"] == signal.id
    assert body["symbol"] == "BTCUSDT"
    assert body["direction"] == "long"
    assert body["entry"] == 100.0
    assert body["confidence"] == 80
    assert body["indicators"]["rsi"] == 55.0  # jsonb: sent as an object, not a string
    assert body["news_headlines"] == ["headline one"]
    assert body["created_at"] == signal.created_at


def test_save_signal_raises_on_http_error():
    session = FakeSession(status=401)
    with pytest.raises(RuntimeError):
        save_signal(_signal(), "https://abc.supabase.co", "bad-key", session=session)


def test_save_xau_scan_run_posts_row_to_supabase():
    session = FakeSession()
    run = {
        "id": "run-uuid-1",
        "run_id": "20260804T120000Z",
        "signal_found": True,
        "finished_at": "2026-08-04T12:00:00+00:00",
    }

    save_xau_scan_run(run, "https://abc.supabase.co", "service-key", session=session)

    assert session.last_url == "https://abc.supabase.co/rest/v1/xau_scan_runs"
    assert session.last_headers["apikey"] == "service-key"
    assert session.last_headers["Authorization"] == "Bearer service-key"
    assert session.last_headers["Prefer"] == "return=minimal"
    assert session.last_json == run


def test_save_xau_scan_run_raises_on_http_error():
    session = FakeSession(status=500)
    with pytest.raises(RuntimeError):
        save_xau_scan_run(
            {"id": "run-uuid-1", "run_id": "x", "signal_found": False,
             "finished_at": "2026-08-04T12:00:00+00:00"},
            "https://abc.supabase.co", "bad-key", session=session,
        )


def test_update_signal_outcome_unconditional_unchanged():
    session = FakeSession()
    result = update_signal_outcome(
        "sig-1", "sl_hit", "2026-08-04T12:00:00+00:00",
        "https://abc.supabase.co", "key", terminal=True, session=session,
    )
    assert result is None
    assert "status=eq." not in session.last_url
    assert session.last_headers["Prefer"] == "return=minimal"


def test_update_signal_outcome_conditional_claim_succeeds():
    session = FakeSession(payload=[{"id": "sig-1", "status": "sl_hit"}])
    result = update_signal_outcome(
        "sig-1", "sl_hit", "2026-08-04T12:00:00+00:00",
        "https://abc.supabase.co", "key", terminal=True,
        expected_status="open", session=session,
    )
    assert result is True
    assert "status=eq.open" in session.last_url
    assert session.last_headers["Prefer"] == "return=representation"


def test_update_signal_outcome_conditional_claim_fails_when_already_moved():
    session = FakeSession(payload=[])
    result = update_signal_outcome(
        "sig-1", "sl_hit", "2026-08-04T12:00:00+00:00",
        "https://abc.supabase.co", "key", terminal=True,
        expected_status="open", session=session,
    )
    assert result is False


class FakeGetSession:
    def __init__(self, payload=None, status=200, patch_payload=None):
        self._payload = payload
        self._status = status
        self._patch_payload = patch_payload if patch_payload is not None else [{"id": "x"}]
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def get(self, url, headers=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        response = FakeResponse(self._status)
        response.json = lambda: self._payload
        return response

    def patch(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        response = FakeResponse(200, self._patch_payload)
        response.json = lambda: self._patch_payload
        return response


def test_fetch_bot_settings_reads_row():
    session = FakeGetSession(
        payload=[{
            "symbols": ["btcusdt", "SOLUSDT"],
            "min_alert_confidence": 75,
            "signal_strategy": "ict_smc",
        }],
    )
    settings = fetch_bot_settings(
        "https://abc.supabase.co", "service-key", session=session,
    )
    assert settings.symbols == ("BTCUSD", "SOLUSD")
    assert settings.min_alert_confidence == 75
    assert settings.min_store_confidence == 0
    assert settings.signal_strategy == "ict_smc"
    assert "bot_settings" in session.last_url
    assert session.last_headers["apikey"] == "service-key"


def test_fetch_bot_settings_reads_store_confidence():
    session = FakeGetSession(
        payload=[{
            "symbols": ["BTCUSDT"],
            "min_alert_confidence": 80,
            "min_store_confidence": 60,
            "signal_strategy": "ema_cross",
        }],
    )
    settings = fetch_bot_settings(
        "https://abc.supabase.co", "service-key", session=session,
    )
    assert settings.min_store_confidence == 60
    assert settings.min_alert_confidence == 80


def test_fetch_bot_settings_defaults_unknown_strategy():
    session = FakeGetSession(
        payload=[{
            "symbols": ["BTCUSDT"],
            "min_alert_confidence": 50,
            "signal_strategy": "unknown",
        }],
    )
    settings = fetch_bot_settings(
        "https://abc.supabase.co", "service-key", session=session,
    )
    assert settings.signal_strategy == "ema_cross"


def test_fetch_bot_settings_defaults_on_http_error():
    session = FakeGetSession(status=404)
    settings = fetch_bot_settings(
        "https://abc.supabase.co", "service-key", session=session,
    )
    assert settings == BotSettings()


def test_fetch_bot_settings_defaults_on_malformed_row():
    session = FakeGetSession(payload=[{"symbols": [], "min_alert_confidence": 50}])
    settings = fetch_bot_settings(
        "https://abc.supabase.co", "service-key", session=session,
    )
    assert settings == BotSettings()


def test_latest_signal_filters_by_timeframe():
    session = FakeGetSession(payload=[])
    from signals.persistence.signals import latest_signal

    latest_signal("BTCUSDT", "https://abc.supabase.co", "key",
                  timeframe="15m", session=session)
    assert "timeframe=eq.15m" in session.last_url


def test_list_open_signals_selects_timeframe():
    session = FakeGetSession(payload=[])
    from signals.persistence.signals import list_open_signals

    list_open_signals("https://abc.supabase.co", "key", session=session)
    assert "timeframe" in session.last_url


def test_latest_ai_event_time_returns_created_at_for_symbol_and_timeframe():
    session = FakeGetSession(
        payload=[{"created_at": "2026-07-08T09:00:00+00:00"}])
    from signals.persistence.events import latest_ai_event_time

    result = latest_ai_event_time(
        "BTCUSDT", "1h", "https://abc.supabase.co", "key", session=session)
    assert result == "2026-07-08T09:00:00+00:00"
    assert "symbol=eq.BTCUSDT" in session.last_url
    assert "timeframe=eq.1h" in session.last_url
    assert "ai_events" in session.last_url


def test_latest_ai_event_time_none_when_no_history():
    session = FakeGetSession(payload=[])
    from signals.persistence.events import latest_ai_event_time

    result = latest_ai_event_time(
        "BTCUSDT", "1h", "https://abc.supabase.co", "key", session=session)
    assert result is None


def test_latest_ai_event_times_since_batches_one_query_for_all_symbols():
    from signals.persistence.events import latest_ai_event_times_since

    # Two rows for BTCUSDT (newest first within the group), one for ETHUSDT;
    # SOLUSDT has none.
    session = FakeGetSession(payload=[
        {"symbol": "BTCUSDT", "created_at": "2026-07-09T10:00:00+00:00"},
        {"symbol": "BTCUSDT", "created_at": "2026-07-09T09:00:00+00:00"},
        {"symbol": "ETHUSDT", "created_at": "2026-07-09T08:00:00+00:00"},
    ])

    result = latest_ai_event_times_since(
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "1h",
        "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=session,
    )

    assert result == {
        "BTCUSDT": "2026-07-09T10:00:00+00:00",
        "ETHUSDT": "2026-07-09T08:00:00+00:00",
    }
    assert "symbol=in.(BTCUSDT,ETHUSDT,SOLUSDT)" in session.last_url
    assert "timeframe=eq.1h" in session.last_url
    assert "created_at=gte.2026-07-09T00%3A00%3A00%2B00%3A00" in session.last_url
    assert "order=symbol.asc,created_at.desc" in session.last_url


def test_latest_ai_event_times_since_empty_symbols_skips_request():
    class ExplodingSession:
        def get(self, *a, **k):
            raise AssertionError("no request should be made for an empty symbol list")

    from signals.persistence.events import latest_ai_event_times_since

    result = latest_ai_event_times_since(
        [], "1h", "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=ExplodingSession(),
    )
    assert result == {}


def test_latest_signals_since_batches_one_query_for_all_symbols():
    from signals.persistence.signals import latest_signals_since

    session = FakeGetSession(payload=[
        {"symbol": "BTCUSDT", "direction": "long",
         "created_at": "2026-07-09T10:00:00+00:00"},
        {"symbol": "BTCUSDT", "direction": "short",
         "created_at": "2026-07-09T09:00:00+00:00"},
    ])

    result = latest_signals_since(
        ["BTCUSDT", "ETHUSDT"], "15m", "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=session,
    )

    assert result == {
        "BTCUSDT": {"symbol": "BTCUSDT", "direction": "long",
                    "created_at": "2026-07-09T10:00:00+00:00"},
    }
    assert "ETHUSDT" not in result
    assert "symbol=in.(BTCUSDT,ETHUSDT)" in session.last_url
    assert "timeframe=eq.15m" in session.last_url


def test_list_closed_signals_filters_terminal_statuses():
    from signals.persistence.signals import list_closed_signals

    session = FakeGetSession(payload=[
        {"symbol": "BTCUSDT", "status": "tp_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ])
    rows = list_closed_signals("https://abc.supabase.co", "key", session=session)

    assert rows == [
        {"symbol": "BTCUSDT", "status": "tp_hit"},
        {"symbol": "ETHUSDT", "status": "sl_hit"},
    ]
    assert "status.in.(tp_hit,tp3_hit,sl_hit,expired)" in session.last_url
    assert "tp1_hit,tp2_hit" in session.last_url
    assert session.last_headers["apikey"] == "key"


def test_latest_signals_since_empty_symbols_skips_request():
    class ExplodingSession:
        def get(self, *a, **k):
            raise AssertionError("no request should be made for an empty symbol list")

    from signals.persistence.signals import latest_signals_since

    result = latest_signals_since(
        [], "1h", "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=ExplodingSession(),
    )
    assert result == {}


def test_set_outcome_chart_url_patches_row():
    from signals.persistence.signals import set_outcome_chart_url

    class _Resp:
        status_code = 200
        def raise_for_status(self):
            return None

    class _Sess:
        def __init__(self):
            self.calls = []
        def patch(self, url, headers=None, json=None, timeout=None):
            self.calls.append({"url": url, "json": json})
            return _Resp()

    s = _Sess()
    set_outcome_chart_url("sig-1", "http://x/sig-1-outcome.png",
                          "https://p.supabase.co", "key", session=s)
    assert "id=eq.sig-1" in s.calls[0]["url"]
    assert s.calls[0]["json"] == {"outcome_chart_url": "http://x/sig-1-outcome.png"}


def test_save_signal_marks_shadow_rows():
    """Shadow rows are LLM-rejected setups recorded for the gate A/B."""
    session = FakeSession()
    save_signal(_signal(), "https://abc.supabase.co", "service-key",
                session=session, shadow=True)
    assert session.last_json["shadow"] is True


def test_save_signal_defaults_to_visible():
    """Anything not explicitly a shadow must be deliverable as normal."""
    session = FakeSession()
    save_signal(_signal(), "https://abc.supabase.co", "service-key",
                session=session)
    assert session.last_json["shadow"] is False


def _query_of(session):
    return session.last_url


def test_dedup_queries_ignore_shadow_rows():
    """A shadow signal must never suppress a real one.

    open_symbols_for_timeframe / latest_signal / latest_signals_since drive the
    duplicate guard and run with the service-role key, which bypasses RLS. If
    they saw shadows, an LLM-rejected setup stored as 'open' would make the
    engine skip a genuine confirmed setup for that symbol — the experiment
    would silently change what gets traded.
    """
    from signals.persistence.signals import (
        latest_signal, latest_signals_since, open_symbols_for_timeframe,
    )

    s1 = FakeGetSession(payload=[])
    open_symbols_for_timeframe(["BTCUSD"], "15m", "https://abc.supabase.co",
                               "k", session=s1)
    assert "shadow=is.false" in _query_of(s1)

    s2 = FakeGetSession(payload=[])
    latest_signal("BTCUSD", "https://abc.supabase.co", "k",
                  timeframe="15m", session=s2)
    assert "shadow=is.false" in _query_of(s2)

    s3 = FakeGetSession(payload=[])
    latest_signals_since(["BTCUSD"], "15m", "2026-07-01T00:00:00Z",
                         "https://abc.supabase.co", "k", session=s3)
    assert "shadow=is.false" in _query_of(s3)


def test_outcome_polling_still_sees_shadow_rows():
    """Shadows MUST be polled — that is how their outcome gets recorded."""
    from signals.persistence.signals import list_open_signals

    session = FakeGetSession(payload=[])
    list_open_signals("https://abc.supabase.co", "k", session=session)
    assert "shadow" not in _query_of(session)


def test_list_signals_missing_outcome_chart_queries_closed_without_chart():
    session = FakeGetSession(payload=[{"id": "sig-1", "symbol": "XAUUSD"}])
    rows = list_signals_missing_outcome_chart(
        "https://abc.supabase.co", "key", limit=20, session=session)
    assert rows == [{"id": "sig-1", "symbol": "XAUUSD"}]
    query = _query_of(session)
    assert "closed_at=not.is.null" in query
    assert "outcome_chart_url=is.null" in query
    assert "limit=20" in query


def test_upsert_mt5_last_tick_posts_merge():
    from signals.persistence.mt5 import upsert_mt5_last_tick

    session = FakeSession()
    upsert_mt5_last_tick(
        "XAUUSD", tick_time_iso="2026-08-05T03:00:00+00:00",
        supabase_url="https://abc.supabase.co", service_key="service-key",
        session=session, bid=4120.0, ask=4120.4,
    )
    assert session.last_url.endswith("/mt5_last_ticks")
    assert "merge-duplicates" in session.last_headers["Prefer"]
    assert session.last_json["symbol"] == "XAUUSD"
    assert session.last_json["bid"] == 4120.0
    assert session.last_json["ask"] == 4120.4
    assert session.last_json["mid"] == 4120.2
    assert session.last_json["price"] == 4120.2


def test_mt5_tick_is_fresh():
    from datetime import datetime, timedelta, timezone

    from signals.persistence.mt5 import mt5_tick_is_fresh

    now = datetime.now(timezone.utc)
    fresh = {"price": 1.0, "tick_time": now.isoformat()}
    stale = {
        "price": 1.0,
        "tick_time": (now - timedelta(seconds=120)).isoformat(),
    }
    assert mt5_tick_is_fresh(fresh) is True
    assert mt5_tick_is_fresh(stale) is False
    assert mt5_tick_is_fresh(None) is False


def test_fetch_mt5_last_tick_parses_row():
    from signals.persistence.mt5 import fetch_mt5_last_tick

    session = FakeGetSession(payload=[{
        "symbol": "XAUUSD", "price": 4121.1, "bid": 4121.0, "ask": 4121.2,
        "mid": 4121.1,
        "tick_time": "2026-08-05T03:00:00Z", "updated_at": "2026-08-05T03:00:01Z",
    }])
    row = fetch_mt5_last_tick(
        "XAUUSD", "https://abc.supabase.co", "k", session=session,
    )
    assert row["mid"] == 4121.1
    assert row["bid"] == 4121.0
    assert "mt5_last_ticks" in session.last_url


def test_expire_drifted_open_gold_signals():
    from signals.persistence.mt5 import expire_drifted_open_gold_signals

    session = FakeGetSession(
        payload=[{
            "id": "sig-1", "symbol": "XAUUSD", "status": "open",
            "entry": 4154.0, "timeframe": "1m",
        }],
        patch_payload=[{"id": "sig-1"}],
    )
    n = expire_drifted_open_gold_signals(
        4120.0, "https://abc.supabase.co", "k", session=session,
    )
    assert n == 1
    assert session.last_json["status"] == "expired"


def test_merge_mt5_candle_bars_dedupes_and_caps():
    from signals.persistence.mt5 import merge_mt5_candle_bars

    existing = [
        {"open_time": 100, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1},
        {"open_time": 160, "open": 1.5, "high": 2, "low": 1, "close": 1.8, "volume": 1},
    ]
    incoming = [
        {"open_time": 160, "open": 1.5, "high": 3, "low": 1, "close": 2.0, "volume": 2},
        {"open_time": 220, "open": 2, "high": 2.5, "low": 1.9, "close": 2.2, "volume": 1},
    ]
    merged = merge_mt5_candle_bars(existing, incoming, max_bars=2)
    assert len(merged) == 2
    assert merged[0]["open_time"] == 160
    assert merged[0]["high"] == 3
    assert merged[1]["open_time"] == 220


def test_mt5_candles_usable_requires_depth_and_freshness():
    from datetime import datetime, timezone

    from signals.persistence.mt5 import mt5_candles_usable

    now = int(datetime.now(timezone.utc).timestamp())
    # Align to minute
    now = now - (now % 60) - 60
    rows = [
        {"open_time": now - 60 * i, "open": 1, "high": 1, "low": 1, "close": 1}
        for i in range(100, 0, -1)
    ]
    assert mt5_candles_usable(rows) is True
    assert mt5_candles_usable(rows[:10]) is False
    stale = [{"open_time": now - 3600, "open": 1, "high": 1, "low": 1, "close": 1}] * 100
    assert mt5_candles_usable(stale) is False


def test_purge_mt5_candle_outliers_drops_far_closes():
    from signals.persistence.mt5 import purge_mt5_candle_outliers

    # Gradual live move 4138→4139, then a discontinuous junk cluster at 4120.
    rows = [
        {"open_time": 1, "open": 4120, "high": 4121, "low": 4119, "close": 4120.0, "volume": 1},
        {"open_time": 2, "open": 4120, "high": 4121, "low": 4119, "close": 4120.5, "volume": 1},
        {"open_time": 3, "open": 4138, "high": 4139, "low": 4137, "close": 4138.5, "volume": 1},
        {"open_time": 4, "open": 4139, "high": 4140, "low": 4138, "close": 4139.2, "volume": 1},
    ]
    kept = purge_mt5_candle_outliers(rows, 4139.2, max_drift=15.0)
    assert len(kept) == 2
    assert kept[0]["close"] == 4138.5
    assert kept[1]["close"] == 4139.2


def test_purge_mt5_candle_outliers_keeps_fast_gold_moves_by_default():
    """Default drift must tolerate a >$15 1m gold step (news / TP rush)."""
    from signals.persistence.mt5 import purge_mt5_candle_outliers

    rows = []
    px = 5050.0
    for i in range(20):
        nxt = px - 18.0  # >$15/bar — the old flat cap shredded this path
        rows.append({
            "open_time": i, "open": px, "high": px + 1, "low": nxt - 1,
            "close": nxt, "volume": 1,
        })
        px = nxt
    kept = purge_mt5_candle_outliers(rows, rows[-1]["close"])
    assert len(kept) == len(rows)


def test_purge_mt5_candle_outliers_still_drops_junk_seed_by_default():
    from signals.persistence.mt5 import purge_mt5_candle_outliers

    rows = [
        {"open_time": 1, "open": 4120, "high": 4121, "low": 4119, "close": 4120.0, "volume": 1},
        {"open_time": 2, "open": 4120, "high": 4121, "low": 4119, "close": 4120.5, "volume": 1},
        {"open_time": 3, "open": 5048, "high": 5050, "low": 5046, "close": 5049.0, "volume": 1},
        {"open_time": 4, "open": 5049, "high": 5051, "low": 5048, "close": 5050.0, "volume": 1},
    ]
    kept = purge_mt5_candle_outliers(rows, 5050.0)
    assert [r["close"] for r in kept] == [5049.0, 5050.0]


def test_delete_rows_older_than_uses_correct_cutoff_and_table():
    from datetime import datetime, timedelta, timezone

    session = FakeSession()
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    delete_rows_older_than("ai_events", "created_at", 90,
                           "https://abc.supabase.co", "key",
                           session=session, now=now)

    assert session.last_method == "DELETE"
    assert session.last_url.startswith("https://abc.supabase.co/rest/v1/ai_events?")
    expected_cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert f"created_at=lt.{expected_cutoff}" in session.last_url
    assert session.last_headers["apikey"] == "key"
    assert session.last_headers["Authorization"] == "Bearer key"


def test_delete_rows_older_than_raises_on_http_error():
    session = FakeSession(status=500)
    with pytest.raises(RuntimeError):
        delete_rows_older_than("ai_events", "created_at", 90,
                               "https://abc.supabase.co", "bad-key",
                               session=session)


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
