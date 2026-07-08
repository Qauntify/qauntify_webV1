#!/usr/bin/env python3
"""Send a real Telegram message to confirm push notifications are wired up.

Usage:
  python scripts/test_telegram_push.py
  python scripts/test_telegram_push.py --message "custom text"

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID from the environment (or
.env) — the same two values the engine uses for every real alert.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from signals.telegram_client import send_message

DEFAULT_MESSAGE = (
    "✅ <b>Qauntify push notification test</b>\n"
    "If you can see this, TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID are "
    "wired up correctly."
)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Send a real Telegram message to verify push notifications work",
    )
    parser.add_argument(
        "--message", default=DEFAULT_MESSAGE,
        help="Custom message text (HTML parse mode)",
    )
    args = parser.parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 2
    if not channel_id:
        print("TELEGRAM_CHANNEL_ID is not set", file=sys.stderr)
        return 2

    try:
        send_message(args.message, token, channel_id)
    except Exception as exc:
        print(f"Failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Sent. Check the Telegram chat/channel for {channel_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
