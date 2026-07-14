"""Tests for the LLM confirmation composer."""
from signals.composer import (
    build_messages,
    build_no_setup_messages,
    confirm_setup,
    explain_no_setup,
    parse_confirmation,
    parse_rationale,
)
from signals.models import CandidateSetup

SETUP = CandidateSetup(
    symbol="BTCUSDT",
    direction="long",
    entry=100.0,
    stop_loss=98.0,
    take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)

HEADLINES = ["Bitcoin breaks resistance", "ETF inflows surge"]


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error
        self.last_messages = None

    def chat(self, messages, temperature=0.2):
        self.last_messages = messages
        if self._error:
            raise self._error
        return self._reply


def test_build_messages_includes_setup_and_news():
    messages = build_messages(SETUP, HEADLINES)
    assert messages[0]["role"] == "system"
    user_content = messages[1]["content"]
    assert "BTCUSDT" in user_content
    assert "long" in user_content
    assert "100.0" in user_content       # entry
    assert "98.0" in user_content        # stop loss
    assert "Bitcoin breaks resistance" in user_content
    assert "economic-calendar" in messages[0]["content"] or (
        "economic calendar" in messages[0]["content"].lower()
    )
    assert "Market session" in user_content
    assert "Economic calendar" in user_content


def test_build_messages_includes_session_and_calendar_blocks():
    messages = build_messages(
        SETUP, HEADLINES,
        session_context="Market session at 2026-07-14 14:00 UTC: London / New York overlap",
        calendar_block="- 2026-07-14 12:30 UTC | USD | High | CPI m/m | forecast 0.2%",
    )
    user_content = messages[1]["content"]
    assert "London / New York overlap" in user_content
    assert "CPI m/m" in user_content
    assert "May confirm trades during news" in messages[0]["content"] or (
        "MAY confirm trades during news" in messages[0]["content"]
    )

def test_build_messages_handles_no_headlines():
    messages = build_messages(SETUP, [])
    assert "No recent headlines available" in messages[1]["content"]


def test_build_messages_includes_adx_and_htf_trend_when_present():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0,
                    "macd_hist": 0.5, "adx": 27.3, "htf_trend": "up"},
    )
    user_content = build_messages(setup, [])[1]["content"]
    assert "ADX=27.3" in user_content
    assert "HTF trend=up" in user_content


def test_build_messages_omits_adx_and_htf_trend_when_absent():
    user_content = build_messages(SETUP, [])[1]["content"]
    assert "ADX=" not in user_content
    assert "HTF trend=" not in user_content


def test_parse_confirmation_valid_json():
    text = '{"verdict": "confirm", "confidence": 78, "rationale": "Momentum aligns."}'
    result = parse_confirmation(text)
    assert result.verdict == "confirm"
    assert result.confidence == 78
    assert result.rationale == "Momentum aligns."


def test_parse_confirmation_json_wrapped_in_prose():
    text = 'Sure! Here is my analysis:\n```json\n{"verdict": "reject", "confidence": 30, "rationale": "News is bearish."}\n```\nHope that helps.'
    result = parse_confirmation(text)
    assert result.verdict == "reject"
    assert result.confidence == 30


def test_parse_confirmation_malformed_is_reject():
    result = parse_confirmation("I think this trade looks great, go for it!")
    assert result.verdict == "reject"
    assert result.confidence == 0


def test_parse_confirmation_bad_verdict_is_reject():
    result = parse_confirmation('{"verdict": "maybe", "confidence": 50, "rationale": "hmm"}')
    assert result.verdict == "reject"


def test_parse_confirmation_clamps_confidence():
    result = parse_confirmation('{"verdict": "confirm", "confidence": 150, "rationale": "very sure"}')
    assert result.confidence == 100


def test_parse_confirmation_infinite_confidence_is_reject_safe():
    result = parse_confirmation('{"verdict": "confirm", "confidence": Infinity, "rationale": "x"}')
    assert result.confidence == 0


def test_confirm_setup_happy_path():
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')
    result = confirm_setup(SETUP, HEADLINES, llm)
    assert result.verdict == "confirm"
    assert llm.last_messages is not None


def test_confirm_setup_llm_error_is_reject():
    llm = FakeLLM(error=RuntimeError("HTTP 429"))
    result = confirm_setup(SETUP, HEADLINES, llm)
    assert result.verdict == "reject"
    assert result.confidence == 0
    assert "HTTP 429" in result.rationale


def test_build_no_setup_messages_includes_indicators_and_news():
    indicators = {"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5}
    messages = build_no_setup_messages("BTCUSDT", "1h", indicators, HEADLINES)
    user_content = messages[1]["content"]
    assert "BTCUSDT" in user_content
    assert "EMA9=101.00" in user_content
    assert "Bitcoin breaks resistance" in user_content


def test_parse_rationale_extracts_json_field():
    text = '{"rationale": "No crossover on recent bars."}'
    assert parse_rationale(text) == "No crossover on recent bars."


def test_explain_no_setup_happy_path():
    indicators = {"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5}
    llm = FakeLLM(reply='{"rationale": "Trend is sideways."}')
    result = explain_no_setup("BTCUSDT", "1h", indicators, HEADLINES, llm)
    assert result == "Trend is sideways."
    assert llm.last_messages is not None


def test_explain_no_setup_llm_error_returns_message():
    indicators = {"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5}
    llm = FakeLLM(error=RuntimeError("HTTP 503"))
    result = explain_no_setup("BTCUSDT", "1h", indicators, [], llm)
    assert "HTTP 503" in result
