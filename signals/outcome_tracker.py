"""Checks open signals against fresh candles and closes TP/SL hits.

Signals are never deleted. Multi-TP ladder:
  open → tp1_hit → tp2_hit → tp3_hit (terminal win)
  sl_hit / expired can end the trade from any non-terminal state.
Telegram fires once per newly crossed level.
"""
from datetime import datetime, timedelta, timezone

from signals.chart.outcome_pipeline import attach_outcome_chart
from signals.market_client import fetch_candles
from signals.models import ALL_SESSIONS, OPEN_POLL_STATUSES, TIMEFRAME_MINUTES
from signals.storage import list_open_signals, update_signal_outcome, set_outcome_chart_url
from signals.telegram_client import send_outcome_alert

# Keyed off ALL_SESSIONS, not TRADING_SESSIONS: this tracker settles every open
# row, including those written by workflows the main scan loop never runs.
_SESSION_BY_TIMEFRAME = {s.timeframe: s for s in ALL_SESSIONS}
_DEFAULT_MAX_OPEN = next(
    s.max_open for s in ALL_SESSIONS if s.timeframe == "1h")
HISTORY_LIMIT = 1000

_TP_ORDER = ("tp1_hit", "tp2_hit", "tp3_hit")
# Terminal outcomes. tp1_hit / tp2_hit are also terminal when closed_at is set
# (TP banked, later stop — we freeze the highest level reached as the win).
_TERMINAL = frozenset({"tp3_hit", "sl_hit", "expired", "tp_hit"})


def _candle_closed_at(candle) -> str:
    return datetime.fromtimestamp(
        candle.open_time / 1000, tz=timezone.utc,
    ).isoformat()


def _stop_to_partial_win(already: set[str], events: list[tuple[str, str]]) -> str | None:
    """If a stop arrives after banking TP1+, freeze the highest banked level.

    Returns the win status to store instead of sl_hit, or None for a pure stop.
    """
    hit = set(already)
    for name, _ in events:
        if name in _TP_ORDER or name == "tp_hit":
            hit.add(name if name != "tp_hit" else "tp1_hit")
    if "tp2_hit" in hit or "tp3_hit" in hit:
        return "tp2_hit"
    if "tp1_hit" in hit:
        return "tp1_hit"
    return None


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


def fills_intrabar(signal_row: dict) -> bool:
    """Whether this signal's entry was a resting order filled INSIDE a bar.

    Market entries (every detector except sr_limit) are taken at the close of
    their signal bar, so that bar is already history when the trade starts. A
    limit entry fills partway through its bar, and the rest of that bar's range
    — including a stop sitting just beyond the level — is part of the trade.
    """
    indicators = signal_row.get("indicators") or {}
    return indicators.get("entry_style") == "limit"


def _scan_start(candles: list, created_ms: float, include_entry_bar: bool,
                bar_ms: int | None) -> int:
    """Index of the first candle belonging to the trade's life.

    For a limit fill this is the bar the order filled on: the newest bar that
    had already CLOSED when the row was written, which is exactly the bar the
    detector built the setup from. Identified by its own close time rather than
    by stepping back one index from created_at — the engine writes the row an
    arbitrary number of minutes into the following bar, so neither index
    arithmetic nor subtracting one bar's duration lands reliably.
    """
    first = next((i for i, c in enumerate(candles)
                  if c.open_time >= created_ms), len(candles))
    if not include_entry_bar or bar_ms is None:
        return first
    entry_bar = max(
        (i for i, c in enumerate(candles) if c.open_time + bar_ms <= created_ms),
        default=None,
    )
    return first if entry_bar is None else entry_bar


def check_outcome_events(signal_row: dict, candles: list, *,
                         include_entry_bar: bool = False,
                         bar_ms: int | None = None) -> list[tuple[str, str]]:
    """Ordered new events for this run: (status, closed_at_iso).

    Stop wins on a same-candle tie with any TP. A fast move can cross
    multiple unhit TPs in one candle — all are returned in order. That tie rule
    is what makes including the entry bar safe for limit fills: a bar that
    spans both the fill and the stop scores as a stop.
    """
    created_ms = datetime.fromisoformat(signal_row["created_at"]).timestamp() * 1000
    start = _scan_start(candles, created_ms, include_entry_bar, bar_ms)
    candles = candles[start:]
    is_long = signal_row["direction"] == "long"
    stop = float(signal_row["stop_loss"])
    entry = float(signal_row["entry"])
    targets = _targets(signal_row)
    already = _already_hit(signal_row)
    events: list[tuple[str, str]] = []

    # Map target index → status name. Legacy single target closes as tp_hit
    # (and tp3_hit alias) for stats compatibility.
    if len(targets) == 1:
        level_names = ["tp_hit"]
    else:
        level_names = list(_TP_ORDER[:len(targets)])

    # Once any target is banked the stop trails to entry, matching
    # r_model.scaled_r and backtest.simulate_scaled. Settling a partially-
    # banked trade against the ORIGINAL stop while scoring it at breakeven is
    # the hybrid that overstated every strategy here by ~0.24R per trade.
    # The status stays "sl_hit" — with tp*_hit_at set, scaled_r already reads
    # that as "booked slices kept, remainder out flat", so no schema changes.
    final_name = level_names[-1]

    def _closed_out():
        """True once the LAST target is banked — the position is flat."""
        return final_name in already or any(e[0] == final_name for e in events)

    def _active_stop():
        """Original stop until a target banks, entry thereafter.

        Only partial fills trail: with the final target hit there is no
        remainder left to protect, which `_closed_out` handles by ending the
        scan.
        """
        banked = bool(already & set(_TP_ORDER)) or any(
            event[0] in _TP_ORDER or event[0] == "tp_hit" for event in events)
        return entry if banked else stop

    if _closed_out():
        return events

    for candle in candles:
        stamp = _candle_closed_at(candle)
        if is_long:
            if candle.low <= _active_stop():
                events.append(("sl_hit", stamp))
                break
            for target, name in zip(targets, level_names):
                if name in already or any(e[0] == name for e in events):
                    continue
                if candle.high >= target:
                    events.append((name, stamp))
            if _closed_out():
                break
        else:
            if candle.high >= _active_stop():
                events.append(("sl_hit", stamp))
                break
            for target, name in zip(targets, level_names):
                if name in already or any(e[0] == name for e in events):
                    continue
                if candle.low <= target:
                    events.append((name, stamp))
            if _closed_out():
                break
    return events


def check_outcome(signal_row: dict, candles: list) -> tuple[str, str] | None:
    """Backward-compatible: first new event only (used by older tests)."""
    events = check_outcome_events(signal_row, candles)
    return events[0] if events else None


def apply_events(row: dict, events: list[tuple[str, str]], window: list,
                 cfg, session=None) -> tuple[dict, str | None]:
    """Apply each new event to `row` in order: claim it (race-safe against
    any other writer advancing the same row concurrently — the slow cron and
    the realtime watcher both call this), attach an outcome chart on the
    terminal event, and alert Telegram. Returns the updated row and the
    latest status actually applied (None if nothing was claimed).

    Stops applying further events the moment a claim is lost — a row another
    writer already moved out from under us is not safe to keep advancing
    locally, and an event that was never actually persisted must never alert.
    """
    symbol = row["symbol"]
    latest = None
    applied: list[tuple[str, str]] = []
    for outcome, closed_at in events:
        freeze_only = False
        prior_status = row.get("status") or "open"
        if outcome == "sl_hit":
            locked = _stop_to_partial_win(_already_hit(row), applied)
            if locked is not None:
                # Banked TP1+ then stopped: freeze as a TP1/TP2 win.
                outcome = locked
                terminal = True
                freeze_only = True
            else:
                terminal = True
        else:
            terminal = outcome in _TERMINAL
        try:
            claimed = update_signal_outcome(
                row["id"], outcome, closed_at,
                cfg.supabase_url, cfg.supabase_service_key,
                terminal=terminal, expected_status=prior_status,
                session=session,
            )
        except Exception as exc:
            print(f"[{symbol}] failed to mark {outcome} "
                  f"({type(exc).__name__}), will retry next run")
            break
        if claimed is False:
            print(f"[{symbol}] {outcome} already applied by another writer, "
                  "stopping here")
            break
        print(f"[{symbol}] {outcome.upper().replace('_', ' ')} — "
              f"{row['direction']} from {row['entry']}")
        latest = outcome
        row = {**row, "status": outcome}
        if terminal:
            row = {**row, "closed_at": closed_at}
        if terminal and outcome != "expired":
            chart_url = attach_outcome_chart(
                row, outcome, window,
                supabase_url=cfg.supabase_url,
                service_key=cfg.supabase_service_key,
                session=session,
            )
            if chart_url:
                row = {**row, "outcome_chart_url": chart_url}
                try:
                    set_outcome_chart_url(
                        row["id"], chart_url, cfg.supabase_url,
                        cfg.supabase_service_key, session=session,
                    )
                except Exception as exc:
                    print(f"[{symbol}] failed to store outcome_chart_url "
                          f"({type(exc).__name__}), continuing")
        if (not freeze_only
                and outcome in ("tp1_hit", "tp2_hit", "tp3_hit", "tp_hit",
                                "sl_hit")
                and cfg.telegram_bot_token and cfg.telegram_channel_id):
            try:
                send_outcome_alert(row, outcome, cfg.telegram_bot_token,
                                   cfg.telegram_channel_id)
                print(f"[{symbol}] Telegram outcome alert sent ({outcome})")
            except Exception as exc:
                print(f"[{symbol}] Telegram outcome alert failed "
                      f"({type(exc).__name__}: {exc}), continuing")
        applied.append((outcome, closed_at))
    return row, latest


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

    def candles_covering(symbol, timeframe, from_ms):
        pre = prefetched.get((symbol, timeframe))
        if pre and pre[0].open_time <= from_ms:
            return pre
        key = (symbol, timeframe, from_ms)
        if key not in fetch_cache:
            try:
                fetch_cache[key] = fetch_candles(
                    symbol, timeframe, HISTORY_LIMIT,
                    start_time=int(from_ms), session=session,
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
        max_open = session_cfg.max_open if session_cfg else _DEFAULT_MAX_OPEN
        created = datetime.fromisoformat(row["created_at"])
        created_ms = created.timestamp() * 1000
        expires_at = created + max_open
        # A limit fill needs its own entry bar in the window. Reach back two
        # bars rather than one so the fetch lands before that bar's open
        # whatever the delay between bar close and row write; _scan_start then
        # trims to the exact bar by position.
        include_entry_bar = fills_intrabar(row)
        bar_ms = TIMEFRAME_MINUTES.get(timeframe, 60) * 60_000
        from_ms = created_ms - 2 * bar_ms if include_entry_bar else created_ms
        candles = candles_covering(symbol, timeframe, from_ms)
        if candles is None:
            continue
        expiry_ms = expires_at.timestamp() * 1000
        window = [c for c in candles if c.open_time < expiry_ms]
        events = check_outcome_events(row, window,
                                      include_entry_bar=include_entry_bar,
                                      bar_ms=bar_ms)
        if not events and now >= expires_at:
            events = [("expired", now.isoformat())]
        if not events:
            continue

        row, latest = apply_events(row, events, window, cfg, session=session)
        if latest is not None:
            closed.append((row, latest))
    return closed
