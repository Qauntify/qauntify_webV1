"""Fetches OHLCV candles (no API key required).

Crypto + FX (BTCUSD, ETHUSD, GBPUSD) come from Kraken public OHLC.
Legacy PAXG* symbols canonicalize to XAUUSD so older rows still settle.

Gold OHLC prefers closed MT5 1m bars (pushed by QauntifyTickPush) when the
EA ring buffer is warm; otherwise Kraken PAXGUSD. App symbol stays XAUUSD.
Yahoo GC=F futures were removed — they sat ~40–60 USD above broker spot.
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
        f"Entry {entry:.2f} is {drift:.2f} from live broker {live:.2f} "
        f"(max {cap:.2f} for {timeframe}) — refusing stale levels.",
    )


# Minimum |entry - stop| / |entry|. Tight stops pay disproportionate spread
# cost in R and were ~30% of historical SL rows at the bottom of this band.
MIN_STOP_RISK_FRACTION = 0.00097


def stop_risk_fraction(entry: float, stop_loss: float) -> float:
    if entry == 0:
        return 0.0
    return abs(entry - stop_loss) / abs(entry)


def setup_stop_risk_ok(entry: float, stop_loss: float, *,
                       min_fraction: float = MIN_STOP_RISK_FRACTION
                       ) -> tuple[bool, str]:
    frac = stop_risk_fraction(entry, stop_loss)
    if frac >= min_fraction:
        return True, ""
    return (
        False,
        f"Stop distance {frac * 100:.3f}% of entry is below "
        f"{min_fraction * 100:.3f}% minimum — refusing tight stop.",
    )


def fetch_candles(symbol, interval="1h", limit=200, start_time=None,
                  session=None, *, supabase_url=None, service_key=None,
                  require_mt5_1m: bool | None = None):
    """Return candles newest-last, same shape as the old Binance client.

    `start_time` is epoch **milliseconds** (engine convention).
    For XAUUSD 1m with Supabase credentials, uses the MT5 closed-bar buffer
    only. When that buffer is cold, raises (default) so detection never
    mixes PAXG structure with broker entries. Pass
    `require_mt5_1m=False` to allow a Kraken PAXG fallback (legacy / offline).
    """
    session = session or requests.Session()
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"unsupported interval: {interval}")

    gold_1m = is_gold_symbol(symbol) and interval == "1m"
    must_mt5 = require_mt5_1m if require_mt5_1m is not None else (
        gold_1m and bool(supabase_url and service_key)
    )

    if gold_1m and supabase_url and service_key:
        from signals.storage import (
            fetch_mt5_candles,
            mt5_candles_usable,
            mt5_rows_to_candles,
        )
        rows = fetch_mt5_candles(
            symbol, "1m", supabase_url, service_key, session=session,
        )
        if mt5_candles_usable(rows):
            candles = mt5_rows_to_candles(rows)
            if start_time is not None:
                candles = [c for c in candles if c.open_time >= int(start_time)]
            if limit is not None and limit > 0 and len(candles) > limit:
                candles = candles[-limit:]
            # Callers drop candles[:-1] assuming a still-forming bar exists
            # (Kraken). MT5 buffer is closed-only — append a synthetic forming
            # bar so the closed history survives that slice.
            if candles:
                last = candles[-1]
                candles = list(candles) + [
                    Candle(
                        open_time=last.open_time + 60_000,
                        open=last.close,
                        high=last.close,
                        low=last.close,
                        close=last.close,
                        volume=0.0,
                    )
                ]
            print(f"[{canonical_symbol(symbol)}] using MT5 1m candles "
                  f"({len(candles) - 1} closed bars)")
            return candles
        if must_mt5:
            raise RuntimeError(
                f"MT5 1m candles unavailable for {canonical_symbol(symbol)} "
                f"(have {len(rows)} bars; need EA backfill) — "
                f"refusing PAXG structure"
            )

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
