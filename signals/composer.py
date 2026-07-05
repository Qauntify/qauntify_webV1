"""Builds the confirmation prompt, calls the LLM, and parses the verdict.

Fail-closed: any LLM failure or unparseable reply becomes a reject so an
unconfirmed signal is never stored.
"""
import json

from signals.models import CandidateSetup, Confirmation

SYSTEM_PROMPT = (
    "You are a disciplined trading-signal reviewer. You receive a candidate "
    "trade setup derived from technical indicators, plus recent news "
    "headlines. Decide whether the setup is worth taking.\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "confirm" or "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short paragraph explaining your decision>"}'
)


def build_messages(setup: CandidateSetup, headlines: list) -> list:
    if headlines:
        news_block = "\n".join(f"- {h}" for h in headlines)
    else:
        news_block = "No recent headlines available."
    ind = setup.indicators
    user_content = (
        f"Candidate setup:\n"
        f"- Symbol: {setup.symbol}\n"
        f"- Direction: {setup.direction}\n"
        f"- Entry: {setup.entry}\n"
        f"- Stop loss: {setup.stop_loss}\n"
        f"- Take profit: {setup.take_profit}\n"
        f"- Indicators: EMA9={ind['ema9']:.2f}, EMA21={ind['ema21']:.2f}, "
        f"RSI={ind['rsi']:.1f}, MACD hist={ind['macd_hist']:.4f}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_confirmation(text: str) -> Confirmation:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return Confirmation("reject", 0, f"Unparseable LLM reply: {text[:200]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return Confirmation("reject", 0, f"Invalid JSON in LLM reply: {text[:200]}")
    verdict = data.get("verdict")
    if verdict not in ("confirm", "reject"):
        return Confirmation("reject", 0, f"Invalid verdict in LLM reply: {verdict!r}")
    try:
        confidence = max(0, min(100, int(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    rationale = str(data.get("rationale", ""))
    return Confirmation(verdict, confidence, rationale)


def confirm_setup(setup: CandidateSetup, headlines: list, llm) -> Confirmation:
    try:
        reply = llm.chat(build_messages(setup, headlines))
    except Exception as exc:
        return Confirmation("reject", 0, f"LLM call failed: {exc}")
    return parse_confirmation(reply)
