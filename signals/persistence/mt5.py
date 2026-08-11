"""MT5 tick/candle persistence (Supabase table + Storage fallback) and the
gold-drift signal-expiry helper that reads/writes those quotes."""
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from signals.clients.market import canonical_symbol
from signals.persistence.signals import list_open_signals, update_signal_outcome

# Prefer MT5 broker mid when fresher than this; gold publish requires it.
MT5_TICK_MAX_AGE_SECONDS = 45
# Open gold signals this far from live are treated as futures-era junk.
GOLD_OPEN_DRIFT_EXPIRE = 25.0
MT5_TICK_BUCKET = "signal-charts"
MT5_TICK_OBJECT_PREFIX = "mt5-last-ticks"


def _mt5_tick_object_path(symbol: str) -> str:
    return f"{MT5_TICK_OBJECT_PREFIX}/{canonical_symbol(symbol)}.json"


def _normalize_mt5_quotes(price=None, *, bid=None, ask=None, mid=None) -> dict:
    """Build bid/ask/mid/price from any partial quote payload."""
    b = bid if bid is not None else price
    a = ask if ask is not None else price
    if b is None or a is None:
        raise ValueError("MT5 quote needs bid/ask or price")
    b, a = float(b), float(a)
    if a < b:
        b, a = a, b
    m = float(mid) if mid is not None else (b + a) / 2.0
    return {"bid": b, "ask": a, "mid": m, "price": m}


def _upsert_mt5_tick_table(symbol: str, quotes: dict, tick_time_iso: str,
                           supabase_url: str, service_key: str,
                           session) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    response = session.post(
        f"{supabase_url}/rest/v1/mt5_last_ticks",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json={
            "symbol": canonical_symbol(symbol),
            "price": quotes["price"],
            "bid": quotes["bid"],
            "ask": quotes["ask"],
            "mid": quotes["mid"],
            "tick_time": tick_time_iso,
            "updated_at": now,
        },
        timeout=10,
    )
    if response.status_code in (404, 406):
        return False
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = {}
        # Missing table, or extra columns not migrated yet.
        if isinstance(detail, dict) and detail.get("code") in ("PGRST205", "PGRST204"):
            # Retry minimal columns if new columns are unknown.
            if detail.get("code") == "PGRST204":
                response = session.post(
                    f"{supabase_url}/rest/v1/mt5_last_ticks",
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    json={
                        "symbol": canonical_symbol(symbol),
                        "price": quotes["price"],
                        "tick_time": tick_time_iso,
                        "updated_at": now,
                    },
                    timeout=10,
                )
                if response.status_code < 400 or response.status_code in (200, 201):
                    return True
            return False
        response.raise_for_status()
    return True


def _upsert_mt5_tick_storage(symbol: str, quotes: dict, tick_time_iso: str,
                             supabase_url: str, service_key: str,
                             session) -> None:
    import json

    now = datetime.now(timezone.utc).isoformat()
    path = _mt5_tick_object_path(symbol)
    payload = json.dumps({
        "symbol": canonical_symbol(symbol),
        **quotes,
        "tick_time": tick_time_iso,
        "updated_at": now,
    }).encode("utf-8")
    response = session.post(
        f"{supabase_url}/storage/v1/object/{MT5_TICK_BUCKET}/{path}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
        data=payload,
        timeout=10,
    )
    response.raise_for_status()


def upsert_mt5_last_tick(symbol: str, price=None, tick_time_iso: str = "",
                         supabase_url: str = "", service_key: str = "",
                         session=None, *, bid=None, ask=None, mid=None) -> None:
    """Persist latest MT5 quote (table if migrated, else Storage JSON).

    Accepts legacy positional `price` or explicit bid/ask/mid.
    """
    session = session or requests.Session()
    quotes = _normalize_mt5_quotes(price, bid=bid, ask=ask, mid=mid)
    if _upsert_mt5_tick_table(
        symbol, quotes, tick_time_iso, supabase_url, service_key, session,
    ):
        return
    _upsert_mt5_tick_storage(
        symbol, quotes, tick_time_iso, supabase_url, service_key, session,
    )


def _row_to_mt5_tick(row: dict, symbol: str) -> dict:
    price = row.get("price")
    bid = row.get("bid", price)
    ask = row.get("ask", price)
    mid = row.get("mid", price)
    quotes = _normalize_mt5_quotes(price, bid=bid, ask=ask, mid=mid)
    return {
        "symbol": row.get("symbol") or canonical_symbol(symbol),
        **quotes,
        "tick_time": row.get("tick_time"),
        "updated_at": row.get("updated_at"),
    }


def _fetch_mt5_tick_table(symbol: str, supabase_url: str, service_key: str,
                          session) -> dict | None:
    canon = canonical_symbol(symbol)
    response = session.get(
        f"{supabase_url}/rest/v1/mt5_last_ticks"
        f"?symbol=eq.{quote(canon)}"
        "&select=symbol,price,bid,ask,mid,tick_time,updated_at&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=10,
    )
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = {}
        # Older table without bid/ask columns — retry minimal select.
        if isinstance(detail, dict) and detail.get("code") in ("PGRST205", "PGRST204"):
            if detail.get("code") == "PGRST205":
                return None
            response = session.get(
                f"{supabase_url}/rest/v1/mt5_last_ticks"
                f"?symbol=eq.{quote(canon)}"
                "&select=symbol,price,tick_time,updated_at&limit=1",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                },
                timeout=10,
            )
            if response.status_code >= 400:
                return None
        else:
            response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        return None
    return _row_to_mt5_tick(rows[0], symbol)


def _fetch_mt5_tick_storage(symbol: str, supabase_url: str, service_key: str,
                            session) -> dict | None:
    import json

    path = _mt5_tick_object_path(symbol)
    response = session.get(
        f"{supabase_url}/storage/v1/object/{MT5_TICK_BUCKET}/{path}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json() if hasattr(response, "json") else json.loads(response.content)
    if isinstance(data, (bytes, bytearray, str)):
        data = json.loads(data)
    if not isinstance(data, dict) or "price" not in data:
        return None
    return _row_to_mt5_tick(data, symbol)


def fetch_mt5_last_tick(symbol: str, supabase_url: str, service_key: str,
                        session=None) -> dict | None:
    """Latest stored MT5 tick for `symbol`, or None if missing / unavailable."""
    session = session or requests.Session()
    try:
        row = _fetch_mt5_tick_table(symbol, supabase_url, service_key, session)
        if row is not None:
            return row
        return _fetch_mt5_tick_storage(symbol, supabase_url, service_key, session)
    except Exception as exc:
        print(f"mt5_last_ticks fetch failed ({type(exc).__name__})")
        return None


MT5_CANDLE_MAX_BARS = 14_400  # ~10 days of M1 — enough to resample 1h/4h
# Match ict structure window so a partial EA backfill can go live sooner.
MT5_CANDLE_MIN_BARS = 60
# Last closed M1 bar must be newer than now - this (seconds).
MT5_CANDLE_MAX_STALE_SECONDS = 180


def _mt5_candle_object_path(symbol: str, timeframe: str = "1m") -> str:
    return f"mt5-candles/{canonical_symbol(symbol)}-{timeframe}.json"


def merge_mt5_candle_bars(existing: list, incoming: list,
                          *, max_bars: int = MT5_CANDLE_MAX_BARS) -> list:
    """Merge OHLC dicts keyed by open_time (unix seconds); return oldest→newest."""
    by_time: dict[int, dict] = {}
    for row in existing:
        try:
            t = int(row["open_time"])
        except (TypeError, ValueError, KeyError):
            continue
        by_time[t] = row
    for row in incoming:
        try:
            t = int(row["open_time"])
        except (TypeError, ValueError, KeyError):
            continue
        by_time[t] = {
            "open_time": t,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume") or 0),
        }
    out = [by_time[t] for t in sorted(by_time)]
    if max_bars and len(out) > max_bars:
        out = out[-max_bars:]
    return out


def fetch_mt5_candles(symbol: str, timeframe: str, supabase_url: str,
                      service_key: str, session=None) -> list:
    """Closed MT5 OHLC bars from Storage (dicts with open_time in seconds)."""
    import json

    session = session or requests.Session()
    path = _mt5_candle_object_path(symbol, timeframe)
    try:
        response = session.get(
            f"{supabase_url}/storage/v1/object/{MT5_TICK_BUCKET}/{path}",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=15,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        if isinstance(data, (bytes, bytearray, str)):
            data = json.loads(data)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("candles") or []
        else:
            return []
        rows = merge_mt5_candle_bars([], rows)
        # Drop discontinuous junk clusters (old test seed), keep live chain.
        if rows:
            rows = purge_mt5_candle_outliers(rows, float(rows[-1]["close"]))
        return rows
    except Exception as exc:
        print(f"mt5 candles fetch failed ({type(exc).__name__})")
        return []


def mt5_candles_usable(rows: list, *,
                       min_bars: int = MT5_CANDLE_MIN_BARS,
                       max_stale_seconds: int = MT5_CANDLE_MAX_STALE_SECONDS
                       ) -> bool:
    if len(rows) < min_bars:
        return False
    try:
        last_open = int(rows[-1]["open_time"])
    except (TypeError, ValueError, KeyError):
        return False
    # Closed M1 bar open_time is ~60s behind "now"; allow a little slack.
    age = datetime.now(timezone.utc).timestamp() - last_open
    return 0 <= age <= max_stale_seconds + 60


def mt5_rows_to_candles(rows: list):
    """Convert Storage rows (open_time seconds) to engine Candle list (ms)."""
    from signals.models import Candle

    out = []
    for row in rows:
        out.append(Candle(
            open_time=int(row["open_time"]) * 1000,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume") or 0),
        ))
    return out


def purge_mt5_candle_outliers(rows: list, ref_price: float | None = None,
                              *, max_drift: float | None = None) -> list:
    """Drop discontinuous junk clusters (e.g. old ~4120 test seed).

    Walks newest→oldest. Keeps a bar when its close is within `max_drift` of
    the previous kept close (chained), so gradual live moves survive while a
    sudden jump to an old seed cluster is cut off.

    Default drift is price-relative: gold 1m often moves well past a flat $15
    step during news — a tight cap was shredding live history and leaving
    holes on outcome charts when the setup snapshot was merged back in.
    """
    if not rows:
        return []
    ordered = merge_mt5_candle_bars([], rows)
    kept_rev: list = []
    try:
        ref = float(ref_price) if ref_price is not None else float(ordered[-1]["close"])
    except (TypeError, ValueError, KeyError):
        return ordered
    # ~1.5% of price, floored at $80 — still far below a ~$900 junk-seed jump.
    if max_drift is None:
        max_drift = max(80.0, abs(ref) * 0.015)
    for row in reversed(ordered):
        try:
            close = float(row["close"])
        except (TypeError, ValueError, KeyError):
            continue
        if abs(close - ref) <= max_drift:
            kept_rev.append(row)
            ref = close
    kept_rev.reverse()
    return kept_rev


def write_mt5_candles(symbol: str, timeframe: str, rows: list,
                      supabase_url: str, service_key: str,
                      session=None) -> None:
    """Overwrite the MT5 candle Storage object with `rows`."""
    import json

    session = session or requests.Session()
    path = _mt5_candle_object_path(symbol, timeframe)
    payload = json.dumps({
        "symbol": canonical_symbol(symbol),
        "timeframe": timeframe,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "candles": merge_mt5_candle_bars([], rows),
    }).encode("utf-8")
    response = session.post(
        f"{supabase_url}/storage/v1/object/{MT5_TICK_BUCKET}/{path}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
        data=payload,
        timeout=20,
    )
    response.raise_for_status()


def mt5_tick_is_fresh(tick: dict | None, *,
                      max_age_seconds: int = MT5_TICK_MAX_AGE_SECONDS) -> bool:
    if not tick:
        return False
    raw = tick.get("tick_time") or tick.get("updated_at")
    if not raw:
        return False
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - when).total_seconds()
    return 0 <= age <= max_age_seconds


def expire_drifted_open_gold_signals(
    live_price: float,
    supabase_url: str,
    service_key: str,
    *,
    max_drift: float = GOLD_OPEN_DRIFT_EXPIRE,
    session=None,
) -> int:
    """Expire open XAUUSD rows whose entry is wildly off live (old futures feed).

    Returns how many rows were closed. Failures are swallowed so scans continue.
    """
    session = session or requests.Session()
    try:
        rows = list_open_signals(supabase_url, service_key, session=session)
    except Exception as exc:
        print(f"expire drifted gold: list failed ({type(exc).__name__})")
        return 0
    closed = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if canonical_symbol(row.get("symbol") or "") != "XAUUSD":
            continue
        if (row.get("status") or "open") != "open":
            continue
        try:
            entry = float(row["entry"])
        except (TypeError, ValueError, KeyError):
            continue
        if abs(entry - live_price) < max_drift:
            continue
        try:
            claimed = update_signal_outcome(
                row["id"], "expired", now, supabase_url, service_key,
                terminal=True, expected_status="open", session=session,
            )
            if claimed:
                closed += 1
                print(
                    f"[XAUUSD] expired drifted open signal {row['id']} "
                    f"entry={entry:.2f} live={live_price:.2f}"
                )
        except Exception as exc:
            print(f"expire drifted gold {row.get('id')}: {type(exc).__name__}")
    return closed
