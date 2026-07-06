"""Persists confirmed signals to Supabase (PostgREST insert)."""
from dataclasses import asdict

import requests

from signals.models import Signal


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
