"""Sends confirmed-signal and SL/TP outcome alerts to Telegram."""
import html

import requests

from signals.models import NoSignalReport, Signal


def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal."""
    return (
        f"<b>{signal.direction.upper()} {html.escape(signal.symbol)}</b>"
        f" ({html.escape(signal.timeframe)})\n"
        f"Entry {signal.entry:g} | SL {signal.stop_loss:g}"
        f" | TP1 {signal.take_profit:g}"
        f" | TP2 {(signal.take_profit_2 or signal.take_profit):g}"
        f" | TP3 {(signal.take_profit_3 or signal.take_profit):g}\n"
        f"Confidence {signal.confidence}%\n"
        f"{html.escape(signal.rationale)}"
    )


def format_no_signal_alert(report: NoSignalReport) -> str:
    """Telegram HTML-mode message explaining why no signal was stored."""
    ind = report.indicators
    if ind.get("strategy") == "ict_smc" or "structure" in ind:
        parts = []
        if "structure" in ind:
            parts.append(f"structure {ind['structure']}")
        if "atr" in ind:
            parts.append(f"ATR {ind['atr']:.2f}")
        if "adx" in ind:
            parts.append(f"ADX {ind['adx']:.1f}")
        indicator_line = " | ".join(parts) if parts else "ICT/SMC context"
    else:
        indicator_line = (
            f"EMA9 {ind.get('ema9', 0):.2f} | EMA21 {ind.get('ema21', 0):.2f} | "
            f"RSI {ind.get('rsi', 0):.1f} | MACD {ind.get('macd_hist', 0):.4f}"
        )
    if report.kind == "rejected":
        header = (
            f"<b>REJECTED {html.escape(report.symbol)}</b>"
            f" ({html.escape(report.timeframe)})"
        )
        trade_line = (
            f"{html.escape((report.direction or '').upper())} candidate"
            f" @ {report.entry:g} | SL {report.stop_loss:g}"
            f" | TP {report.take_profit:g}\n"
            f"Confidence {report.confidence}%"
        )
        body = f"{header}\n{trade_line}\n{indicator_line}\n{html.escape(report.rationale)}"
    else:
        header = (
            f"<b>NO SIGNAL {html.escape(report.symbol)}</b>"
            f" ({html.escape(report.timeframe)})"
        )
        body = f"{header}\n{indicator_line}\n{html.escape(report.rationale)}"
    return body


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


def format_outcome_alert(signal_row: dict, outcome: str) -> str:
    """Telegram HTML-mode message for TP1/TP2/TP3 or SL hits."""
    entry = signal_row["entry"]
    direction = html.escape(signal_row["direction"].upper())
    symbol = html.escape(signal_row["symbol"])
    if outcome == "sl_hit":
        exit_price = signal_row["stop_loss"]
        move = (exit_price - entry) / entry * 100
        if signal_row["direction"] == "short":
            move = -move
        return (
            f"<b>SL HIT {symbol}</b> — {direction} {move:+.2f}%\n"
            f"Entry {entry:g} → {exit_price:g}"
        )
    # Resolve TP price for this level.
    tp_map = {
        "tp1_hit": signal_row.get("take_profit_1", signal_row.get("take_profit")),
        "tp2_hit": signal_row.get("take_profit_2"),
        "tp3_hit": signal_row.get("take_profit_3"),
        "tp_hit": signal_row.get("take_profit_3") or signal_row.get("take_profit"),
    }
    exit_price = tp_map.get(outcome) or signal_row.get("take_profit")
    move = (float(exit_price) - entry) / entry * 100
    if signal_row["direction"] == "short":
        move = -move
    labels = {
        "tp1_hit": "TP1 HIT",
        "tp2_hit": "TP2 HIT",
        "tp3_hit": "TP3 HIT",
        "tp_hit": "TP HIT",
    }
    header = labels.get(outcome, outcome.upper().replace("_", " "))
    next_hint = {
        "tp1_hit": " — running to TP2",
        "tp2_hit": " — running to TP3",
        "tp3_hit": "",
        "tp_hit": "",
    }.get(outcome, "")
    return (
        f"<b>{header} {symbol}</b> — {direction} {move:+.2f}%{next_hint}\n"
        f"Entry {entry:g} → {float(exit_price):g}"
    )


def send_outcome_alert(signal_row: dict, outcome: str, bot_token: str,
                       chat_id: str, session=None) -> None:
    """Send one TP/SL-hit alert."""
    send_message(format_outcome_alert(signal_row, outcome), bot_token,
                 chat_id, session=session)


def format_run_summary(run_id: str, timeframe: str, outcomes: list[dict]) -> str:
    """Telegram HTML-mode summary that is sent every run."""
    lines = [f"<b>ENGINE RUN</b> ({html.escape(timeframe)})", f"Run id: {html.escape(run_id)}"]
    if not outcomes:
        lines.append("No symbols scanned.")
        return "\n".join(lines)

    # One compact line per symbol to avoid spammy multi-paragraph messages.
    for o in outcomes:
        symbol = html.escape(str(o.get("symbol", "")))
        tf = o.get("timeframe")
        if tf:
            symbol = f"{symbol} [{html.escape(str(tf))}]"
        status = html.escape(str(o.get("status", "")))
        extra = str(o.get("extra", "") or "")
        extra = html.escape(extra)
        if extra:
            lines.append(f"{symbol}: {status} — {extra}")
        else:
            lines.append(f"{symbol}: {status}")
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
