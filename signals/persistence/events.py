"""Event/run log tables: AI debates, ai_events, engine_runs, xau_scan_runs."""
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests


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
