"""Builds the confirmation prompt, calls the LLM, and parses the verdict.

Fail-closed: any LLM failure or unparseable reply becomes a reject so an
unconfirmed signal is never stored.
"""
import json

from signals.models import DEFAULT_SIGNAL_STRATEGY, CandidateSetup, Confirmation

SYSTEM_PROMPT = (
    "You are a balanced trading-signal reviewer. You receive a candidate "
    "trade setup derived from technical rules, the current FX market session "
    "(Asia / London / New York), and optional retrieved context (similar past "
    "outcomes, prior AI decisions, and strategy playbook rules). The rules "
    "engine already filtered this setup — confirm when the chart and levels "
    "are sound; do not hunt for reasons to reject.\n"
    "This is a purely technical review — judge the chart and the levels.\n"
    "Retrieved context is evidence, not a hard veto — weigh it with the "
    "live setup.\n"
    "Confirm when risk/reward is workable, the session fits the timeframe, "
    "and there is no clear technical conflict (e.g. HTF trend directly "
    "opposed or structure plainly broken). When borderline but valid, lean "
    "confirm with moderate confidence (55–72) rather than reject.\n"
    "Reject only on clear disqualifiers — bad R:R, strong HTF opposition, "
    "or a setup that plainly fails the strategy rules.\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "confirm" or "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short paragraph explaining your decision>"}'
)

# Super Scalp (5m) only — maximize confirms; volume over perfection.
# Must match signals/strategies/ict_fvg/detector.py entry priority:
# FVG retest, or sweep+CHoCH without FVG, or sweep reclaim alone.
SUPER_SCALP_SYSTEM_PROMPT = (
    "You are a high-throughput Super Scalp (5m) reviewer. The rules engine "
    "already found a valid ict_fvg candidate — one of: (1) liquidity sweep + "
    "CHoCH + FVG retest, (2) sweep + CHoCH without FVG, or (3) sweep reclaim "
    "(close back through the swept level). Treat that as the default pass. "
    "Prefer confirming so the live feed stays active.\n"
    "This is a purely technical review — judge the chart and the levels.\n"
    "Retrieved context is evidence, not a hard veto.\n"
    "DEFAULT TO CONFIRM. Borderline or imperfect structure still gets "
    "confirm at confidence 50–65. Soft HTF disagreement is not enough to "
    "reject on 5m. Missing FVG alone is NOT a reject when CHoCH or reclaim "
    "is present.\n"
    "Reject ONLY on hard disqualifiers: stop already invalid vs entry, "
    "nonsensical R:R (targets on the wrong side of entry), or a setup that "
    "plainly fails every ict_fvg path (no sweep AND no CHoCH AND no reclaim).\n"
    "Do not hunt for reasons to reject.\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "confirm" or "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short paragraph explaining your decision>"}'
)


def _system_prompt_for(timeframe: str) -> str:
    """5m Super Scalp uses the hot confirm prompt; other sessions stay balanced."""
    if timeframe == "5m":
        return SUPER_SCALP_SYSTEM_PROMPT
    return SYSTEM_PROMPT


def _no_setup_reason(strategy: str, timeframe: str) -> str:
    chart = f"{timeframe} chart" if timeframe else "chart"
    if strategy == "ict_smc":
        return (
            f"The rules engine found no valid ICT/SMC setup (no recent "
            f"liquidity sweep followed by a structure shift / CHoCH on the "
            f"{chart})."
        )
    if strategy == "ict_fvg":
        return (
            f"The rules engine found no valid ICT FVG scalp setup (need a "
            f"liquidity sweep with CHoCH and/or FVG retest, or a sweep "
            f"reclaim, on the {chart})."
        )
    if strategy == "ce_lwma":
        return (
            f"The rules engine found no valid CE+LWMA setup (no fresh H1 "
            f"Chandelier Exit flip into the matching discount/premium zone "
            f"on the {chart})."
        )
    if strategy == "sr_zone":
        return (
            f"The rules engine found no valid Support/Resistance bounce (no "
            f"tested S/R zone with a confirmation candle rejecting the level "
            f"on the {chart})."
        )
    if strategy == "cloud_mss":
        return (
            f"The rules engine found no valid cloud rejection + market "
            f"structure shift setup (no H1 Chandelier/MA200 cloud rejection "
            f"with a CHoCH on the {chart})."
        )
    if strategy in ("bbma_extreme", "bbma_reentry"):
        return (
            f"The rules engine found no valid BBMA setup (no Bollinger "
            f"Band {'extreme touch' if strategy == 'bbma_extreme' else 're-entry trigger'} "
            f"confirmed by the MA5/MA10 stack on the {chart})."
        )
    return (
        f"The rules engine found no valid trade setup (no EMA 9/21 crossover "
        f"with aligned RSI and MACD filters on the last few {timeframe or 'hourly'} "
        f"bars)."
    )


def no_setup_rationale(symbol: str, timeframe: str, indicators: dict,
                       strategy: str = DEFAULT_SIGNAL_STRATEGY) -> str:
    """Deterministic no-setup copy — avoids burning an LLM call every quiet scan."""
    reason = _no_setup_reason(strategy, timeframe)
    context = _format_indicators(strategy, indicators)
    return (
        f"{symbol} {timeframe}: {reason} "
        f"Current readings: {context}."
    )


def _format_indicators(strategy: str, indicators: dict) -> str:
    active = indicators.get("strategy", strategy)
    if active == "ict_fvg":
        parts = []
        for key, label in (
            ("structure", "structure"),
            ("sweep_level", "sweep level"),
            ("choch_level", "CHoCH level"),
            ("fvg_bottom", "FVG low"),
            ("fvg_top", "FVG high"),
            ("atr", "ATR"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no ICT FVG reading"
    if active == "ce_lwma":
        parts = []
        for key, label in (
            ("ce_trail", "CE trail"),
            ("ce_direction", "CE dir"),
            ("lwma200", "LWMA200"),
            ("zone", "zone"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no CE/LWMA reading"
    if active == "sr_zone":
        parts = []
        for key, label in (
            ("side", "side"),
            ("zone_low", "zone low"),
            ("zone_high", "zone high"),
            ("touches", "touches"),
            ("atr", "ATR"),
            ("adx", "ADX"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no S/R zone reading"
    if active == "ict_smc":
        parts = []
        for key, label in (
            ("structure", "structure"),
            ("sweep_level", "sweep level"),
            ("choch_level", "CHoCH level"),
            ("sweep_low", "sweep low"),
            ("sweep_high", "sweep high"),
            ("atr", "ATR"),
            ("adx", "ADX"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        if "ema9" in indicators and "ema21" in indicators:
            parts.append(
                f"EMA9={indicators['ema9']:.2f}, EMA21={indicators['ema21']:.2f}"
            )
        if "rsi" in indicators:
            parts.append(f"RSI={indicators['rsi']:.1f}")
        return ", ".join(parts) if parts else "no ICT structure on chart"
    if active == "cloud_mss":
        parts = []
        for key, label in (
            ("side", "side"),
            ("ce_trend", "CE trend"),
            ("cloud_low", "cloud low"),
            ("cloud_high", "cloud high"),
            ("ma200", "MA200"),
            ("choch_level", "CHoCH level"),
            ("atr", "ATR"),
            ("adx", "ADX"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no cloud/MSS reading"
    if active in ("bbma_extreme", "bbma_reentry"):
        parts = []
        for key, label in (
            ("side", "side"),
            ("trigger", "trigger"),
            ("bb_upper", "BB upper"),
            ("bb_mid", "BB mid"),
            ("bb_lower", "BB lower"),
            ("ma5h", "MA5 high"),
            ("ma5l", "MA5 low"),
            ("ma10h", "MA10 high"),
            ("ma10l", "MA10 low"),
            ("ema50", "EMA50"),
            ("atr", "ATR"),
            ("adx", "ADX"),
            ("htf_trend", "HTF trend"),
        ):
            if key in indicators:
                value = indicators[key]
                if isinstance(value, float):
                    parts.append(f"{label}={value:.4f}")
                else:
                    parts.append(f"{label}={value}")
        return ", ".join(parts) if parts else "no BBMA reading"
    if "ema9" not in indicators:
        # Defence in depth: an unrecognised strategy must not crash the
        # confirmation prompt (that fails closed and silently auto-rejects
        # every candidate — see cloud_mss's 2026-08-05 incident). Fall back
        # to whatever numeric readings are present instead of assuming the
        # ema_cross key set.
        parts = [f"{key}={value}" for key, value in indicators.items()
                 if key != "strategy"]
        return ", ".join(parts) if parts else "no indicator reading"
    parts = [
        f"EMA9={indicators['ema9']:.2f}",
        f"EMA21={indicators['ema21']:.2f}",
        f"RSI={indicators['rsi']:.1f}",
        f"MACD hist={indicators['macd_hist']:.4f}",
    ]
    if "adx" in indicators:
        parts.append(f"ADX={indicators['adx']:.1f}")
    if "htf_trend" in indicators:
        parts.append(f"HTF trend={indicators['htf_trend']}")
    return ", ".join(parts)


def _tp_r_labels(setup: CandidateSetup) -> tuple[str, str, str]:
    """R-multiple labels for the three TPs (from indicators or classic 1/2/3)."""
    raw = (setup.indicators or {}).get("tp_r")
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        def _fmt(r) -> str:
            try:
                v = float(r)
            except (TypeError, ValueError):
                return "?"
            return f"{v:g}R"
        return _fmt(raw[0]), _fmt(raw[1]), _fmt(raw[2])
    return "1R", "2R", "3R"


def build_messages(setup: CandidateSetup,
                   strategy: str = DEFAULT_SIGNAL_STRATEGY,
                   timeframe: str = "1h",
                   *,
                   session_context: str | None = None,
                   rag_block: str | None = None) -> list:
    ind = setup.indicators
    active = ind.get("strategy", strategy)
    if active == "ict_smc":
        strategy_line = (
            "- Strategy: ICT/SMC (liquidity sweep + structure shift)\n"
        )
    elif active == "ce_lwma":
        strategy_line = (
            "- Strategy: H1 Chandelier Exit flip + M15 LWMA200 zone "
            "(discount/premium)\n"
        )
    elif active == "ict_fvg":
        structure = ind.get("structure") or "ict_fvg"
        strategy_line = (
            f"- Strategy: ICT 5m scalp ({structure}; paths: FVG retest, "
            f"sweep+CHoCH, or sweep reclaim; tight 0.5R/1R/1.5R targets)\n"
        )
    elif active == "sr_zone":
        strategy_line = (
            "- Strategy: Support/Resistance bounce (rejection candle at a "
            "tested S/R zone)\n"
        )
    elif active == "cloud_mss":
        strategy_line = (
            "- Strategy: Cloud rejection + market structure shift (H1 "
            "Chandelier/MA200 cloud rejection with a CHoCH)\n"
        )
    elif active == "bbma_extreme":
        strategy_line = (
            "- Strategy: BBMA Extreme (price extends outside the Bollinger "
            "Band, confirmed against the MA5/MA10 stack)\n"
        )
    elif active == "bbma_reentry":
        strategy_line = (
            "- Strategy: BBMA Re-entry (CSM/CSAK trigger back inside the "
            "Bollinger Band toward the MA5/MA10 stack)\n"
        )
    else:
        strategy_line = (
            "- Strategy: EMA 9/21 crossover with RSI + MACD filters\n"
        )
    tp1, tp2, tp3 = setup.resolved_take_profits()
    r1, r2, r3 = _tp_r_labels(setup)
    session_hint = (
        "super scalp" if timeframe == "5m"
        else ("scalp" if timeframe in ("15m",) else "swing")
    )
    session_line = session_context or "Market session: unavailable"
    rag_section = f"\n\n{rag_block}" if rag_block else ""
    user_content = (
        f"Candidate setup:\n"
        f"{strategy_line}"
        f"- Symbol: {setup.symbol}\n"
        f"- Timeframe: {timeframe} ({session_hint})\n"
        f"- Direction: {setup.direction}\n"
        f"- Entry: {setup.entry}\n"
        f"- Stop loss: {setup.stop_loss}\n"
        f"- Take profit 1 ({r1}): {tp1}\n"
        f"- Take profit 2 ({r2}): {tp2}\n"
        f"- Take profit 3 ({r3}): {tp3}\n"
        f"- Context: {_format_indicators(strategy, ind)}\n\n"
        f"{session_line}"
        f"{rag_section}"
    )
    return [
        {"role": "system", "content": _system_prompt_for(timeframe)},
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


def confirm_setup(setup: CandidateSetup, llm,
                  strategy: str = DEFAULT_SIGNAL_STRATEGY,
                  timeframe: str = "1h",
                  *,
                  session_context: str | None = None,
                  rag_block: str | None = None) -> Confirmation:
    try:
        reply = llm.chat(
            build_messages(
                setup, strategy=strategy, timeframe=timeframe,
                session_context=session_context,
                rag_block=rag_block,
            ),
        )
        return parse_confirmation(reply)
    except Exception as exc:
        return Confirmation("reject", 0, f"LLM call failed: {exc}")


def no_setup_system_prompt(strategy: str = DEFAULT_SIGNAL_STRATEGY,
                           timeframe: str = "1h") -> str:
    reason = _no_setup_reason(strategy, timeframe)
    return (
        "You are a disciplined trading analyst. You receive the current "
        "technical readings for a market pair (crypto, gold, or forex) and "
        f"recent news headlines. {reason} Explain briefly why conditions do "
        "not support a long or short entry right now.\n"
        "Respond with ONLY a JSON object, no other text:\n"
        '{"rationale": "<one short paragraph>"}'
    )


NO_SETUP_SYSTEM_PROMPT = no_setup_system_prompt()


def build_no_setup_messages(symbol, timeframe, indicators, headlines,
                            strategy: str = DEFAULT_SIGNAL_STRATEGY) -> list:
    if headlines:
        news_block = "\n".join(f"- {h}" for h in headlines)
    else:
        news_block = "No recent headlines available."
    user_content = (
        f"Market snapshot:\n"
        f"- Symbol: {symbol}\n"
        f"- Timeframe: {timeframe}\n"
        f"- Strategy: {strategy}\n"
        f"- Readings: {_format_indicators(strategy, indicators)}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
    return [
        {"role": "system", "content": no_setup_system_prompt(strategy, timeframe)},
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


def explain_no_setup(symbol, timeframe, indicators, headlines, llm,
                     strategy: str = DEFAULT_SIGNAL_STRATEGY) -> str:
    """Legacy LLM path kept for tests; production uses no_setup_rationale."""
    try:
        reply = llm.chat(build_no_setup_messages(
            symbol, timeframe, indicators, headlines, strategy=strategy,
        ))
        return parse_rationale(reply)
    except Exception as exc:
        return f"LLM call failed: {exc}"
