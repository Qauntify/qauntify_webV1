"""Fetches OHLCV candles from Kraken's public REST API (no key required).

Symbols are stored/displayed as USD pairs (BTCUSD, ETHUSD, …). Legacy
USDT names still resolve so open signals from the Binance era can settle.
"""
from __future__ import annotations

import requests

from signals.models import Candle

OHLC_URL = "https://api.kraken.com/0/public/OHLC"

# App symbol → Kraken pair name accepted by /public/OHLC.
KRAKEN_PAIR_BY_SYMBOL = {
    "BTCUSD": "XBTUSD",
    "ETHUSD": "ETHUSD",
    "PAXGUSD": "PAXGUSD",
    "GBPUSD": "GBPUSD",
    # Legacy Binance USDT symbols (outcome tracking / old rows).
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "PAXGUSDT": "PAXGUSD",
    "GBPUSDT": "GBPUSD",
}

INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def canonical_symbol(symbol: str) -> str:
    """Normalize to a USD quote symbol (BTCUSDT → BTCUSD)."""
    s = (symbol or "").strip().upper()
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}USD"
    return s


def kraken_pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s in KRAKEN_PAIR_BY_SYMBOL:
        return KRAKEN_PAIR_BY_SYMBOL[s]
    canon = canonical_symbol(s)
    if canon in KRAKEN_PAIR_BY_SYMBOL:
        return KRAKEN_PAIR_BY_SYMBOL[canon]
    # Fallback: pass through (Kraken accepts many altnames like SOLUSD).
    return canon.replace("BTC", "XBT") if canon.startswith("BTC") else canon


def fetch_candles(symbol, interval="1h", limit=200, start_time=None,
                  session=None):
    """Return candles newest-last, same shape as the old Binance client.

    `start_time` is epoch **milliseconds** (engine convention). Kraken only
    serves the most recent ~720 bars; rows before `start_time` are filtered
    out client-side when provided.
    """
    session = session or requests.Session()
    minutes = INTERVAL_MINUTES.get(interval)
    if minutes is None:
        raise ValueError(f"unsupported interval: {interval}")

    pair = kraken_pair(symbol)
    params = {"pair": pair, "interval": minutes}
    if start_time is not None:
        # Kraken `since` is unix seconds; request from just before the window.
        params["since"] = max(0, int(start_time) // 1000 - minutes * 60)

    response = session.get(OHLC_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("error") or []
    if errors:
        raise RuntimeError(f"Kraken OHLC error: {errors}")

    result = payload.get("result") or {}
    rows = None
    for key, value in result.items():
        if key == "last":
            continue
        if isinstance(value, list):
            rows = value
            break
    if not rows:
        return []

    candles = [
        Candle(
            open_time=int(row[0]) * 1000,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[6]),
        )
        for row in rows
        if isinstance(row, (list, tuple)) and len(row) >= 7
    ]

    if start_time is not None:
        candles = [c for c in candles if c.open_time >= int(start_time)]

    if limit is not None and limit > 0 and len(candles) > limit:
        candles = candles[-limit:]

    return candles
