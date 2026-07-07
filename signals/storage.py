"""Persists signals + AI scan events to Supabase (PostgREST insert)."""
from dataclasses import asdict

import requests

from signals.models import BotSettings, Signal


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
    Raises on any failure — including the status column not existing yet."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?status=eq.open"
        "&select=id,symbol,direction,entry,stop_loss,take_profit,created_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


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
                  session=None):
    """Newest stored signal for `symbol` as {"direction", "created_at"},
    or None when the symbol has no signals. Raises on any failure."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{symbol}&select=direction,created_at"
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
            "?id=eq.1&select=symbols,min_alert_confidence",
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
        if not symbols or not 0 <= confidence <= 100:
            raise ValueError("empty symbols or confidence out of range")
        return BotSettings(symbols=symbols, min_alert_confidence=confidence)
    except Exception as exc:
        print(f"bot_settings unavailable ({type(exc).__name__}), using defaults")
        return BotSettings()
