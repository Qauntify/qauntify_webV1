"""Sends confirmed-signal alerts to Telegram (Bot API sendMessage)."""
import html

import requests

from signals.models import Signal


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


def send_alert(signal: Signal, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one alert; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": format_alert(signal),
            "parse_mode": "HTML",
        },
        timeout=15,
    )
    response.raise_for_status()
