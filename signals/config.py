"""Configuration loaded from environment / .env file."""
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv


def _sealion_keys() -> tuple:
    """Collect SEA-LION keys from the environment, first non-empty form wins:
    numbered SEALION_API_KEY1..N, comma-separated SEALION_API_KEYS, or the
    single legacy SEALION_API_KEY."""
    numbered = sorted(
        (
            (int(match.group(1)), value.strip())
            for name, value in os.environ.items()
            if (match := re.fullmatch(r"SEALION_API_KEY(\d+)", name))
            and value.strip()
        ),
    )
    if numbered:
        return tuple(value for _, value in numbered)
    from_list = tuple(
        k.strip()
        for k in os.environ.get("SEALION_API_KEYS", "").split(",")
        if k.strip()
    )
    if from_list:
        return from_list
    single = os.environ.get("SEALION_API_KEY", "").strip()
    return (single,) if single else ()


@dataclass(frozen=True)
class Config:
    sealion_api_key: str
    supabase_url: str
    supabase_service_key: str
    # All SEA-LION keys; symbols are spread across them round-robin so one
    # key's rate limit is never hit by the whole scan. Always includes
    # sealion_api_key when only the single-key env var is set.
    sealion_api_keys: tuple = ()
    # Optional: alerts are skipped when either is empty.
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    symbols: tuple = ("BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT")
    timeframe: str = "1h"
    candle_limit: int = 201  # one extra: the last fetched candle is still forming and gets dropped
    sealion_base_url: str = "https://api.sea-lion.ai/v1"
    sealion_model: str = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


def load_config() -> Config:
    load_dotenv()
    keys = _sealion_keys()
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not keys:
        raise SystemExit(
            "No SEA-LION key set: use SEALION_API_KEY1..4, SEALION_API_KEYS, "
            "or SEALION_API_KEY (copy .env.example to .env)"
        )
    if not supabase_url:
        raise SystemExit("SUPABASE_URL is not set (copy .env.example to .env)")
    if not supabase_service_key:
        raise SystemExit(
            "SUPABASE_SERVICE_ROLE_KEY is not set (copy .env.example to .env)"
        )
    return Config(
        sealion_api_key=keys[0],
        sealion_api_keys=keys,
        supabase_url=supabase_url.rstrip("/"),
        supabase_service_key=supabase_service_key,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        # Prefer CHANNEL_ID; fall back to legacy CHAT_ID if unset.
        telegram_channel_id=(
            os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
            or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        ),
    )
