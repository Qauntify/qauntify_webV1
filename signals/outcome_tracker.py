"""Checks open signals against fresh candles and closes TP/SL hits.

Signals are never deleted. Multi-TP ladder:
  open → tp1_hit → tp2_hit → tp3_hit (terminal win)
  sl_hit / expired can end the trade from any non-terminal state.
Telegram fires once per newly crossed level.
"""
from datetime import datetime, timedelta, timezone

from signals.market_client import fetch_candles
from signals.models import OPEN_POLL_STATUSES, TRADING_SESSIONS
from signals.storage import list_open_signals, update_signal_outcome
from signals.telegram_client import send_outcome_alert

_SESSION_BY_TIMEFRAME = {s.timeframe: s for s in TRADING_SESSIONS}
_DEFAULT_MAX_OPEN_DAYS = next(
    s.max_open_days for s in TRADING_SESSIONS if s.timeframe == "1h")
HISTORY_LIMIT = 1000

_TP_ORDER = ("tp1_hit", "tp2_hit", "tp3_hit")
_TERMINAL = frozenset({"tp3_hit", "sl_hit", "expired", "tp_hit"})


def _candle_closed_at(candle) -> str:
    return datetime.fromtimestamp(
        candle.open_time / 1000, tz=timezone.utc,
    ).isoformat()


def _targets(signal_row: dict) -> list[float]:
    """TP1/TP2/TP3 prices — fall back to single take_profit for legacy rows.

    Rows where TP2/TP3 were wrongly cloned to equal TP1 are treated as a
    single-target trade so one touch cannot mark all three levels.
    """
    tp1 = signal_row.get("take_profit_1", signal_row.get("take_profit"))
    tp2 = signal_row.get("take_profit_2")
    tp3 = signal_row.get("take_profit_3")
    if tp1 is None:
        return []
    tp1_f = float(tp1)
    if tp2 is None or tp3 is None:
        return [tp1_f]
    tp2_f, tp3_f = float(tp2), float(tp3)
    if tp2_f == tp1_f and tp3_f == tp1_f:
        return [tp1_f]
    return [tp1_f, tp2_f, tp3_f]


def _already_hit(signal_row: dict) -> set[str]:
    status = signal_row.get("status") or "open"
    hit = set()
    if status in ("tp1_hit", "tp2_hit", "tp3_hit", "tp_hit"):
        hit.add("tp1_hit")
    if status in ("tp2_hit", "tp3_hit"):
        hit.add("tp2_hit")
    if status in ("tp3_hit", "tp_hit"):
        hit.add("tp3_hit")
    # Prefer explicit timestamps when present.
    for level, col in (
        ("tp1_hit", "tp1_hit_at"),
        ("tp2_hit", "tp2_hit_at"),
        ("tp3_hit", "tp3_hit_at"),
    ):
        if signal_row.get(col):
            hit.add(level)
    return hit


def check_outcome_events(signal_row: dict, candles: list) -> list[tuple[str, str]]:
    """Ordered new events for this run: (status, closed_at_iso).

    Stop wins on a same-candle tie with any TP. A fast move can cross
    multiple unhit TPs in one candle — all are returned in order.
    """
    created_ms = datetime.fromisoformat(signal_row["created_at"]).timestamp() * 1000
    is_long = signal_row["direction"] == "long"
    stop = float(signal_row["stop_loss"])
    targets = _targets(signal_row)
    already = _already_hit(signal_row)
    events: list[tuple[str, str]] = []

    # Map target index → status name. Legacy single target closes as tp_hit
    # (and tp3_hit alias) for stats compatibility.
    if len(targets) == 1:
        level_names = ["tp_hit"]
    else:
        level_names = list(_TP_ORDER[:len(targets)])

    for candle in candles:
        if candle.open_time < created_ms:
            continue
        stamp = _candle_closed_at(candle)
        if is_long:
            if candle.low <= stop:
                events.append(("sl_hit", stamp))
                break
            for target, name in zip(targets, level_names):
                if name in already or any(e[0] == name for e in events):
                    continue
                if candle.high >= target:
                    events.append((name, stamp))
        else:
            if candle.high >= stop:
                events.append(("sl_hit", stamp))
                break
            for target, name in zip(targets, level_names):
                if name in already or any(e[0] == name for e in events):
                    continue
                if candle.low <= target:
                    events.append((name, stamp))
    return events


def check_outcome(signal_row: dict, candles: list) -> tuple[str, str] | None:
    """Backward-compatible: first new event only (used by older tests)."""
    events = check_outcome_events(signal_row, candles)
    return events[0] if events else None


def track_open_signals(cfg, prefetched=None, session=None) -> list:
    """Advance every open/partially-hit signal; return (row, latest_status) pairs."""
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

    def candles_covering(symbol, timeframe, created_ms):
        pre = prefetched.get((symbol, timeframe))
        if pre and pre[0].open_time <= created_ms:
            return pre
        key = (symbol, timeframe, created_ms)
        if key not in fetch_cache:
            try:
                fetch_cache[key] = fetch_candles(
                    symbol, timeframe, HISTORY_LIMIT,
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
        timeframe = row.get("timeframe") or "1h"
        session_cfg = _SESSION_BY_TIMEFRAME.get(timeframe)
        max_open_days = (session_cfg.max_open_days if session_cfg
                         else _DEFAULT_MAX_OPEN_DAYS)
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + timedelta(days=max_open_days)
        candles = candles_covering(symbol, timeframe, created_ms)
        if candles is None:
            continue
        expiry_ms = expires_at.timestamp() * 1000
        window = [c for c in candles if c.open_time < expiry_ms]
        events = check_outcome_events(row, window)
        if not events and now >= expires_at:
            events = [("expired", now.isoformat())]
        if not events:
            continue

        latest = None
        for outcome, closed_at in events:
            terminal = outcome in _TERMINAL
            try:
                update_signal_outcome(
                    row["id"], outcome, closed_at,
                    cfg.supabase_url, cfg.supabase_service_key,
                    terminal=terminal, session=session,
                )
            except Exception as exc:
                print(f"[{symbol}] failed to mark {outcome} "
                      f"({type(exc).__name__}), will retry next run")
                break
            print(f"[{symbol}] {outcome.upper().replace('_', ' ')} — "
                  f"{row['direction']} from {row['entry']}")
            latest = outcome
            row = {**row, "status": outcome}
            if (outcome in ("tp1_hit", "tp2_hit", "tp3_hit", "tp_hit", "sl_hit")
                    and cfg.telegram_bot_token and cfg.telegram_channel_id):
                try:
                    send_outcome_alert(row, outcome, cfg.telegram_bot_token,
                                       cfg.telegram_channel_id)
                    print(f"[{symbol}] Telegram outcome alert sent ({outcome})")
                except Exception as exc:
                    print(f"[{symbol}] Telegram outcome alert failed "
                          f"({type(exc).__name__}: {exc}), continuing")
        if latest is not None:
            closed.append((row, latest))
    return closed
