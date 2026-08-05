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


def test_build_messages_includes_setup():
    messages = build_messages(SETUP)
    assert messages[0]["role"] == "system"
    user_content = messages[1]["content"]
    assert "BTCUSDT" in user_content
    assert "long" in user_content
    assert "100.0" in user_content       # entry
    assert "98.0" in user_content        # stop loss
    assert "Market session" in user_content


def test_build_messages_is_purely_technical():
    """News and calendar must be gone from both halves of the prompt."""
    messages = build_messages(SETUP)
    system = messages[0]["content"].lower()
    user_content = messages[1]["content"].lower()
    assert "headline" not in user_content
    assert "economic calendar" not in user_content
    assert "headline" not in system
    assert "calendar" not in system


def test_system_prompt_leans_confirm_on_borderline_setups():
    messages = build_messages(SETUP)
    system = messages[0]["content"].lower()
    assert "lean confirm" in system
    assert "reject only" in system


def test_build_messages_includes_session_context():
    messages = build_messages(
        SETUP,
        session_context="Market session at 2026-07-14 14:00 UTC: London / New York overlap",
    )
    user_content = messages[1]["content"]
    assert "London / New York overlap" in user_content


def test_build_messages_includes_adx_and_htf_trend_when_present():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0,
                    "macd_hist": 0.5, "adx": 27.3, "htf_trend": "up"},
    )
    user_content = build_messages(setup)[1]["content"]
    assert "ADX=27.3" in user_content
    assert "HTF trend=up" in user_content


def test_build_messages_omits_adx_and_htf_trend_when_absent():
    user_content = build_messages(SETUP)[1]["content"]
    assert "ADX=" not in user_content
    assert "HTF trend=" not in user_content


def test_build_messages_cloud_mss_does_not_crash_on_missing_ema9():
    """cloud_mss indicators have no ema9/ema21/rsi/macd_hist keys — the
    generic EMA fallback in _format_indicators must not be reached for it."""
    setup = CandidateSetup(
        symbol="XAUUSD", direction="long", entry=4100.0,
        stop_loss=4080.0, take_profit=4140.0,
        indicators={
            "strategy": "cloud_mss", "side": "long", "ce_trend": "up",
            "cloud_low": 4090.0, "cloud_high": 4095.0, "ma200": 4088.0,
            "choch_level": 4082.0, "atr": 3.5,
        },
    )
    user_content = build_messages(setup, strategy="cloud_mss")[1]["content"]
    assert "cloud" in user_content.lower()
    assert "CHoCH" in user_content


def test_build_messages_bbma_extreme_does_not_crash_on_missing_ema9():
    setup = CandidateSetup(
        symbol="ETHUSD", direction="short", entry=3000.0,
        stop_loss=3050.0, take_profit=2900.0,
        indicators={
            "strategy": "bbma_extreme", "side": "short",
            "bb_upper": 3040.0, "bb_mid": 3000.0, "bb_lower": 2960.0,
            "ma5h": 3010.0, "ma5l": 2990.0, "atr": 15.0,
        },
    )
    user_content = build_messages(setup, strategy="bbma_extreme")[1]["content"]
    assert "BB" in user_content or "bb" in user_content.lower()


def test_build_messages_bbma_reentry_does_not_crash_on_missing_ema9():
    setup = CandidateSetup(
        symbol="BTCUSD", direction="long", entry=64000.0,
        stop_loss=63800.0, take_profit=64400.0,
        indicators={
            "strategy": "bbma_reentry", "side": "long", "trigger": "csm",
            "bb_upper": 64200.0, "bb_mid": 64000.0, "bb_lower": 63800.0,
            "ma5h": 64050.0, "ma5l": 63950.0, "ma10h": 64100.0,
            "ma10l": 63900.0, "ema50": 63900.0, "atr": 120.0,
        },
    )
    user_content = build_messages(setup, strategy="bbma_reentry")[1]["content"]
    assert "csm" in user_content.lower()


def test_confirm_setup_cloud_mss_calls_llm_instead_of_fail_closed_rejecting():
    """Regression test: a broken _format_indicators branch used to make
    every cloud_mss candidate crash inside build_messages, which confirm_setup
    silently turned into a fail-closed reject without ever calling the LLM."""
    setup = CandidateSetup(
        symbol="XAUUSD", direction="long", entry=4100.0,
        stop_loss=4080.0, take_profit=4140.0,
        indicators={
            "strategy": "cloud_mss", "side": "long", "ce_trend": "up",
            "cloud_low": 4090.0, "cloud_high": 4095.0, "ma200": 4088.0,
            "choch_level": 4082.0, "atr": 3.5,
        },
    )
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 70, "rationale": "ok"}')
    result = confirm_setup(setup, llm, strategy="cloud_mss")
    assert llm.last_messages is not None
    assert result.verdict == "confirm"


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
    result = confirm_setup(SETUP, llm)
    assert result.verdict == "confirm"
    assert llm.last_messages is not None


def test_confirm_setup_llm_error_is_reject():
    llm = FakeLLM(error=RuntimeError("HTTP 429"))
    result = confirm_setup(SETUP, llm)
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
