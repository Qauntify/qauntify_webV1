import pytest

from signals.config import Config
from signals.models import BotSettings, CandidateSetup, Confirmation, make_signal
from signals.run import maybe_send_alert
from signals.telegram_client import format_alert, send_alert


def _signal(direction="long", confidence=80, rationale="Looks good."):
    setup = CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=108240.0,
        stop_loss=106900.0, take_profit=110920.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", confidence, rationale)
    return make_signal(setup, confirmation, ["headline one"])


class FakeResponse:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, status=200):
        self._status = status
        self.last_url = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_json = json
        return FakeResponse(self._status)


def test_format_alert_contains_trade_details():
    text = format_alert(_signal())
    assert "<b>LONG BTCUSDT</b>" in text
    assert "(1h)" in text
    assert "Entry 108240 | SL 106900 | TP 110920" in text
    assert "Confidence 80%" in text
    assert "Looks good." in text
    assert text.startswith("\U0001F7E2")


def test_format_alert_short_uses_red_and_escapes_html():
    text = format_alert(_signal(direction="short", rationale="a<b>&c"))
    assert text.startswith("\U0001F534")
    assert "<b>SHORT BTCUSDT</b>" in text
    assert "a&lt;b&gt;&amp;c" in text


def test_send_alert_posts_to_bot_api():
    session = FakeSession()
    send_alert(_signal(), "bot-token", "chat-42", session=session)
    assert session.last_url == "https://api.telegram.org/botbot-token/sendMessage"
    assert session.last_json["chat_id"] == "chat-42"
    assert session.last_json["parse_mode"] == "HTML"
    assert "BTCUSDT" in session.last_json["text"]


def test_send_alert_raises_on_http_error():
    with pytest.raises(RuntimeError):
        send_alert(_signal(), "t", "c", session=FakeSession(status=401))


def _cfg(token="bot-token", chat="chat-42"):
    return Config(
        sealion_api_key="k", supabase_url="https://abc.supabase.co",
        supabase_service_key="s", telegram_bot_token=token,
        telegram_chat_id=chat,
    )


def test_maybe_send_alert_skips_without_telegram_config(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.run.send_alert",
                        lambda *a, **k: calls.append(a))
    maybe_send_alert(_signal(), BotSettings(), _cfg(token=""))
    assert calls == []


def test_maybe_send_alert_skips_below_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.run.send_alert",
                        lambda *a, **k: calls.append(a))
    settings = BotSettings(min_alert_confidence=90)
    maybe_send_alert(_signal(confidence=80), settings, _cfg())
    assert calls == []


def test_maybe_send_alert_sends_at_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.run.send_alert",
                        lambda *a, **k: calls.append(a))
    settings = BotSettings(min_alert_confidence=80)
    maybe_send_alert(_signal(confidence=80), settings, _cfg())
    assert len(calls) == 1


def test_maybe_send_alert_swallows_send_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr("signals.run.send_alert", boom)
    monkeypatch.setattr("signals.run.RETRY_DELAY", 0)
    maybe_send_alert(_signal(), BotSettings(), _cfg())  # must not raise
