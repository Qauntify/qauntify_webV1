"""Single-row engine_lock table: claim/release the cross-process run lock."""
from urllib.parse import quote

import requests

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
