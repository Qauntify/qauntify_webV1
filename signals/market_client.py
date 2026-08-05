"""Fetches OHLCV candles (no API key required).

Crypto + FX (BTCUSD, ETHUSD, GBPUSD) come from Kraken public OHLC.
Legacy PAXG* symbols canonicalize to XAUUSD so older rows still settle.

Gold OHLC is Kraken PAXGUSD (tokenized physical gold), not COMEX futures.
The app symbol stays XAUUSD for storage and alerts so existing rows and MT5
EA config stay unchanged; only the price feed changed. PAXG tracks spot bullion
closely enough for CFD/MT5 XAUUSD execution. Yahoo GC=F was removed because
futures trade ~40–60 USD above spot and made 1m scalp entries look wrong on
broker charts.
"""
from __future__ import annotations

import requests

from signals.models import Candle

OHLC_URL = "https://api.kraken.com/0/public/OHLC"
TICKER_URL = "https://api.kraken.com/0/public/Ticker"
# Kraken pair for all XAUUSD/PAXG* candle fetches (spot gold proxy).
KRAKEN_GOLD_PAIR = "PAXGUSD"

# App symbol → Kraken pair name accepted by /public/OHLC.
KRAKEN_PAIR_BY_SYMBOL = {
    "BTCUSD": "XBTUSD",
    "ETHUSD": "ETHUSD",
    "GBPUSD": "GBPUSD",
    "PAXGUSD": "PAXGUSD",
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




def _fetch_kraken_gold_candles(interval, limit, start_time, session):
    """Spot-gold OHLC via PAXGUSD; 4h uses Kraken's native 240m bucket."""
    return _fetch_kraken_candles(
        KRAKEN_GOLD_PAIR, interval, limit, start_time, session,
    )


def _parse_kraken_last_price(payload: dict, pair_hint: str) -> float:
    errors = payload.get("error") or []
    if errors:
        raise RuntimeError(f"Kraken ticker error: {errors}")
    result = payload.get("result") or {}
    hint = pair_hint.upper()
    for key, data in result.items():
        if not isinstance(data, dict):
            continue
        if key.upper() == hint or hint in key.upper():
            last = (data.get("c") or [None])[0]
            if last is not None:
                return float(last)
    for data in result.values():
        if isinstance(data, dict):
            last = (data.get("c") or [None])[0]
            if last is not None:
                return float(last)
    raise RuntimeError("Kraken ticker returned no last price")


def fetch_kraken_last_price(pair: str, session=None) -> float:
    """Last trade price for a Kraken pair (live ticker, not OHLC close)."""
    session = session or requests.Session()
    response = session.get(
        TICKER_URL, params={"pair": pair}, timeout=10,
    )
    response.raise_for_status()
    return _parse_kraken_last_price(response.json(), pair)


def fetch_gold_last_price(session=None) -> float:
    return fetch_kraken_last_price(KRAKEN_GOLD_PAIR, session=session)


def max_gold_entry_drift(timeframe: str, atr: float | None) -> float:
    """Max allowed |entry - live| before a gold signal is treated as stale."""
    base = {"1m": 2.5, "5m": 4.0, "15m": 6.0}.get(timeframe, 8.0)
    if atr is not None and atr > 0:
        scale = {"1m": 0.25, "5m": 0.3, "15m": 0.35}.get(timeframe, 0.4)
        base = max(base, min(12.0, scale * atr))
    return base


def gold_entry_live_ok(entry: float, live: float, timeframe: str,
                       atr: float | None) -> tuple[bool, str]:
    drift = abs(entry - live)
    cap = max_gold_entry_drift(timeframe, atr)
    if drift <= cap:
        return True, ""
    return (
        False,
        f"Entry {entry:.2f} is {drift:.2f} from live PAXG {live:.2f} "
        f"(max {cap:.2f} for {timeframe}) — refusing stale levels.",
    )


def fetch_candles(symbol, interval="1h", limit=200, start_time=None,
                  session=None):
    """Return candles newest-last, same shape as the old Binance client.

    `start_time` is epoch **milliseconds** (engine convention).
    """
    session = session or requests.Session()
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"unsupported interval: {interval}")

    if is_gold_symbol(symbol):
        candles = _fetch_kraken_gold_candles(interval, limit, start_time, session)
    else:
        candles = _fetch_kraken_candles(
            symbol, interval, limit, start_time, session,
        )

    if start_time is not None:
        candles = [c for c in candles if c.open_time >= int(start_time)]

    if limit is not None and limit > 0 and len(candles) > limit:
        candles = candles[-limit:]

    return candles
