"""Configuration loaded from environment / .env file."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    sealion_api_key: str
    cryptopanic_api_key: str
    symbols: tuple = ("BTCUSDT", "ETHUSDT")
    timeframe: str = "1h"
    candle_limit: int = 200
    db_path: str = "signals.db"
    json_path: str = "signals.json"
    sealion_base_url: str = "https://api.sea-lion.ai/v1"
    sealion_model: str = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


def load_config() -> Config:
    load_dotenv()
    sealion_key = os.environ.get("SEALION_API_KEY", "")
    cryptopanic_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
    if not sealion_key:
        raise SystemExit("SEALION_API_KEY is not set (copy .env.example to .env)")
    if not cryptopanic_key:
        raise SystemExit("CRYPTOPANIC_API_KEY is not set (copy .env.example to .env)")
    return Config(sealion_api_key=sealion_key, cryptopanic_api_key=cryptopanic_key)
