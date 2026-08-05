"""Persists signals + AI scan events to Supabase (PostgREST insert)."""
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from signals.models import (
    ADMIN_SELECTABLE_STRATEGIES,
    BotSettings,
    DEFAULT_SIGNAL_STRATEGY,
    Signal,
)
from signals.market_client import canonical_symbol


def save_signal(signal: Signal, supabase_url: str, service_key: str,
                session=None, *, shadow: bool = False,
                experiment: str | None = None) -> None:
    """Insert one signal row; raises on any failure so the caller can retry.

    `shadow=True` means "record but never deliver" — it is the containment
    flag every user-facing read path filters on. `experiment` names WHICH study
    the row belongs to ("gate_ab", "sr_limit"), so unrelated trials are never
    pooled together in analysis. Ordinary delivered signals leave both unset.
    """
    session = session or requests.Session()
    payload = asdict(signal)
    # Mirror TP1 into take_profit_1 for the multi-TP schema while keeping
    # legacy `take_profit` populated for older readers.
    payload["take_profit_1"] = signal.take_profit
    payload["shadow"] = shadow
    payload["experiment"] = experiment
    response = session.post(
        f"{supabase_url}/rest/v1/signals",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()


def save_debate(debate: dict, supabase_url: str, service_key: str,
                session=None) -> None:
    """Insert one AI War Room debate row; raises on failure so the caller can
    decide (the hook treats it best-effort)."""
    session = session or requests.Session()
    payload = {
        "id": str(uuid.uuid4()),
        "signal_id": debate.get("signal_id"),
        "symbol": debate["symbol"],
        "timeframe": debate["timeframe"],
        "direction": debate["direction"],
        "transcript": debate["transcript"],
        "manager_verdict": debate["manager_verdict"],
        "manager_confidence": debate["manager_confidence"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    response = session.post(
        f"{supabase_url}/rest/v1/agent_debates",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()


def save_ai_event(event: dict, supabase_url: str, service_key: str,
                  session=None) -> None:
    """Insert one ai_events row; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"{supabase_url}/rest/v1/ai_events",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=event,
        timeout=15,
    )
    response.raise_for_status()


def save_engine_run(run: dict, supabase_url: str, service_key: str,
                    session=None) -> None:
    """Insert one engine_runs row; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"{supabase_url}/rest/v1/engine_runs",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=run,
        timeout=15,
    )
    response.raise_for_status()


def save_xau_scan_run(run: dict, supabase_url: str, service_key: str,
                      session=None) -> None:
    """Insert one xau_scan_runs row; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"{supabase_url}/rest/v1/xau_scan_runs",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=run,
        timeout=15,
    )
    response.raise_for_status()


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


ENGINE_LOCK_STALE_MINUTES = 12


def try_acquire_engine_lock(
    holder: str,
    supabase_url: str,
    service_key: str,
    *,
    stale_minutes: int = ENGINE_LOCK_STALE_MINUTES,
    session=None,
) -> bool:
    """Claim the single engine_lock row. Returns False if another live run holds it.

    Soft-fails open (returns True) when the lock table is missing so a missing
    migration never permanently stops scans.
    """
    from datetime import datetime, timedelta, timezone

    session = session or requests.Session()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=stale_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        response = session.patch(
            f"{supabase_url}/rest/v1/engine_lock"
            f"?id=eq.1&or=(holder.is.null,acquired_at.lt.{cutoff})",
            headers=headers,
            json={"holder": holder, "acquired_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
            timeout=15,
        )
        if response.status_code == 404:
            print("engine_lock unavailable (missing table?), continuing without lock")
            return True
        response.raise_for_status()
        rows = response.json()
        return bool(rows)
    except Exception as exc:
        print(f"engine_lock acquire failed ({type(exc).__name__}), continuing without lock")
        return True


def release_engine_lock(
    holder: str,
    supabase_url: str,
    service_key: str,
    session=None,
) -> None:
    """Clear the lock if we still own it. Never raises."""
    session = session or requests.Session()
    try:
        response = session.patch(
            f"{supabase_url}/rest/v1/engine_lock"
            f"?id=eq.1&holder=eq.{quote(holder)}",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"holder": None, "acquired_at": None},
            timeout=15,
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
    except Exception as exc:
        print(f"engine_lock release failed ({type(exc).__name__}), continuing")


def list_open_signals(supabase_url: str, service_key: str, session=None):
    """Signals still needing outcome polling (open / tp1 / tp2), oldest first."""
    session = session or requests.Session()
    page_size = 1000
    offset = 0
    rows: list = []
    while True:
        response = session.get(
            f"{supabase_url}/rest/v1/signals"
            "?status=in.(open,tp1_hit,tp2_hit)"
            "&closed_at=is.null"
            # `indicators` carries entry_style, which decides whether the
            # outcome tracker counts the bar the order filled on.
            "&select=id,symbol,timeframe,direction,entry,stop_loss,"
            "take_profit,take_profit_1,take_profit_2,take_profit_3,"
            "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,chart_data,"
            "indicators"
            "&order=created_at.asc",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Range": f"{offset}-{offset + page_size - 1}",
                "Prefer": "count=exact",
            },
            timeout=15,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def list_signals_missing_outcome_chart(supabase_url: str, service_key: str,
                                       limit: int = 20, session=None):
    """Closed rows with no outcome_chart_url yet, most recently closed first.

    Backfill target for realtime-closed rows (e.g. via the MT5/Vercel path,
    which never renders a chart) and for any row whose chart attach failed
    at close time in the normal cron path.
    """
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?closed_at=not.is.null"
        "&outcome_chart_url=is.null"
        "&select=id,symbol,timeframe,direction,entry,stop_loss,"
        "take_profit,take_profit_1,take_profit_2,take_profit_3,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,closed_at"
        f"&order=closed_at.desc&limit={limit}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def open_symbols_for_timeframe(symbols, timeframe: str, supabase_url: str,
                               service_key: str, session=None) -> set:
    """Symbols that already have a non-terminal signal on `timeframe`."""
    if not symbols:
        return set()
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?status=in.(open,tp1_hit,tp2_hit)&closed_at=is.null"
        f"&timeframe=eq.{timeframe}"
        f"&symbol=in.({symbols_filter})&shadow=is.false&select=symbol",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return {row["symbol"] for row in response.json()}


def close_signal(signal_id: str, status: str, closed_at: str,
                 supabase_url: str, service_key: str, session=None) -> None:
    """Mark one signal terminal (tp_hit/tp3_hit/sl_hit/expired)."""
    update_signal_outcome(
        signal_id, status, closed_at, supabase_url, service_key,
        terminal=True, session=session,
    )


def update_signal_outcome(signal_id: str, status: str, at: str,
                          supabase_url: str, service_key: str, *,
                          terminal: bool, expected_status: str | None = None,
                          session=None) -> bool | None:
    """PATCH status (+ optional tpN_hit_at / closed_at).

    tp1_hit / tp2_hit can be intermediate (still open) or terminal (TP banked
    then froze with closed_at). Only stamp the first-hit timestamp when the
    trade is still advancing — a terminal freeze must not overwrite it.

    `expected_status` makes the PATCH a conditional claim (mirrors
    try_acquire_engine_lock's conditional-PATCH pattern): it only applies if
    the row is still in that status, so two writers racing on the same row
    (the slow cron and the realtime watcher) can't both "win" and double-fire
    Telegram. Returns True/False (claimed or not) when given, else None
    (existing unconditional behavior, unchanged).
    """
    session = session or requests.Session()
    payload: dict = {"status": status}
    if status == "tp1_hit" and not terminal:
        payload["tp1_hit_at"] = at
    elif status == "tp2_hit" and not terminal:
        payload["tp2_hit_at"] = at
    elif status in ("tp3_hit", "tp_hit"):
        payload["tp3_hit_at"] = at
        # Legacy tp_hit also stamps closed_at.
        terminal = True
    if terminal:
        payload["closed_at"] = at

    url = f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}"
    prefer = "return=minimal"
    if expected_status is not None:
        url += f"&status=eq.{expected_status}"
        prefer = "return=representation"

    response = session.patch(
        url,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    if expected_status is not None:
        return bool(response.json())
    return None


def set_outcome_chart_url(signal_id: str, url: str, supabase_url: str,
                          service_key: str, session=None) -> None:
    """PATCH just the outcome_chart_url on one signal row."""
    session = session or requests.Session()
    response = session.patch(
        f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"outcome_chart_url": url},
        timeout=15,
    )
    response.raise_for_status()


def latest_signal(symbol: str, supabase_url: str, service_key: str,
                  timeframe: str | None = None, session=None):
    """Newest stored signal for `symbol` as {"direction", "created_at"},
    or None when the symbol has no signals. `timeframe` scopes the lookup
    to one session's stream so scalp and swing never dedup each other.
    Raises on any failure."""
    session = session or requests.Session()
    timeframe_filter = f"&timeframe=eq.{timeframe}" if timeframe else ""
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{symbol}{timeframe_filter}&shadow=is.false"
        "&select=direction,created_at"
        "&order=created_at.desc&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def latest_ai_event_time(symbol: str, timeframe: str, supabase_url: str,
                         service_key: str, session=None) -> str | None:
    """created_at of the newest ai_events row for `symbol`+`timeframe` (every
    scan outcome — confirm, reject, no_setup — logs one), or None when this
    session has never evaluated the symbol. Raises on any failure."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/ai_events"
        f"?symbol=eq.{symbol}&timeframe=eq.{timeframe}&select=created_at"
        "&order=created_at.desc&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0]["created_at"] if rows else None


def latest_ai_event_times_since(symbols, timeframe: str, since: str,
                                supabase_url: str, service_key: str,
                                session=None) -> dict:
    """created_at of the newest ai_events row for each symbol in `symbols`
    at `timeframe`, restricted to rows at/after `since` (an ISO timestamp) —
    the only rows a throttle check ever needs. One query replaces what
    would otherwise be one `latest_ai_event_time` call per symbol. Symbols
    with no qualifying row are simply absent from the result (same meaning
    as `latest_ai_event_time` returning None). Raises on any failure."""
    if not symbols:
        return {}
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/ai_events"
        f"?symbol=in.({symbols_filter})&timeframe=eq.{timeframe}"
        f"&created_at=gte.{quote(since, safe='')}"
        "&select=symbol,created_at&order=symbol.asc,created_at.desc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    latest: dict = {}
    for row in response.json():
        # Rows arrive sorted newest-first within each symbol group, so the
        # first occurrence of a symbol is already its latest timestamp.
        latest.setdefault(row["symbol"], row["created_at"])
    return latest


def latest_signals_since(symbols, timeframe: str, since: str,
                         supabase_url: str, service_key: str,
                         session=None) -> dict:
    """{"direction", "created_at"} of the newest signal for each symbol in
    `symbols` at `timeframe`, restricted to rows at/after `since` — the
    only rows a dedup check ever needs. One query replaces what would
    otherwise be one `latest_signal` call per symbol. Symbols with no
    qualifying row are absent from the result. Raises on any failure."""
    if not symbols:
        return {}
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=in.({symbols_filter})&timeframe=eq.{timeframe}"
        f"&created_at=gte.{quote(since, safe='')}&shadow=is.false"
        "&select=symbol,direction,created_at&order=symbol.asc,created_at.desc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    latest: dict = {}
    for row in response.json():
        latest.setdefault(row["symbol"], row)
    return latest


def list_closed_signals(supabase_url: str, service_key: str, session=None,
                        *, include_shadow: bool = False):
    """Every signal that has reached a terminal status (tp_hit/sl_hit/
    expired), for calibration reporting — win rate and expectancy can only
    be computed once an outcome is known. Raises on any failure.

    Shadow rows (LLM-rejected setups recorded for the gate A/B) are excluded by
    default, so existing calibration reporting is unaffected by them. The gate
    report passes `include_shadow=True` because it needs both arms.
    """
    session = session or requests.Session()
    shadow_filter = "" if include_shadow else "&shadow=is.false"
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?or=(status.in.(tp_hit,tp3_hit,sl_hit,expired),"
        "and(status.in.(tp1_hit,tp2_hit),closed_at.not.is.null))"
        f"{shadow_filter}"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "take_profit_1,take_profit_2,take_profit_3,confidence,indicators,"
        "status,created_at,closed_at,shadow,experiment,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_bot_settings(supabase_url: str, service_key: str,
                       session=None) -> BotSettings:
    """Read the single bot_settings row; fall back to defaults on any failure.

    Settings must never break a scan, so every error path (network, missing
    table, malformed row) returns BotSettings() and logs one short line.
    """
    session = session or requests.Session()
    try:
        response = session.get(
            f"{supabase_url}/rest/v1/bot_settings"
            "?id=eq.1&select=symbols,min_alert_confidence,min_store_confidence,signal_strategy",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()
        row = rows[0]
        symbols = tuple(
            canonical_symbol(s)
            for s in row["symbols"]
            if isinstance(s, str) and s.strip()
        )
        alert_confidence = int(row["min_alert_confidence"])
        store_raw = row.get("min_store_confidence", 0)
        store_confidence = int(store_raw if store_raw is not None else 0)
        strategy = row.get("signal_strategy", DEFAULT_SIGNAL_STRATEGY)
        if strategy not in ADMIN_SELECTABLE_STRATEGIES:
            strategy = DEFAULT_SIGNAL_STRATEGY
        if not symbols or not 0 <= alert_confidence <= 100:
            raise ValueError("empty symbols or confidence out of range")
        if not 0 <= store_confidence <= 100:
            store_confidence = 0
        return BotSettings(
            symbols=symbols,
            min_alert_confidence=alert_confidence,
            min_store_confidence=store_confidence,
            signal_strategy=strategy,
        )
    except Exception as exc:
        print(f"bot_settings unavailable ({type(exc).__name__}), using defaults")
        return BotSettings()
