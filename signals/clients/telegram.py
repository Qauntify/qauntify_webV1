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


def _confluence_badge(signal: Signal) -> str:
    """A short banner line when `signal` is a confluence publish -- empty
    string for every ordinary signal."""
    tags = (signal.indicators or {}).get("confluence_of")
    if not tags:
        return ""
    names = " + ".join(_esc(str(t)) for t in tags)
    return f"\U0001F525 <b>CONFLUENCE</b>  {names}\n\n"


def _risk_reward(entry: float, stop: float, target: float) -> str:
    risk = abs(entry - stop)
    if risk == 0:
        return "—"
    return f"1 : {abs(target - entry) / risk:.1f}"


def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal.

    Carries the breakeven instruction because the engine depends on it. Every
    trade is scored as thirds booked at TP1/TP2/TP3 with the stop trailed to
    entry once TP1 banks, and `outcome_tracker` settles live trades that way.
    A follower who never moves the stop is not making the trade the public
    track record reports, so this cannot live only in a methodology page.
    """
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    symbol = _esc(signal.symbol)
    timeframe = _esc(signal.timeframe)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    badge = _confluence_badge(signal)
    return (
        f"{badge}{dot} <b>{direction} SIGNAL</b>\n"
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
        f"↩️ Once TP1 hits, <b>move your stop to entry</b>\n"
        f"\n"
        f"⚖️ <b>Risk : Reward</b>  {_risk_reward(signal.entry, signal.stop_loss, tp3)}\n"
        f"\n"
        f"🧠 <b>Analysis</b>\n"
        f"<i>{_esc(signal.rationale)}</i>"
    )


def format_caption(signal: Signal) -> str:
    """Compact caption essentials for the chart photo (symbol, levels, R:R).
    `send_alert` appends the AI analysis on top of this when it fits under the
    caption limit, or sends it as a follow-up message when it doesn't."""
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    badge = _confluence_badge(signal)
    return (
        f"{badge}{dot} <b>{direction} SIGNAL</b>\n"
        f"💹 <b>{_esc(signal.symbol)}</b> · <code>{_esc(signal.timeframe)}</code>\n"
        f"🎯 Confidence {signal.confidence}%\n"
        f"📍 Entry {_price(signal.entry)}  🛑 SL {_price(signal.stop_loss)}\n"
        f"🎯 TP {_price(signal.take_profit)} / {_price(tp2)} / {_price(tp3)}\n"
        f"↩️ TP1 hit → move SL to entry\n"
        f"⚖️ R:R {_risk_reward(signal.entry, signal.stop_loss, tp3)}"
    )


def send_photo(photo_url: str, caption: str, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one photo message; raises on failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = (response.json() or {}).get("description") or ""
        except Exception:
            detail = (response.text or "")[:200]
        raise requests.HTTPError(
            f"{response.status_code} Telegram photo failed"
            + (f": {detail}" if detail else ""),
            response=response,
        )
    response.raise_for_status()


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
    if indicators.get("strategy") == "cloud_mss" or "cloud_low" in indicators:
        parts = []
        if "side" in indicators:
            parts.append(str(indicators["side"]))
        if "cloud_low" in indicators and "cloud_high" in indicators:
            parts.append(
                f"cloud {indicators['cloud_low']:.2f}-{indicators['cloud_high']:.2f}"
            )
        if "atr" in indicators:
            parts.append(f"ATR {indicators['atr']:.2f}")
        if "adx" in indicators:
            parts.append(f"ADX {indicators['adx']:.1f}")
        return " | ".join(parts) if parts else "Cloud/MSS context"
    if indicators.get("strategy") in ("bbma_extreme", "bbma_reentry") or "bb_upper" in indicators:
        parts = []
        if "side" in indicators:
            parts.append(str(indicators["side"]))
        if "bb_upper" in indicators and "bb_lower" in indicators:
            parts.append(
                f"BB {indicators['bb_lower']:.2f}-{indicators['bb_upper']:.2f}"
            )
        if "atr" in indicators:
            parts.append(f"ATR {indicators['atr']:.2f}")
        return " | ".join(parts) if parts else "BBMA context"
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


# Telegram caps photo captions at 1024 UTF-16 units; stay conservative since
# emojis count as 2. Longer analysis is sent as a separate follow-up message.
_CAPTION_LIMIT = 1000


def _analysis_text(signal: Signal) -> str:
    return f"🧠 <b>Analysis</b>\n<i>{_esc(signal.rationale)}</i>"


def send_alert(signal: Signal, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one confirmed-signal alert. With a chart: a photo whose caption is
    the setup essentials plus the AI analysis (or, if that overflows the caption
    limit, the essentials as the caption and the analysis as a follow-up
    message). Without a chart: the full text alert."""
    if not getattr(signal, "chart_url", None):
        send_message(format_alert(signal), bot_token, chat_id, session=session)
        return

    caption = format_caption(signal)
    analysis = _analysis_text(signal) if signal.rationale else ""
    if analysis and len(caption) + len(analysis) + 2 <= _CAPTION_LIMIT:
        send_photo(signal.chart_url, f"{caption}\n\n{analysis}", bot_token,
                   chat_id, session=session)
    else:
        send_photo(signal.chart_url, caption, bot_token, chat_id, session=session)
        if analysis:
            send_message(analysis, bot_token, chat_id, session=session)


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

    move = float(exit_price) - entry
    if direction == "short":
        move = -move
    trend = "📈" if move >= 0 else "📉"

    lines = [
        f"{emoji} <b>{title}</b>",
        _DIVIDER,
        f"{dot} <b>{symbol}</b>  ·  <b>{arrow} {direction_label}</b>  ·  "
        f"{trend} <b>{move:+.2f} pips</b>",
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
    """Send one TP/SL-hit alert — a photo when an outcome chart exists,
    otherwise the text message."""
    text = format_outcome_alert(signal_row, outcome)
    url = signal_row.get("outcome_chart_url")
    if url:
        send_photo(url, text, bot_token, chat_id, session=session)
    else:
        send_message(text, bot_token, chat_id, session=session)


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
