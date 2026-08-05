"""AI War Room: a 3-agent technical debate about a candidate trade (showcase).

A Structure Analyst and a Momentum Analyst argue independently on the chart,
then a Manager synthesises both into a verdict. Purely for the gamified UI —
it never gates real signals. Fail-soft: any agent error becomes an abstention,
and the Manager still returns a (safe) verdict.
"""
import json

# Agent identities carried into the transcript for the UI.
STRUCTURE = {"agent": "Structure Analyst", "avatar": "📐"}
MOMENTUM = {"agent": "Momentum Analyst", "avatar": "📈"}
MANAGER = {"agent": "Manager", "avatar": "🧑‍💼"}

VALID_VERDICTS = ("agree", "caution", "reject")

_STRUCTURE_SYSTEM = (
    "You are the Structure Analyst in a trading war room of robots. Given a "
    "candidate setup and its indicators, argue the structural case in ONE or "
    "TWO short sentences — liquidity sweep, CHoCH / market structure, FVG or "
    "level quality, and risk/reward. Be decisive and concise. No preamble, "
    "no JSON. Purely technical — ignore news and macro."
)
_MOMENTUM_SYSTEM = (
    "You are the Momentum Analyst in a trading war room of robots. Given a "
    "candidate setup and its indicators, argue the momentum / timing case in "
    "ONE or TWO short sentences — RSI, MACD, ADX, HTF trend preference, and "
    "whether the setup still looks fresh. Be decisive and concise. No "
    "preamble, no JSON. Purely technical — ignore news and macro."
)
_MANAGER_SYSTEM = (
    "You are the Manager in a trading war room of robots. You read the "
    "Structure Analyst and the Momentum Analyst, then make the final call. "
    "Weigh both technical views only — no fundamental or news overlay. "
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "agree" | "caution" | "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short sentence>"}'
)


def _setup_prompt(setup, timeframe: str, lens: str) -> str:
    tp1, tp2, tp3 = setup.resolved_take_profits()
    return (
        f"Lens: {lens}.\n"
        f"Setup: {setup.direction.upper()} {setup.symbol} on {timeframe}.\n"
        f"Entry {setup.entry}, stop {setup.stop_loss}, targets {tp1}/{tp2}/{tp3}.\n"
        f"Indicators: {setup.indicators}"
    )


def _manager_prompt(setup, timeframe, structure_msg, momentum_msg) -> str:
    return (
        f"Trade: {setup.direction.upper()} {setup.symbol} on {timeframe}.\n\n"
        f"Structure Analyst says: {structure_msg}\n\n"
        f"Momentum Analyst says: {momentum_msg}\n\n"
        f"Make the final call on technicals alone."
    )


def _clean_message(text: str) -> str:
    """Unwrap an analyst reply that came back as JSON (e.g. {"output": "..."})
    into its inner text, so chat bubbles never show raw JSON."""
    t = (text or "").strip()
    if t.startswith("{") and t.endswith("}"):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                for value in data.values():
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except json.JSONDecodeError:
            pass
    return t


def _ask(llm, system: str, user: str):
    """One agent turn; None on any failure (the agent abstains). Raw reply —
    the Manager's JSON must reach parse_manager intact."""
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
    """Run the 3-agent technical debate; return transcript + Manager verdict.

    `headlines` and `calendar_block` are accepted for call-site compatibility
    but ignored — the War Room is technical-only.
    """
    del headlines, calendar_block  # unused; kept in signature for callers
    structure = _clean_message(
        _ask(
            llm, _STRUCTURE_SYSTEM,
            _setup_prompt(setup, timeframe, "structure / levels / R:R"),
        ) or ""
    ) or "(The Structure Analyst abstains — no response.)"
    momentum = _clean_message(
        _ask(
            llm, _MOMENTUM_SYSTEM,
            _setup_prompt(setup, timeframe, "momentum / timing / HTF"),
        ) or ""
    ) or "(The Momentum Analyst abstains — no response.)"
    manager_reply = _ask(
        llm, _MANAGER_SYSTEM,
        _manager_prompt(setup, timeframe, structure, momentum),
    )
    verdict, confidence, rationale = parse_manager(manager_reply or "")

    transcript = [
        {**STRUCTURE, "message": structure},
        {**MOMENTUM, "message": momentum},
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
