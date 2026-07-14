import pytest

from signals.models import BotSettings, CandidateSetup, Confirmation, make_signal
from signals.storage import fetch_bot_settings, save_signal


def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])


class FakeResponse:
    def __init__(self, status=201):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, status=201):
        self._status = status
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
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


class FakeGetSession:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self._status = status
        self.last_url = None
        self.last_headers = None

    def get(self, url, headers=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        response = FakeResponse(self._status)
        response.json = lambda: self._payload
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
    assert settings.symbols == ("BTCUSDT", "SOLUSDT")
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
    from signals.storage import latest_signal

    latest_signal("BTCUSDT", "https://abc.supabase.co", "key",
                  timeframe="15m", session=session)
    assert "timeframe=eq.15m" in session.last_url


def test_list_open_signals_selects_timeframe():
    session = FakeGetSession(payload=[])
    from signals.storage import list_open_signals

    list_open_signals("https://abc.supabase.co", "key", session=session)
    assert "timeframe" in session.last_url


def test_latest_ai_event_time_returns_created_at_for_symbol_and_timeframe():
    session = FakeGetSession(
        payload=[{"created_at": "2026-07-08T09:00:00+00:00"}])
    from signals.storage import latest_ai_event_time

    result = latest_ai_event_time(
        "BTCUSDT", "1h", "https://abc.supabase.co", "key", session=session)
    assert result == "2026-07-08T09:00:00+00:00"
    assert "symbol=eq.BTCUSDT" in session.last_url
    assert "timeframe=eq.1h" in session.last_url
    assert "ai_events" in session.last_url


def test_latest_ai_event_time_none_when_no_history():
    session = FakeGetSession(payload=[])
    from signals.storage import latest_ai_event_time

    result = latest_ai_event_time(
        "BTCUSDT", "1h", "https://abc.supabase.co", "key", session=session)
    assert result is None


def test_latest_ai_event_times_since_batches_one_query_for_all_symbols():
    from signals.storage import latest_ai_event_times_since

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

    from signals.storage import latest_ai_event_times_since

    result = latest_ai_event_times_since(
        [], "1h", "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=ExplodingSession(),
    )
    assert result == {}


def test_latest_signals_since_batches_one_query_for_all_symbols():
    from signals.storage import latest_signals_since

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
    assert "status=in.(tp_hit,tp3_hit,sl_hit,expired)" in session.last_url
    assert session.last_headers["apikey"] == "key"


def test_latest_signals_since_empty_symbols_skips_request():
    class ExplodingSession:
        def get(self, *a, **k):
            raise AssertionError("no request should be made for an empty symbol list")

    from signals.storage import latest_signals_since

    result = latest_signals_since(
        [], "1h", "2026-07-09T00:00:00+00:00",
        "https://abc.supabase.co", "key", session=ExplodingSession(),
    )
    assert result == {}
