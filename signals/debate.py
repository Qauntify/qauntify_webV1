"""AI War Room: a 3-agent debate about a candidate trade (showcase only).

A Technical analyst and a Fundamental analyst argue independently, then a
Manager synthesises both into a verdict. Purely for the gamified UI — it never
gates real signals. Fail-soft: any agent error becomes an abstention, and the
Manager still returns a (safe) verdict.
"""
import json

# Agent identities carried into the transcript for the UI.
TECHNICAL = {"agent": "Technical Analyst", "avatar": "🤖"}
FUNDAMENTAL = {"agent": "Fundamental Analyst", "avatar": "🌐"}
MANAGER = {"agent": "Manager", "avatar": "🧑‍💼"}

VALID_VERDICTS = ("agree", "caution", "reject")

_TECHNICAL_SYSTEM = (
    "You are the Technical Analyst in a trading war room of robots. Given a "
    "candidate setup and its indicators, argue the technical case in ONE or TWO "
    "short sentences — structure, momentum, and risk/reward. Be decisive and "
    "concise. No preamble, no JSON."
)
_FUNDAMENTAL_SYSTEM = (
    "You are the Fundamental Analyst in a trading war room of robots. Given "
    "recent news headlines and nearby economic-calendar events, argue the macro "
    "case for or against the trade in ONE or TWO short sentences. If there is no "
    "relevant news, say the macro backdrop is quiet. No preamble, no JSON."
)
_MANAGER_SYSTEM = (
    "You are the Manager in a trading war room of robots. You read the Technical "
    "Analyst and the Fundamental Analyst, then make the final call. Weigh both. "
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "agree" | "caution" | "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short sentence>"}'
)


def _technical_prompt(setup, timeframe: str) -> str:
    tp1, tp2, tp3 = setup.resolved_take_profits()
    return (
        f"Setup: {setup.direction.upper()} {setup.symbol} on {timeframe}.\n"
        f"Entry {setup.entry}, stop {setup.stop_loss}, targets {tp1}/{tp2}/{tp3}.\n"
        f"Indicators: {setup.indicators}"
    )


def _fundamental_prompt(symbol: str, headlines, calendar_block) -> str:
    news = "\n".join(f"- {h}" for h in (headlines or [])) or "No recent headlines."
    cal = calendar_block or "No nearby high/medium-impact events."
    return (
        f"Symbol: {symbol}\n"
        f"Recent headlines:\n{news}\n\n"
        f"Economic calendar:\n{cal}"
    )


def _manager_prompt(setup, timeframe, technical_msg, fundamental_msg) -> str:
    return (
        f"Trade: {setup.direction.upper()} {setup.symbol} on {timeframe}.\n\n"
        f"Technical Analyst says: {technical_msg}\n\n"
        f"Fundamental Analyst says: {fundamental_msg}\n\n"
        f"Make the final call."
    )


def _ask(llm, system: str, user: str):
    """One agent turn; None on any failure (the agent abstains)."""
    try:
        reply = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return (reply or "").strip() or None
    except Exception:
        return None


def parse_manager(text: str):
    """(verdict, confidence, rationale) from the Manager's JSON.

    Falls back to a neutral 'caution' / confidence 0 — never a confident yes —
    when the reply is missing or unparseable.
    """
    text = text or ""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            verdict = data.get("verdict")
            if verdict in VALID_VERDICTS:
                try:
                    confidence = max(0, min(100, int(data.get("confidence", 0))))
                except (TypeError, ValueError, OverflowError):
                    confidence = 0
                rationale = str(data.get("rationale", "")) or "No rationale given."
                return verdict, confidence, rationale
        except json.JSONDecodeError:
            pass
    return "caution", 0, (text.strip()[:200] or "Manager reply unclear.")


def run_debate(setup, llm, *, timeframe: str, headlines=None,
               calendar_block=None) -> dict:
    """Run the 3-agent debate; return a transcript + Manager verdict dict."""
    technical = _ask(llm, _TECHNICAL_SYSTEM, _technical_prompt(setup, timeframe)) \
        or "(The Technical Analyst abstains — no response.)"
    fundamental = _ask(
        llm, _FUNDAMENTAL_SYSTEM,
        _fundamental_prompt(setup.symbol, headlines, calendar_block),
    ) or "(The Fundamental Analyst abstains — no response.)"
    manager_reply = _ask(
        llm, _MANAGER_SYSTEM,
        _manager_prompt(setup, timeframe, technical, fundamental),
    )
    verdict, confidence, rationale = parse_manager(manager_reply or "")

    transcript = [
        {**TECHNICAL, "message": technical},
        {**FUNDAMENTAL, "message": fundamental},
        {**MANAGER, "message": rationale},
    ]
    return {
        "symbol": setup.symbol,
        "timeframe": timeframe,
        "direction": setup.direction,
        "transcript": transcript,
        "manager_verdict": verdict,
        "manager_confidence": confidence,
    }
