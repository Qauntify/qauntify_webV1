"""Unit tests for the AI War Room technical debate orchestration."""
from signals.debate import parse_manager, run_debate
from signals.models import CandidateSetup

SETUP = CandidateSetup(
    symbol="XAUUSD", direction="long", entry=2400.0, stop_loss=2396.0,
    take_profit=2408.0, indicators={"strategy": "ict_fvg", "atr": 2.0},
)


class SeqLLM:
    """Returns canned replies in order: structure, momentum, manager."""
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def chat(self, messages, temperature=0.2):
        self.calls.append(messages)
        return self._replies.pop(0)


def test_run_debate_builds_three_agent_transcript():
    llm = SeqLLM([
        "Clean sweep + CHoCH; FVG retest holds, R:R solid.",
        "RSI supportive and HTF preference aligned; setup still fresh.",
        '{"verdict": "agree", "confidence": 72, "rationale": "Both align — take it."}',
    ])
    d = run_debate(SETUP, llm, timeframe="1h",
                   headlines=["Gold steady"], calendar_block="quiet")
    agents = [m["agent"] for m in d["transcript"]]
    assert agents == ["Structure Analyst", "Momentum Analyst", "Manager"]
    assert all(m["avatar"] for m in d["transcript"])  # every bubble has an avatar
    assert d["transcript"][0]["message"].startswith("Clean sweep")
    assert d["transcript"][1]["message"].startswith("RSI supportive")
    assert d["manager_verdict"] == "agree"
    assert d["manager_confidence"] == 72
    assert d["symbol"] == "XAUUSD"
    assert d["direction"] == "long"
    assert d["timeframe"] == "1h"


def test_run_debate_makes_three_llm_calls():
    llm = SeqLLM(["t", "m", '{"verdict":"agree","confidence":50,"rationale":"ok"}'])
    run_debate(SETUP, llm, timeframe="1h")
    assert len(llm.calls) == 3


def test_run_debate_ignores_headlines_and_calendar():
    """Technical-only: news inputs must not appear in any agent prompt."""
    llm = SeqLLM([
        "Structure looks fine.",
        "Momentum looks fine.",
        '{"verdict":"agree","confidence":60,"rationale":"ok"}',
    ])
    run_debate(
        SETUP, llm, timeframe="5m",
        headlines=["Fed hikes rates", "Gold ETF outflows"],
        calendar_block="NFP in 30 minutes",
    )
    blob = " ".join(
        m["content"] for call in llm.calls for m in call
    ).lower()
    assert "fed hikes" not in blob
    assert "nfp" not in blob
    assert "headline" not in blob


def test_run_debate_is_failsoft_when_an_agent_errors():
    class FlakyLLM:
        def __init__(self):
            self.n = 0

        def chat(self, messages, temperature=0.2):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("read timeout")  # structure agent fails
            if self.n == 2:
                return "Momentum is neutral."
            return '{"verdict": "caution", "confidence": 40, "rationale": "Mixed."}'

    d = run_debate(SETUP, FlakyLLM(), timeframe="1h")
    assert "abstain" in d["transcript"][0]["message"].lower()
    assert d["transcript"][1]["message"] == "Momentum is neutral."
    assert d["manager_verdict"] == "caution"


def test_run_debate_unwraps_json_wrapped_agent_replies():
    # Some models wrap analyst answers in JSON despite instructions — the
    # transcript must show the inner text, not raw JSON.
    llm = SeqLLM([
        '{"output": "Strong bullish continuation structure."}',
        '{"response": "Momentum still supportive."}',
        '{"verdict": "agree", "confidence": 60, "rationale": "Take it."}',
    ])
    d = run_debate(SETUP, llm, timeframe="1h")
    assert d["transcript"][0]["message"] == "Strong bullish continuation structure."
    assert d["transcript"][1]["message"] == "Momentum still supportive."


def test_parse_manager_handles_valid_json():
    v, c, r = parse_manager(
        '{"verdict": "reject", "confidence": 20, "rationale": "Structure broken."}'
    )
    assert v == "reject"
    assert c == 20
    assert r == "Structure broken."


def test_parse_manager_bad_json_falls_back_safely():
    v, c, r = parse_manager("I think maybe take it?")
    assert v == "caution"     # neutral fallback, never a confident yes
    assert c == 0
    assert r  # keeps some rationale text


def test_parse_manager_clamps_confidence():
    v, c, r = parse_manager('{"verdict":"agree","confidence":250,"rationale":"x"}')
    assert c == 100
