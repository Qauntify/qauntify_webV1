"""Bulk deletion of aged rows for unbounded log-style tables."""
from datetime import datetime, timezone

import requests


def delete_rows_older_than(table: str, date_column: str, days: int,
                           supabase_url: str, service_key: str, *,
                           session=None, now: datetime | None = None) -> None:
    """DELETEs rows in `table` where `date_column` is older than `days` days.

    For unbounded log-style tables (ai_events, engine_runs, xau_scan_runs)
    with no natural cap on growth. Raises on any failure so the caller can
    log/skip — never partially-applied since it's a single DELETE statement.
    """
    session = session or requests.Session()
    from datetime import timedelta
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = session.delete(
        f"{supabase_url}/rest/v1/{table}?{date_column}=lt.{cutoff}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
