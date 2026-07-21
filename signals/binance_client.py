"""Backward-compatible alias — market data now comes from Kraken USD. """
from signals.market_client import fetch_candles

__all__ = ["fetch_candles"]
