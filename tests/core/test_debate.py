"""Unit tests for the AI War Room 3-agent debate orchestration."""
from signals.debate import parse_manager, run_debate
from signals.models import CandidateSetup

SETUP = CandidateSetup(
    symbol="XAUUSD", direction="long", entry=2400.0, stop_loss=2396.0,
    take_profit=2408.0, indicators={"strategy": "ict_fvg", "atr": 2.0},
)


class SeqLLM:
    """Returns canned replies in order: technical, fundamental, manager."""
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def chat(self, messages, temperature=0.2):
        self.calls.append(messages)
        return self._replies.pop(0)


def test_run_debate_builds_three_agent_transcript():
    llm = SeqLLM([
        "Clean bounce off support; RSI supportive, R:R 2:1.",
        "No high-impact gold news; macro calendar quiet.",
        '{"verdict": "agree", "confidence": 72, "rationale": "Both align — take it."}',
    ])
    d = run_debate(SETUP, llm, timeframe="1h",
                   headlines=["Gold steady"], calendar_block="quiet")
    agents = [m["agent"] for m in d["transcript"]]
    assert agents == ["Technical Analyst", "Fundamental Analyst", "Manager"]
    assert all(m["avatar"] for m in d["transcript"])  # every bubble has an avatar
    assert d["transcript"][0]["message"].startswith("Clean bounce")
    assert d["transcript"][1]["message"].startswith("No high-impact")
    assert d["manager_verdict"] == "agree"
    assert d["manager_confidence"] == 72
    assert d["symbol"] == "XAUUSD"
    assert d["direction"] == "long"
    assert d["timeframe"] == "1h"


def test_run_debate_makes_three_llm_calls():
    llm = SeqLLM(["t", "f", '{"verdict":"agree","confidence":50,"rationale":"ok"}'])
    run_debate(SETUP, llm, timeframe="1h")
    assert len(llm.calls) == 3


def test_run_debate_is_failsoft_when_an_agent_errors():
    class FlakyLLM:
        def __init__(self):
            self.n = 0

        def chat(self, messages, temperature=0.2):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("read timeout")  # technical agent fails
            if self.n == 2:
                return "Macro backdrop is neutral."
            return '{"verdict": "caution", "confidence": 40, "rationale": "Mixed."}'

    d = run_debate(SETUP, FlakyLLM(), timeframe="1h")
    assert "abstain" in d["transcript"][0]["message"].lower()
    assert d["transcript"][1]["message"] == "Macro backdrop is neutral."
    assert d["manager_verdict"] == "caution"


def test_run_debate_unwraps_json_wrapped_agent_replies():
    # Some models wrap analyst answers in JSON despite instructions — the
    # transcript must show the inner text, not raw JSON.
    llm = SeqLLM([
        '{"output": "Strong bullish continuation structure."}',
        '{"response": "Macro backdrop is quiet."}',
        '{"verdict": "agree", "confidence": 60, "rationale": "Take it."}',
    ])
    d = run_debate(SETUP, llm, timeframe="1h")
    assert d["transcript"][0]["message"] == "Strong bullish continuation structure."
    assert d["transcript"][1]["message"] == "Macro backdrop is quiet."


def test_parse_manager_handles_valid_json():
    v, c, r = parse_manager('{"verdict": "reject", "confidence": 20, "rationale": "News risk."}')
    assert v == "reject"
    assert c == 20
    assert r == "News risk."


def test_parse_manager_bad_json_falls_back_safely():
    v, c, r = parse_manager("I think maybe take it?")
    assert v == "caution"     # neutral fallback, never a confident yes
    assert c == 0
    assert r  # keeps some rationale text


def test_parse_manager_clamps_confidence():
    v, c, r = parse_manager('{"verdict":"agree","confidence":250,"rationale":"x"}')
    assert c == 100
