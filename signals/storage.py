"""Persists signals + AI scan events to Supabase (PostgREST insert)."""
from dataclasses import asdict
from urllib.parse import quote

import requests

from signals.models import BotSettings, DEFAULT_SIGNAL_STRATEGY, SIGNAL_STRATEGIES, Signal


def save_signal(signal: Signal, supabase_url: str, service_key: str,
                session=None) -> None:
    """Insert one signal row; raises on any failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"{supabase_url}/rest/v1/signals",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=asdict(signal),
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


def list_open_signals(supabase_url: str, service_key: str, session=None):
    """All signals with status 'open' (oldest first) as raw dicts.
    Paginates past PostgREST default row caps. Raises on any failure —
    including the status column not existing yet."""
    session = session or requests.Session()
    page_size = 1000
    offset = 0
    rows: list = []
    while True:
        response = session.get(
            f"{supabase_url}/rest/v1/signals"
            "?status=eq.open"
            "&select=id,symbol,timeframe,direction,entry,stop_loss,take_profit,created_at"
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


def open_symbols_for_timeframe(symbols, timeframe: str, supabase_url: str,
                               service_key: str, session=None) -> set:
    """Symbols in `symbols` that already have an open signal on `timeframe`.
    Raises on any failure so callers can fail closed."""
    if not symbols:
        return set()
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?status=eq.open&timeframe=eq.{timeframe}"
        f"&symbol=in.({symbols_filter})&select=symbol",
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
    """Mark one signal tp_hit/sl_hit; raises on failure so callers can retry."""
    session = session or requests.Session()
    response = session.patch(
        f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"status": status, "closed_at": closed_at},
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
        f"?symbol=eq.{symbol}{timeframe_filter}&select=direction,created_at"
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
        f"&created_at=gte.{quote(since, safe='')}"
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


def list_closed_signals(supabase_url: str, service_key: str, session=None):
    """Every signal that has reached a terminal status (tp_hit/sl_hit/
    expired), for calibration reporting — win rate and expectancy can only
    be computed once an outcome is known. Raises on any failure."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=in.(tp_hit,sl_hit,expired)"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "confidence,status,indicators,created_at,closed_at"
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
            "?id=eq.1&select=symbols,min_alert_confidence,signal_strategy",
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
            s.upper() for s in row["symbols"]
            if isinstance(s, str) and s.strip()
        )
        confidence = int(row["min_alert_confidence"])
        strategy = row.get("signal_strategy", DEFAULT_SIGNAL_STRATEGY)
        if strategy not in SIGNAL_STRATEGIES:
            strategy = DEFAULT_SIGNAL_STRATEGY
        if not symbols or not 0 <= confidence <= 100:
            raise ValueError("empty symbols or confidence out of range")
        return BotSettings(
            symbols=symbols,
            min_alert_confidence=confidence,
            signal_strategy=strategy,
        )
    except Exception as exc:
        print(f"bot_settings unavailable ({type(exc).__name__}), using defaults")
        return BotSettings()
