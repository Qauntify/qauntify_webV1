"""Checks open signals against fresh candles and closes TP/SL hits.

Signals are never deleted: a hit flips status to tp_hit/sl_hit and stamps
closed_at; a signal open past MAX_OPEN_DAYS is closed as expired so stale
setups stop counting as live. Runs as part of every engine run, after
scanning.
"""
from datetime import datetime, timedelta, timezone

from signals.binance_client import fetch_candles
from signals.storage import close_signal, list_open_signals
from signals.telegram_client import send_outcome_alert

# A 1h setup unresolved after two weeks is no longer the trade the engine
# proposed; expiring it keeps the win-rate denominator honest.
MAX_OPEN_DAYS = 14
# Enough hourly candles to cover the full expiry window in one fetch.
HISTORY_LIMIT = 1000


def check_outcome(signal_row: dict, candles: list) -> str | None:
    """First outcome reached by candles fully after the signal's creation:
    'tp_hit', 'sl_hit', or None while still open.

    Only candles that OPENED at/after created_at count, so price movement
    from before the signal existed can never close it. When one candle
    spans both levels, the stop wins — the conservative read.
    """
    created_ms = datetime.fromisoformat(signal_row["created_at"]).timestamp() * 1000
    is_long = signal_row["direction"] == "long"
    stop = signal_row["stop_loss"]
    target = signal_row["take_profit"]
    for candle in candles:
        if candle.open_time < created_ms:
            continue
        if is_long:
            if candle.low <= stop:
                return "sl_hit"
            if candle.high >= target:
                return "tp_hit"
        else:
            if candle.high >= stop:
                return "sl_hit"
            if candle.low <= target:
                return "tp_hit"
    return None


def track_open_signals(cfg, prefetched=None, session=None) -> list:
    """Close every open signal whose TP or SL has been reached, and expire
    signals open past MAX_OPEN_DAYS; returns the closed rows as (row, status)
    pairs. Never raises — outcome tracking must not break a scan run.

    `prefetched` maps symbol -> closed candles already fetched by the scan;
    a signal's history is refetched from its created_at only when the scan
    candles don't reach back that far."""
    try:
        open_rows = list_open_signals(cfg.supabase_url,
                                      cfg.supabase_service_key,
                                      session=session)
    except Exception as exc:
        print(f"outcome tracking unavailable ({type(exc).__name__}) — "
              "has supabase/schema.sql been re-run for the status column?")
        return []
    if not open_rows:
        return []

    prefetched = prefetched or {}
    fetch_cache: dict = {}

    def candles_covering(symbol, created_ms):
        """Closed candles spanning the signal's life, or None when market
        data is unavailable (skip the row and retry next run)."""
        pre = prefetched.get(symbol)
        if pre and pre[0].open_time <= created_ms:
            return pre
        key = (symbol, created_ms)
        if key not in fetch_cache:
            try:
                # Drop the still-forming candle: only closed bars decide hits.
                fetch_cache[key] = fetch_candles(
                    symbol, cfg.timeframe, HISTORY_LIMIT,
                    start_time=int(created_ms), session=session,
                )[:-1]
            except Exception as exc:
                print(f"[{symbol}] outcome check skipped, no market data: {exc}")
                fetch_cache[key] = None
        return fetch_cache[key]

    now = datetime.now(timezone.utc)
    closed = []
    for row in open_rows:
        symbol = row["symbol"]
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + timedelta(days=MAX_OPEN_DAYS)
        candles = candles_covering(symbol, created_ms)
        if candles is None:
            continue
        # Hits only count inside the expiry window: a level touched weeks
        # later is not the trade the engine proposed.
        expiry_ms = expires_at.timestamp() * 1000
        outcome = check_outcome(
            row, [c for c in candles if c.open_time < expiry_ms])
        if outcome is None and now >= expires_at:
            outcome = "expired"
        if outcome is None:
            continue
        closed_at = now.isoformat()
        try:
            close_signal(row["id"], outcome, closed_at,
                         cfg.supabase_url, cfg.supabase_service_key,
                         session=session)
        except Exception as exc:
            print(f"[{symbol}] failed to mark {outcome} "
                  f"({type(exc).__name__}), will retry next run")
            continue
        print(f"[{symbol}] {outcome.upper().replace('_', ' ')} — "
              f"{row['direction']} from {row['entry']}")
        closed.append((row, outcome))
        # Expiry is bookkeeping, not a tradeable outcome — no alert.
        if (outcome in ("tp_hit", "sl_hit")
                and cfg.telegram_bot_token and cfg.telegram_chat_id):
            try:
                send_outcome_alert(row, outcome, cfg.telegram_bot_token,
                                   cfg.telegram_chat_id)
                print(f"[{symbol}] Telegram outcome alert sent")
            except Exception as exc:
                print(f"[{symbol}] Telegram outcome alert failed "
                      f"({type(exc).__name__}), continuing")
    return closed
