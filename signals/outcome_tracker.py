"""Checks open signals against fresh candles and closes TP/SL hits.

Signals are never deleted: a hit flips status to tp_hit/sl_hit and stamps
closed_at. Runs as part of every engine run, after scanning.
"""
from datetime import datetime, timezone

from signals.binance_client import fetch_candles
from signals.storage import close_signal, list_open_signals
from signals.telegram_client import send_outcome_alert


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


def track_open_signals(cfg) -> list:
    """Close every open signal whose TP or SL has been reached; returns the
    closed rows as (row, status) pairs. Never raises — outcome tracking must
    not break a scan run."""
    try:
        open_rows = list_open_signals(cfg.supabase_url, cfg.supabase_service_key)
    except Exception as exc:
        print(f"outcome tracking unavailable ({type(exc).__name__}) — "
              "has supabase/schema.sql been re-run for the status column?")
        return []
    if not open_rows:
        return []

    candles_by_symbol: dict = {}
    closed = []
    for row in open_rows:
        symbol = row["symbol"]
        if symbol not in candles_by_symbol:
            try:
                # Drop the still-forming candle: only closed bars decide hits.
                candles_by_symbol[symbol] = fetch_candles(
                    symbol, cfg.timeframe, cfg.candle_limit,
                )[:-1]
            except Exception as exc:
                print(f"[{symbol}] outcome check skipped, no market data: {exc}")
                candles_by_symbol[symbol] = []
        outcome = check_outcome(row, candles_by_symbol[symbol])
        if outcome is None:
            continue
        closed_at = datetime.now(timezone.utc).isoformat()
        try:
            close_signal(row["id"], outcome, closed_at,
                         cfg.supabase_url, cfg.supabase_service_key)
        except Exception as exc:
            print(f"[{symbol}] failed to mark {outcome} "
                  f"({type(exc).__name__}), will retry next run")
            continue
        print(f"[{symbol}] {outcome.upper().replace('_', ' ')} — "
              f"{row['direction']} from {row['entry']}")
        closed.append((row, outcome))
        if cfg.telegram_bot_token and cfg.telegram_chat_id:
            try:
                send_outcome_alert(row, outcome, cfg.telegram_bot_token,
                                   cfg.telegram_chat_id)
                print(f"[{symbol}] Telegram outcome alert sent")
            except Exception as exc:
                print(f"[{symbol}] Telegram outcome alert failed "
                      f"({type(exc).__name__}), continuing")
    return closed
