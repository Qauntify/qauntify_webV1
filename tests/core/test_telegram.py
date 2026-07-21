import pytest

from signals.config import Config
from signals.models import BotSettings, CandidateSetup, Confirmation, NoSignalReport, make_signal
from signals.run import maybe_send_alert, maybe_send_no_signal_alert, maybe_send_run_summary
from signals.telegram_client import (
    format_alert,
    format_no_signal_alert,
    format_run_summary,
    send_alert,
    send_no_signal_alert,
    send_run_summary,
)


def _signal(direction="long", confidence=80, rationale="Looks good."):
    setup = CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=108240.0,
        stop_loss=106900.0, take_profit=110920.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", confidence, rationale)
    return make_signal(setup, confirmation, ["headline one"])


class FakeResponse:
    def __init__(self, status=200, description=""):
        self.status_code = status
        self._description = description
        self.text = description

    def json(self):
        if self._description:
            return {"ok": False, "description": self._description}
        return {"ok": True}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, status=200, description=""):
        self._status = status
        self._description = description
        self.last_url = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_json = json
        return FakeResponse(self._status, self._description)


def test_format_alert_contains_trade_details():
    text = format_alert(_signal())
    assert "<b>LONG BTCUSDT</b>" in text
    assert "(1h)" in text
    assert "Entry 108240 | SL 106900 | TP1" in text
    assert "Confidence 80%" in text
    assert "Looks good." in text
    assert text.startswith("<b>")


def test_format_alert_short_uses_red_and_escapes_html():
    text = format_alert(_signal(direction="short", rationale="a<b>&c"))
    assert text.startswith("<b>")
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
    import requests

    with pytest.raises(requests.HTTPError, match="need administrator"):
        send_alert(
            _signal(), "t", "c",
            session=FakeSession(
                status=400,
                description="Bad Request: need administrator rights in the channel chat",
            ),
        )


def _cfg(token="bot-token", chat="chat-42"):
    return Config(
        sealion_api_key="k", supabase_url="https://abc.supabase.co",
        supabase_service_key="s", telegram_bot_token=token,
        telegram_channel_id=chat,
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


def _setup(direction="long"):
    return CandidateSetup(
        symbol="BTCUSDT", direction=direction, entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 1.0, "ema21": 1.0, "rsi": 50.0, "macd_hist": 0.1},
    )


def _stored_row(direction="long", minutes_ago=30):
    from datetime import datetime, timedelta, timezone
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"direction": direction, "created_at": ts.isoformat()}


def test_already_signaled_true_for_fresh_same_direction(monkeypatch):
    from signals.run import already_signaled
    monkeypatch.setattr("signals.run.latest_signal",
                        lambda *a, **k: _stored_row("long", minutes_ago=30))
    assert already_signaled(_setup("long"), _cfg()) is True


def test_already_signaled_false_for_other_direction(monkeypatch):
    from signals.run import already_signaled
    monkeypatch.setattr("signals.run.latest_signal",
                        lambda *a, **k: _stored_row("short", minutes_ago=30))
    assert already_signaled(_setup("long"), _cfg()) is False


def test_already_signaled_false_outside_window(monkeypatch):
    from signals.run import already_signaled
    monkeypatch.setattr("signals.run.latest_signal",
                        lambda *a, **k: _stored_row("long", minutes_ago=200))
    assert already_signaled(_setup("long"), _cfg()) is False


def test_already_signaled_false_when_no_history_or_error(monkeypatch):
    from signals.run import already_signaled
    monkeypatch.setattr("signals.run.latest_signal", lambda *a, **k: None)
    assert already_signaled(_setup(), _cfg()) is False

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("signals.run.latest_signal", boom)
    # Fail closed: lookup errors block stores rather than allow duplicates.
    assert already_signaled(_setup(), _cfg()) is True


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


def test_format_no_signal_alert_for_no_setup():
    text = format_no_signal_alert(_no_signal_report())
    assert "<b>NO SIGNAL BTCUSDT</b>" in text
    assert "EMA9 101.00" in text
    assert "No crossover yet." in text


def test_format_no_signal_alert_for_rejected():
    text = format_no_signal_alert(_no_signal_report(kind="rejected"))
    assert "<b>REJECTED BTCUSDT</b>" in text
    assert "LONG candidate @ 100" in text
    assert "Confidence 25%" in text


def test_format_no_signal_alert_for_sr_zone_no_setup():
    report = NoSignalReport(
        symbol="BTCUSDT", timeframe="1h", kind="no_setup",
        rationale="No tested S/R zone rejecting.",
        indicators={"strategy": "sr_zone", "atr": 12.5, "adx": 18.0},
    )
    text = format_no_signal_alert(report)
    assert "ATR 12.50" in text
    assert "ADX 18.0" in text
    # Must NOT fall through to the EMA branch and print zeroed readings.
    assert "EMA9" not in text


def test_format_no_signal_alert_for_sr_zone_rejected_shows_zone():
    report = NoSignalReport(
        symbol="BTCUSDT", timeframe="1h", kind="rejected",
        rationale="Bounce rejected.",
        indicators={
            "strategy": "sr_zone", "side": "support",
            "zone_low": 100.0, "zone_high": 100.5, "touches": 2, "atr": 4.0,
        },
        direction="long", entry=103.0, stop_loss=98.0, take_profit=108.0,
        confidence=40,
    )
    text = format_no_signal_alert(report)
    assert "support" in text
    assert "zone 100.00-100.50" in text


def test_send_no_signal_alert_posts_to_bot_api():
    session = FakeSession()
    send_no_signal_alert(_no_signal_report(), "bot-token", "chat-42", session=session)
    assert session.last_url == "https://api.telegram.org/botbot-token/sendMessage"
    assert "NO SIGNAL BTCUSDT" in session.last_json["text"]


def test_format_run_summary_contains_outcomes():
    text = format_run_summary(
        "run-1",
        "1h",
        [
            {"symbol": "BTCUSDT", "status": "NO SIGNAL", "extra": "sideways"},
            {"symbol": "ETHUSDT", "status": "CONFIRMED", "extra": "LONG 82%"},
        ],
    )
    assert "<b>ENGINE RUN</b> (1h)" in text
    assert "Run id: run-1" in text
    assert "BTCUSDT: NO SIGNAL" in text
    assert "ETHUSDT: CONFIRMED" in text


def test_send_run_summary_posts_to_bot_api():
    session = FakeSession()
    send_run_summary(
        "run-1",
        "1h",
        [{"symbol": "BTCUSDT", "status": "NO SIGNAL"}],
        "bot-token",
        "chat-42",
        session=session,
    )
    assert session.last_url == "https://api.telegram.org/botbot-token/sendMessage"
    assert "ENGINE RUN" in session.last_json["text"]


def test_maybe_send_no_signal_alert_skips_without_telegram_config(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.telegram_client.send_no_signal_alert",
                        lambda *a, **k: calls.append(a))
    maybe_send_no_signal_alert(_no_signal_report(), _cfg(token=""))
    assert calls == []


def test_maybe_send_no_signal_alert_does_not_push(monkeypatch):
    """No-signal / rejected scans must not hit Telegram."""
    calls = []
    monkeypatch.setattr("signals.telegram_client.send_no_signal_alert",
                        lambda *a, **k: calls.append(a))
    maybe_send_no_signal_alert(_no_signal_report(), _cfg())
    assert calls == []


def test_maybe_send_no_signal_alert_swallows_send_failure(monkeypatch):
    # Kept as a no-op safety net — must never raise regardless of config.
    maybe_send_no_signal_alert(_no_signal_report(), _cfg())


def test_maybe_send_run_summary_skips_without_telegram_config(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.telegram_client.send_run_summary",
                        lambda *a, **k: calls.append(a))
    maybe_send_run_summary("run-1", "1h", [], _cfg(token=""))
    assert calls == []


def test_maybe_send_run_summary_does_not_push(monkeypatch):
    """Per-run summaries are stored/logged only — not pushed."""
    calls = []
    monkeypatch.setattr("signals.telegram_client.send_run_summary",
                        lambda *a, **k: calls.append(a))
    maybe_send_run_summary("run-1", "1h", [{"symbol": "BTCUSDT", "status": "NO SIGNAL"}], _cfg())
    assert calls == []


def test_format_run_summary_tags_lines_with_timeframe():
    from signals.telegram_client import format_run_summary

    text = format_run_summary("run-1", "15m+1h", [
        {"symbol": "BTCUSDT", "status": "CONFIRMED", "extra": "LONG 82%",
         "timeframe": "15m"},
        {"symbol": "BTCUSDT", "status": "NO SIGNAL", "extra": "",
         "timeframe": "1h"},
    ])
    assert "BTCUSDT [15m]: CONFIRMED — LONG 82%" in text
    assert "BTCUSDT [1h]: NO SIGNAL" in text
