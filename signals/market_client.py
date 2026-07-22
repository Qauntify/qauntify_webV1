"""Fetches OHLCV candles (no API key required).

Crypto + FX (BTCUSD, ETHUSD, GBPUSD) come from Kraken public OHLC.
Spot-style gold (XAUUSD) comes from Yahoo Finance COMEX gold futures
(GC=F) — Kraken has no XAUUSD pair. Legacy PAXG* symbols canonicalize to
XAUUSD so older rows still settle.
"""
from __future__ import annotations

import requests

from signals.models import Candle

OHLC_URL = "https://api.kraken.com/0/public/OHLC"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"

# App symbol → Kraken pair name accepted by /public/OHLC.
KRAKEN_PAIR_BY_SYMBOL = {
    "BTCUSD": "XBTUSD",
    "ETHUSD": "ETHUSD",
    "GBPUSD": "GBPUSD",
    # Legacy Binance USDT symbols (outcome tracking / old rows).
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "GBPUSDT": "GBPUSD",
}

GOLD_SYMBOLS = frozenset({"XAUUSD", "XAUUSDT", "PAXGUSD", "PAXGUSDT"})

INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Yahoo chart interval + range for each engine timeframe.
YAHOO_INTERVAL = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "1mo"),
    "30m": ("30m", "1mo"),
    "1h": ("60m", "3mo"),
    "4h": ("1h", "6mo"),
    "1d": ("1d", "2y"),
}


def canonical_symbol(symbol: str) -> str:
    """Normalize to a USD quote symbol (BTCUSDT → BTCUSD, PAXG* → XAUUSD)."""
    s = (symbol or "").strip().upper()
    if s in GOLD_SYMBOLS or s.startswith("PAXG") or s.startswith("XAU"):
        return "XAUUSD"
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}USD"
    return s


def is_gold_symbol(symbol: str) -> bool:
    return canonical_symbol(symbol) == "XAUUSD"


def kraken_pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s in KRAKEN_PAIR_BY_SYMBOL:
        return KRAKEN_PAIR_BY_SYMBOL[s]
    canon = canonical_symbol(s)
    if canon in KRAKEN_PAIR_BY_SYMBOL:
        return KRAKEN_PAIR_BY_SYMBOL[canon]
    # Fallback: pass through (Kraken accepts many altnames like SOLUSD).
    return canon.replace("BTC", "XBT") if canon.startswith("BTC") else canon


def _fetch_kraken_candles(symbol, interval, limit, start_time, session):
    minutes = INTERVAL_MINUTES[interval]
    pair = kraken_pair(symbol)
    params = {"pair": pair, "interval": minutes}
    if start_time is not None:
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

    return [
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


def _fetch_yahoo_gold_candles(interval, limit, start_time, session):
    yahoo_interval, yahoo_range = YAHOO_INTERVAL.get(interval, ("60m", "3mo"))
    response = session.get(
        YAHOO_CHART_URL,
        params={"interval": yahoo_interval, "range": yahoo_range},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        error = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo gold chart error: {error}")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    candles: list[Candle] = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = (
            opens[i] if i < len(opens) else None,
            highs[i] if i < len(highs) else None,
            lows[i] if i < len(lows) else None,
            closes[i] if i < len(closes) else None,
        )
        if o is None or h is None or l is None or c is None:
            continue
        vol = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
        candles.append(
            Candle(
                open_time=int(ts) * 1000,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(vol),
            )
        )
    return candles


def fetch_candles(symbol, interval="1h", limit=200, start_time=None,
                  session=None):
    """Return candles newest-last, same shape as the old Binance client.

    `start_time` is epoch **milliseconds** (engine convention).
    """
    session = session or requests.Session()
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"unsupported interval: {interval}")

    if is_gold_symbol(symbol):
        candles = _fetch_yahoo_gold_candles(interval, limit, start_time, session)
    else:
        candles = _fetch_kraken_candles(
            symbol, interval, limit, start_time, session,
        )

    if start_time is not None:
        candles = [c for c in candles if c.open_time >= int(start_time)]

    if limit is not None and limit > 0 and len(candles) > limit:
        candles = candles[-limit:]

    return candles
