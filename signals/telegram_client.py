"""Sends confirmed-signal and SL/TP outcome alerts to Telegram."""
import html

import requests

from signals.models import NoSignalReport, Signal

_DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
_SUBDIVIDER = "────────────────────"


def _esc(text: str) -> str:
    return html.escape(text)


def _price(value: float) -> str:
    return f"<code>{value:g}</code>"


def _header(title: str) -> str:
    return f"<b>{_DIVIDER}\n  {_esc(title)}\n{_DIVIDER}</b>"


def _subsection(title: str) -> str:
    return f"<b>{_esc(title)}</b>"


def _direction_arrow(direction: str) -> str:
    return "▲" if direction == "long" else "▼"


def _direction_dot(direction: str) -> str:
    return "🟢" if direction == "long" else "🔴"


def _confidence_bar(pct: int, segments: int = 10) -> str:
    """A 10-segment ▰/▱ meter for the confidence percentage."""
    filled = max(0, min(segments, round(pct / 100 * segments)))
    return "▰" * filled + "▱" * (segments - filled)


def _risk_reward(entry: float, stop: float, target: float) -> str:
    risk = abs(entry - stop)
    if risk == 0:
        return "—"
    return f"1 : {abs(target - entry) / risk:.1f}"


def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal."""
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    symbol = _esc(signal.symbol)
    timeframe = _esc(signal.timeframe)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    return (
        f"{dot} <b>{direction} SIGNAL</b>\n"
        f"{_DIVIDER}\n"
        f"💹 <b>{symbol}</b>  ·  <code>{timeframe}</code>\n"
        f"\n"
        f"🎯 <b>Confidence</b>  {signal.confidence}%\n"
        f"{_confidence_bar(signal.confidence)}\n"
        f"\n"
        f"📊 <b>Trade Setup</b>\n"
        f"📍 Entry   {_price(signal.entry)}\n"
        f"🛑 Stop    {_price(signal.stop_loss)}\n"
        f"🎯 TP1     {_price(signal.take_profit)}\n"
        f"🎯 TP2     {_price(tp2)}\n"
        f"🎯 TP3     {_price(tp3)}\n"
        f"\n"
        f"⚖️ <b>Risk : Reward</b>  {_risk_reward(signal.entry, signal.stop_loss, tp3)}\n"
        f"\n"
        f"🧠 <b>Analysis</b>\n"
        f"<i>{_esc(signal.rationale)}</i>"
    )


def _indicator_line(indicators: dict) -> str:
    if indicators.get("strategy") == "sr_zone" or "zone_low" in indicators:
        parts = []
        if "side" in indicators:
            parts.append(str(indicators["side"]))
        if "zone_low" in indicators and "zone_high" in indicators:
            parts.append(
                f"zone {indicators['zone_low']:.2f}-{indicators['zone_high']:.2f}"
            )
        if "atr" in indicators:
            parts.append(f"ATR {indicators['atr']:.2f}")
        if "adx" in indicators:
            parts.append(f"ADX {indicators['adx']:.1f}")
        return " | ".join(parts) if parts else "S/R context"
    if indicators.get("strategy") == "ict_smc" or "structure" in indicators:
        parts = []
        if "structure" in indicators:
            parts.append(f"structure {indicators['structure']}")
        if "atr" in indicators:
            parts.append(f"ATR {indicators['atr']:.2f}")
        if "adx" in indicators:
            parts.append(f"ADX {indicators['adx']:.1f}")
        return " | ".join(parts) if parts else "ICT/SMC context"
    return (
        f"EMA9 {indicators.get('ema9', 0):.2f} | "
        f"EMA21 {indicators.get('ema21', 0):.2f} | "
        f"RSI {indicators.get('rsi', 0):.1f} | "
        f"MACD {indicators.get('macd_hist', 0):.4f}"
    )


def format_no_signal_alert(report: NoSignalReport) -> str:
    """Telegram HTML-mode message explaining why no signal was stored."""
    symbol = _esc(report.symbol)
    timeframe = _esc(report.timeframe)
    indicator_line = _indicator_line(report.indicators)
    if report.kind == "rejected":
        direction = _esc((report.direction or "").upper())
        return (
            f"{_header('SIGNAL REJECTED')}\n"
            f"\n"
            f"<b>{symbol}</b>  ·  {timeframe}\n"
            f"\n"
            f"{_subsection('Candidate')}\n"
            f"{direction}  @  {_price(report.entry)}\n"
            f"Stop  {_price(report.stop_loss)}  ·  "
            f"TP  {_price(report.take_profit)}\n"
            f"Confidence  {report.confidence}%\n"
            f"\n"
            f"{_subsection('Market Context')}\n"
            f"{_esc(indicator_line)}\n"
            f"\n"
            f"{_subsection('Reason')}\n"
            f"<i>{_esc(report.rationale)}</i>"
        )
    return (
        f"{_header('NO SIGNAL')}\n"
        f"\n"
        f"<b>{symbol}</b>  ·  {timeframe}\n"
        f"\n"
        f"{_subsection('Market Context')}\n"
        f"{_esc(indicator_line)}\n"
        f"\n"
        f"{_subsection('Reason')}\n"
        f"<i>{_esc(report.rationale)}</i>"
    )


def send_message(text: str, bot_token: str, chat_id: str,
                 session=None) -> None:
    """Send one HTML message; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=15,
    )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = (response.json() or {}).get("description") or ""
        except Exception:
            detail = (response.text or "")[:200]
        raise requests.HTTPError(
            f"{response.status_code} Telegram send failed"
            + (f": {detail}" if detail else ""),
            response=response,
        )
    response.raise_for_status()


def send_alert(signal: Signal, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one confirmed-signal alert."""
    send_message(format_alert(signal), bot_token, chat_id, session=session)


def send_no_signal_alert(report: NoSignalReport, bot_token: str, chat_id: str,
                         session=None) -> None:
    """Send one no-signal explanation alert."""
    send_message(format_no_signal_alert(report), bot_token, chat_id,
                  session=session)


# emoji + title + optional "what's next" line, per outcome.
_OUTCOME_META = {
    "sl_hit": ("🛑", "STOP LOSS", ""),
    "tp1_hit": ("✅", "TP1 HIT", "Next target: TP2 🎯"),
    "tp2_hit": ("✅", "TP2 HIT", "Next target: TP3 🎯"),
    "tp3_hit": ("🏆", "TP3 HIT", "Final target reached 🎉"),
    "tp_hit": ("🏆", "TAKE PROFIT", "Target reached 🎉"),
}


def format_outcome_alert(signal_row: dict, outcome: str) -> str:
    """Telegram HTML-mode message for TP1/TP2/TP3 or SL hits."""
    entry = signal_row["entry"]
    direction = signal_row["direction"]
    direction_label = _esc(direction.upper())
    symbol = _esc(signal_row["symbol"])
    arrow = _direction_arrow(direction)
    dot = _direction_dot(direction)
    emoji, title, next_hint = _OUTCOME_META.get(
        outcome, ("•", outcome.upper().replace("_", " "), ""),
    )

    if outcome == "sl_hit":
        exit_price = signal_row["stop_loss"]
    else:
        tp_map = {
            "tp1_hit": signal_row.get("take_profit_1", signal_row.get("take_profit")),
            "tp2_hit": signal_row.get("take_profit_2"),
            "tp3_hit": signal_row.get("take_profit_3"),
            "tp_hit": signal_row.get("take_profit_3") or signal_row.get("take_profit"),
        }
        exit_price = tp_map.get(outcome) or signal_row.get("take_profit")

    move = (float(exit_price) - entry) / entry * 100
    if direction == "short":
        move = -move
    trend = "📈" if move >= 0 else "📉"

    lines = [
        f"{emoji} <b>{title}</b>",
        _DIVIDER,
        f"{dot} <b>{symbol}</b>  ·  <b>{arrow} {direction_label}</b>  ·  "
        f"{trend} <b>{move:+.2f}%</b>",
    ]
    if next_hint:
        lines.extend(["", f"<i>{next_hint}</i>"])
    lines.extend([
        "",
        f"📍 <b>Exit</b>",
        f"Entry  {_price(entry)}  →  {_price(float(exit_price))}",
    ])
    return "\n".join(lines)


def send_outcome_alert(signal_row: dict, outcome: str, bot_token: str,
                       chat_id: str, session=None) -> None:
    """Send one TP/SL-hit alert."""
    send_message(format_outcome_alert(signal_row, outcome), bot_token,
                 chat_id, session=session)


def format_run_summary(run_id: str, timeframe: str, outcomes: list[dict]) -> str:
    """Telegram HTML-mode summary that is sent every run."""
    lines = [
        _header("ENGINE RUN"),
        "",
        f"<b>Timeframe</b>  {_esc(timeframe)}",
        f"<b>Run ID</b>  <code>{_esc(run_id)}</code>",
    ]
    if not outcomes:
        lines.extend(["", "<i>No symbols scanned.</i>"])
        return "\n".join(lines)

    lines.extend(["", _subsection("Results"), _SUBDIVIDER])
    for o in outcomes:
        symbol = _esc(str(o.get("symbol", "")))
        tf = o.get("timeframe")
        if tf:
            symbol = f"{symbol} [{_esc(str(tf))}]"
        status = _esc(str(o.get("status", "")))
        extra = str(o.get("extra", "") or "")
        if extra:
            lines.append(f"{symbol}  ·  {status}  ·  {_esc(extra)}")
        else:
            lines.append(f"{symbol}  ·  {status}")
    return "\n".join(lines)


def send_run_summary(run_id: str, timeframe: str, outcomes: list[dict],
                     bot_token: str, chat_id: str, session=None) -> None:
    """Send the per-run summary (always)."""
    send_message(
        format_run_summary(run_id, timeframe, outcomes),
        bot_token,
        chat_id,
        session=session,
    )
