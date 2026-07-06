"""Configuration loaded from environment / .env file."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    sealion_api_key: str
    supabase_url: str
    supabase_service_key: str
    symbols: tuple = ("BTCUSDT", "ETHUSDT")
    timeframe: str = "1h"
    candle_limit: int = 201  # one extra: the last fetched candle is still forming and gets dropped
    sealion_base_url: str = "https://api.sea-lion.ai/v1"
    sealion_model: str = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


def load_config() -> Config:
    load_dotenv()
    sealion_key = os.environ.get("SEALION_API_KEY", "")
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not sealion_key:
        raise SystemExit("SEALION_API_KEY is not set (copy .env.example to .env)")
    if not supabase_url:
        raise SystemExit("SUPABASE_URL is not set (copy .env.example to .env)")
    if not supabase_service_key:
        raise SystemExit(
            "SUPABASE_SERVICE_ROLE_KEY is not set (copy .env.example to .env)"
        )
    return Config(
        sealion_api_key=sealion_key,
        supabase_url=supabase_url.rstrip("/"),
        supabase_service_key=supabase_service_key,
    )
