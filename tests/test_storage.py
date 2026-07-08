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
    assert settings.signal_strategy == "ict_smc"
    assert "bot_settings" in session.last_url
    assert session.last_headers["apikey"] == "service-key"


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
