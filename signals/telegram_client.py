"""Sends signal and no-signal alerts to Telegram (Bot API sendMessage)."""
import html

import requests

from signals.models import NoSignalReport, Signal


def format_alert(signal: Signal) -> str:
    """Telegram HTML-mode message for one confirmed signal."""
    emoji = "\U0001F7E2" if signal.direction == "long" else "\U0001F534"
    return (
        f"{emoji} <b>{signal.direction.upper()} {html.escape(signal.symbol)}</b>"
        f" ({html.escape(signal.timeframe)})\n"
        f"Entry {signal.entry:g} | SL {signal.stop_loss:g}"
        f" | TP {signal.take_profit:g}\n"
        f"Confidence {signal.confidence}%\n"
        f"{html.escape(signal.rationale)}"
    )


def format_no_signal_alert(report: NoSignalReport) -> str:
    """Telegram HTML-mode message explaining why no signal was stored."""
    ind = report.indicators
    indicator_line = (
        f"EMA9 {ind['ema9']:.2f} | EMA21 {ind['ema21']:.2f} | "
        f"RSI {ind['rsi']:.1f} | MACD {ind['macd_hist']:.4f}"
    )
    if report.kind == "rejected":
        header = (
            f"\U0001F6AB <b>REJECTED {html.escape(report.symbol)}</b>"
            f" ({html.escape(report.timeframe)})"
        )
        trade_line = (
            f"{html.escape(report.direction.upper())} candidate"
            f" @ {report.entry:g} | SL {report.stop_loss:g}"
            f" | TP {report.take_profit:g}\n"
            f"Confidence {report.confidence}%"
        )
        body = f"{header}\n{trade_line}\n{indicator_line}\n{html.escape(report.rationale)}"
    else:
        header = (
            f"\u26AA <b>NO SIGNAL {html.escape(report.symbol)}</b>"
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
