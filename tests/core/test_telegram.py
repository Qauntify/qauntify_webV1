import pytest

from signals.config import Config
from signals.models import BotSettings, CandidateSetup, Confirmation, NoSignalReport, make_signal
from signals.pipeline.deliver import maybe_send_alert
from signals.clients.telegram import (
    format_alert,
    format_caption,
    format_no_signal_alert,
    format_outcome_alert,
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
    assert "🟢" in text                        # long = green
    assert "LONG SIGNAL" in text
    assert "<b>BTCUSDT</b>" in text
    assert "1h" in text
    assert "<code>108240</code>" in text        # entry
    assert "<code>106900</code>" in text        # stop
    assert "<code>110920</code>" in text        # TP1
    assert "Confidence</b>  80%" in text
    assert "▰" in text and "▱" in text          # confidence bar
    assert "Risk" in text and "Reward" in text  # R:R line
    assert "Looks good." in text


def test_format_alert_short_uses_red_and_escapes_html():
    text = format_alert(_signal(direction="short", rationale="a<b>&c"))
    assert "🔴" in text                         # short = red
    assert "SHORT SIGNAL" in text
    assert "<b>BTCUSDT</b>" in text
    assert "a&lt;b&gt;&amp;c" in text           # rationale escaped


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


def test_format_outcome_alert_tp_hit_is_positive():
    row = {"symbol": "BTCUSD", "direction": "long", "entry": 100.0,
           "stop_loss": 99.0, "take_profit_1": 102.0,
           "take_profit_2": 104.0, "take_profit_3": 106.0}
    text = format_outcome_alert(row, "tp1_hit")
    assert "TP1 HIT" in text
    assert "✅" in text
    assert "🟢" in text                         # long
    assert "+2.00%" in text
    assert "<code>100</code>" in text and "<code>102</code>" in text


def test_format_outcome_alert_sl_hit_is_negative():
    row = {"symbol": "ETHUSD", "direction": "short", "entry": 100.0,
           "stop_loss": 102.0, "take_profit_1": 98.0}
    text = format_outcome_alert(row, "sl_hit")
    assert "STOP LOSS" in text
    assert "🛑" in text
    assert "🔴" in text                         # short
    assert "-2.00%" in text                     # short stopped out 2% against


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
    monkeypatch.setattr("signals.pipeline.deliver.send_alert",
                        lambda *a, **k: calls.append(a))
    maybe_send_alert(_signal(), BotSettings(), _cfg(token=""))
    assert calls == []


def test_maybe_send_alert_skips_below_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.pipeline.deliver.send_alert",
                        lambda *a, **k: calls.append(a))
    settings = BotSettings(min_alert_confidence=90)
    maybe_send_alert(_signal(confidence=80), settings, _cfg())
    assert calls == []


def test_maybe_send_alert_sends_at_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr("signals.pipeline.deliver.send_alert",
                        lambda *a, **k: calls.append(a))
    settings = BotSettings(min_alert_confidence=80)
    maybe_send_alert(_signal(confidence=80), settings, _cfg())
    assert len(calls) == 1


def test_maybe_send_alert_swallows_send_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr("signals.pipeline.deliver.send_alert", boom)
    monkeypatch.setattr("signals.pipeline.dedup.RETRY_DELAY", 0)
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
    from signals.pipeline.dedup import already_signaled
    monkeypatch.setattr("signals.pipeline.dedup.latest_signal",
                        lambda *a, **k: _stored_row("long", minutes_ago=30))
    assert already_signaled(_setup("long"), _cfg()) is True


def test_already_signaled_false_for_other_direction(monkeypatch):
    from signals.pipeline.dedup import already_signaled
    monkeypatch.setattr("signals.pipeline.dedup.latest_signal",
                        lambda *a, **k: _stored_row("short", minutes_ago=30))
    assert already_signaled(_setup("long"), _cfg()) is False


def test_already_signaled_false_outside_window(monkeypatch):
    from signals.pipeline.dedup import already_signaled
    monkeypatch.setattr("signals.pipeline.dedup.latest_signal",
                        lambda *a, **k: _stored_row("long", minutes_ago=200))
    assert already_signaled(_setup("long"), _cfg()) is False


def test_already_signaled_false_when_no_history_or_error(monkeypatch):
    from signals.pipeline.dedup import already_signaled
    monkeypatch.setattr("signals.pipeline.dedup.latest_signal", lambda *a, **k: None)
    assert already_signaled(_setup(), _cfg()) is False

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("signals.pipeline.dedup.latest_signal", boom)
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
    assert "NO SIGNAL" in text
    assert "<b>BTCUSDT</b>" in text
    assert "EMA9 101.00" in text
    assert "No crossover yet." in text


def test_format_no_signal_alert_for_rejected():
    text = format_no_signal_alert(_no_signal_report(kind="rejected"))
    assert "SIGNAL REJECTED" in text
    assert "<b>BTCUSDT</b>" in text
    assert "LONG  @  <code>100</code>" in text
    assert "Confidence  25%" in text


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


def test_format_no_signal_alert_for_cloud_mss_no_setup():
    report = NoSignalReport(
        symbol="XAUUSD", timeframe="15m", kind="no_setup",
        rationale="No cloud rejection + CHoCH.",
        indicators={
            "strategy": "cloud_mss", "side": "long",
            "cloud_low": 4090.0, "cloud_high": 4095.0, "atr": 3.5, "adx": 20.0,
        },
    )
    text = format_no_signal_alert(report)
    assert "cloud 4090.00-4095.00" in text
    assert "EMA9" not in text


def test_format_no_signal_alert_for_bbma_no_setup():
    report = NoSignalReport(
        symbol="ETHUSD", timeframe="1h", kind="no_setup",
        rationale="No BBMA trigger.",
        indicators={
            "strategy": "bbma_reentry", "side": "short",
            "bb_upper": 3040.0, "bb_lower": 2960.0, "atr": 15.0,
        },
    )
    text = format_no_signal_alert(report)
    assert "BB 2960.00-3040.00" in text
    assert "EMA9" not in text


def test_send_no_signal_alert_posts_to_bot_api():
    session = FakeSession()
    send_no_signal_alert(_no_signal_report(), "bot-token", "chat-42", session=session)
    assert session.last_url == "https://api.telegram.org/botbot-token/sendMessage"
    assert "NO SIGNAL" in session.last_json["text"]
    assert "BTCUSDT" in session.last_json["text"]


def test_format_run_summary_contains_outcomes():
    text = format_run_summary(
        "run-1",
        "1h",
        [
            {"symbol": "BTCUSDT", "status": "NO SIGNAL", "extra": "sideways"},
            {"symbol": "ETHUSDT", "status": "CONFIRMED", "extra": "LONG 82%"},
        ],
    )
    assert "ENGINE RUN" in text
    assert "<b>Timeframe</b>  1h" in text
    assert "<code>run-1</code>" in text
    assert "BTCUSDT  ·  NO SIGNAL  ·  sideways" in text
    assert "ETHUSDT  ·  CONFIRMED  ·  LONG 82%" in text


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


def test_pipeline_never_pushes_no_signal_or_summary_alerts():
    """Telegram carries confirmed signals and TP/SL outcomes only.

    This used to be enforced by two functions in signals.run whose entire body
    was `return`, which is a comment pretending to be code. The invariant is
    that the run path (now split across signals.pipeline.*) never reaches the
    no-signal / run-summary senders, so assert that directly.
    """
    import ast
    import inspect

    from signals.pipeline import dedup, deliver, engine, market_data, scan

    called = set()
    for module in (dedup, deliver, engine, market_data, scan):
        tree = ast.parse(inspect.getsource(module))
        called |= {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
    assert "send_no_signal_alert" not in called
    assert "send_run_summary" not in called
    # The senders themselves stay available for ad-hoc use.
    from signals.clients import telegram
    assert hasattr(telegram, "send_no_signal_alert")
    assert hasattr(telegram, "send_run_summary")


def test_format_run_summary_tags_lines_with_timeframe():
    from signals.clients.telegram import format_run_summary

    text = format_run_summary("run-1", "15m+1h", [
        {"symbol": "BTCUSDT", "status": "CONFIRMED", "extra": "LONG 82%",
         "timeframe": "15m"},
        {"symbol": "BTCUSDT", "status": "NO SIGNAL", "extra": "",
         "timeframe": "1h"},
    ])
    assert "BTCUSDT [15m]  ·  CONFIRMED  ·  LONG 82%" in text
    assert "BTCUSDT [1h]  ·  NO SIGNAL" in text


from signals.models import Signal
from signals.clients.telegram import format_caption, send_alert


def _chart_signal(chart_url=None):
    return Signal(id="s1", symbol="XAUUSD", timeframe="5m", direction="long",
                  entry=2006.8, stop_loss=2001.8, take_profit=2009.3,
                  take_profit_2=2011.8, take_profit_3=2014.3, confidence=72,
                  rationale="x" * 2000, indicators={}, news_headlines=[],
                  created_at="t", chart_url=chart_url)


class _ChartRec:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})

        class _R:
            status_code = 200

            def raise_for_status(self_inner):
                return None
        return _R()


def test_caption_stays_under_telegram_limit():
    assert len(format_caption(_chart_signal())) <= 1024


def test_send_alert_uses_photo_when_chart_present():
    rec = _ChartRec()
    send_alert(_chart_signal(chart_url="http://x/s1.png"), "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    assert rec.calls[0]["json"]["photo"] == "http://x/s1.png"


def test_send_alert_falls_back_to_message_without_chart():
    rec = _ChartRec()
    send_alert(_chart_signal(chart_url=None), "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendMessage")


def _chart_signal_with_rationale(rationale, chart_url="http://x/sig.png"):
    return Signal(id="s", symbol="XAUUSD", timeframe="5m", direction="long",
                  entry=2006.8, stop_loss=2001.8, take_profit=2009.3,
                  take_profit_2=2011.8, take_profit_3=2014.3, confidence=72,
                  rationale=rationale, indicators={}, news_headlines=[],
                  created_at="t", chart_url=chart_url)


def test_photo_caption_includes_analysis_when_short():
    rec = _ChartRec()
    sig = _chart_signal_with_rationale("Swept the low then CHoCH up into the FVG.")
    send_alert(sig, "tok", "chat", session=rec)
    assert len(rec.calls) == 1
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    cap = rec.calls[0]["json"]["caption"]
    assert "Analysis" in cap
    assert "CHoCH up into the FVG" in cap


def test_long_analysis_falls_back_to_followup_message():
    rec = _ChartRec()
    sig = _chart_signal_with_rationale("y" * 2000)
    send_alert(sig, "tok", "chat", session=rec)
    assert len(rec.calls) == 2
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    assert "yyyy" not in rec.calls[0]["json"]["caption"]  # essentials only
    assert rec.calls[1]["url"].endswith("/sendMessage")
    assert "Analysis" in rec.calls[1]["json"]["text"]
    assert "y" * 200 in rec.calls[1]["json"]["text"]


def _outcome_row(outcome_chart_url=None):
    return {"symbol": "XAUUSD", "direction": "long", "entry": 100.0,
            "stop_loss": 98.0, "take_profit": 103.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0,
            "outcome_chart_url": outcome_chart_url}


def test_outcome_alert_uses_photo_when_chart_present():
    from signals.clients.telegram import send_outcome_alert
    rec = _ChartRec()
    send_outcome_alert(_outcome_row("http://x/s1-outcome.png"), "tp3_hit",
                       "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    assert rec.calls[0]["json"]["photo"] == "http://x/s1-outcome.png"


def test_outcome_alert_falls_back_to_message_without_chart():
    from signals.clients.telegram import send_outcome_alert
    rec = _ChartRec()
    send_outcome_alert(_outcome_row(None), "sl_hit", "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendMessage")


def test_signal_message_tells_the_follower_to_trail_to_breakeven():
    """The engine books thirds and trails the stop to entry after TP1, and
    outcome_tracker settles trades that way. A follower who never moves the
    stop is not making the trade the track record reports, so the instruction
    has to travel with the signal."""
    assert "move your stop to entry" in format_alert(_signal())
    assert "move SL to entry" in format_caption(_signal())
