"""Fetches OHLCV candles from Binance's public REST API (no key required)."""
import requests

from signals.models import Candle

# Official public market-data host; api.binance.com is DNS-blocked on some
# networks and this engine only needs public data anyway.
KLINES_URL = "https://data-api.binance.vision/api/v3/klines"


def fetch_candles(symbol, interval="1h", limit=200, start_time=None,
                  session=None):
    """`start_time` (epoch ms) fetches history forward from that moment
    instead of the trailing window — used to cover a signal's whole life."""
    session = session or requests.Session()
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = start_time
    response = session.get(
        KLINES_URL,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return [
        Candle(
            open_time=row[0],
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in response.json()
    ]
