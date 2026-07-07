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
    except (TypeError, ValueError, OverflowError):
        confidence = 0
    rationale = str(data.get("rationale", ""))
    return Confirmation(verdict, confidence, rationale)


def confirm_setup(setup: CandidateSetup, headlines: list, llm) -> Confirmation:
    try:
        reply = llm.chat(build_messages(setup, headlines))
        return parse_confirmation(reply)
    except Exception as exc:
        return Confirmation("reject", 0, f"LLM call failed: {exc}")


NO_SETUP_SYSTEM_PROMPT = (
    "You are a disciplined trading analyst. You receive the current technical "
    "indicator readings for a market pair (crypto, gold, or forex) and recent "
    "news headlines. The rules "
    "engine found no valid trade setup (no EMA 9/21 crossover with aligned RSI "
    "and MACD filters on the last few hourly bars). Explain briefly why "
    "conditions do not support a long or short entry right now.\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"rationale": "<one short paragraph>"}'
)


def build_no_setup_messages(symbol, timeframe, indicators, headlines) -> list:
    if headlines:
        news_block = "\n".join(f"- {h}" for h in headlines)
    else:
        news_block = "No recent headlines available."
    user_content = (
        f"Market snapshot:\n"
        f"- Symbol: {symbol}\n"
        f"- Timeframe: {timeframe}\n"
        f"- EMA9={indicators['ema9']:.2f}, EMA21={indicators['ema21']:.2f}, "
        f"RSI={indicators['rsi']:.1f}, MACD hist={indicators['macd_hist']:.4f}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
    return [
        {"role": "system", "content": NO_SETUP_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_rationale(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            rationale = data.get("rationale")
            if rationale:
                return str(rationale)
        except json.JSONDecodeError:
            pass
    return text.strip() or "No analysis available."


def explain_no_setup(symbol, timeframe, indicators, headlines, llm) -> str:
    try:
        reply = llm.chat(build_no_setup_messages(
            symbol, timeframe, indicators, headlines,
        ))
        return parse_rationale(reply)
    except Exception as exc:
        return f"LLM call failed: {exc}"
