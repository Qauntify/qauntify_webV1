"""Alerts when a trading session has logged zero ai_events in the last
few hours — the failure mode that let 15m cloud_mss silently produce zero
signals for five days (2026-07-31 to 2026-08-05, fixed in composer.py).

Posts to TELEGRAM_ALERTS_CHAT_ID, deliberately separate from the public
signals channel (TELEGRAM_CHANNEL_ID) so an ops alert never shows up next
to a trade call. Exits 1 when a session is silent so the GitHub Actions run
also shows red, independent of whether Telegram delivery succeeds.

Usage: .venv/bin/python -m scripts.session_healthcheck
"""
import sys

from signals.config import load_config
from signals.healthcheck import check_session_health, format_healthcheck_alert
from signals.telegram_client import send_message


def main() -> int:
    cfg = load_config()
    results = check_session_health(cfg.supabase_url, cfg.supabase_service_key)
    for r in results:
        status = "silent" if r.silent else f"last event {r.last_event_at}"
        print(f"[{r.session}] {r.timeframe}: {status}")

    alert = format_healthcheck_alert(results)
    if alert is None:
        print("All sessions healthy.")
        return 0

    print("UNHEALTHY:", alert.replace("\n", " "))
    if cfg.telegram_bot_token and cfg.telegram_alerts_chat_id:
        send_message(alert, cfg.telegram_bot_token, cfg.telegram_alerts_chat_id)
    else:
        print("TELEGRAM_ALERTS_CHAT_ID not set — alert logged here only.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
