"""AI War Room: Structure + Momentum + Manager (Trading Floor).

Used by the independent Floor pipeline to gate War Room-only signals.
Fail-soft: any agent error becomes an abstention; the Manager still returns
a (safe) verdict.
"""
import json
from dataclasses import dataclass

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

# When the Floor publishes live War Room signals, agree = store the trade.
_MANAGER_GATE_SYSTEM = (
    "You are the Manager on the Trading Floor. Structure and Momentum have "
    "briefed you on a candidate trade. You alone decide whether to PUBLISH "
    "it to the War Room feed.\n"
    "agree = publish the trade. caution or reject = do not publish.\n"
    "Weigh both technical views only. Respond with ONLY a JSON object:\n"
    '{"verdict": "agree" | "caution" | "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short sentence>"}'
)


@dataclass(frozen=True)
class FloorAgents:
    """One SEA-LION client per Floor desk (do not reuse strategy-engine keys)."""
    structure: object
    momentum: object
    manager: object


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
    """(verdict, confidence, rationale) from the Manager's JSON."""
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


def run_debate(setup, llm=None, *, timeframe: str, headlines=None,
               calendar_block=None, agents: FloorAgents | None = None,
               gate: bool = False) -> dict:
    """Run the 3-agent technical debate; return transcript + Manager verdict.

    Prefer `agents` (per-desk Floor clients). Falls back to a single `llm` for
    all three turns when agents is None. `gate=True` uses the publish-or-not
    Manager prompt for the live War Room pipeline.
    """
    del headlines, calendar_block
    structure_llm = agents.structure if agents is not None else llm
    momentum_llm = agents.momentum if agents is not None else llm
    manager_llm = agents.manager if agents is not None else llm
    if structure_llm is None or momentum_llm is None or manager_llm is None:
        raise ValueError("run_debate requires llm or FloorAgents")

    manager_system = _MANAGER_GATE_SYSTEM if gate else _MANAGER_SYSTEM
    structure = _clean_message(
        _ask(
            structure_llm, _STRUCTURE_SYSTEM,
            _setup_prompt(setup, timeframe, "structure / levels / R:R"),
        ) or ""
    ) or "(The Structure Analyst abstains — no response.)"
    momentum = _clean_message(
        _ask(
            momentum_llm, _MOMENTUM_SYSTEM,
            _setup_prompt(setup, timeframe, "momentum / timing / HTF"),
        ) or ""
    ) or "(The Momentum Analyst abstains — no response.)"
    manager_reply = _ask(
        manager_llm, manager_system,
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
