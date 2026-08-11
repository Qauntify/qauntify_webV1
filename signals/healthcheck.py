"""Detects trading sessions that have gone silent in ai_events.

A healthy session logs a no_setup/reject/confirm ai_event on nearly every
scan — most scans find nothing, but that still gets recorded (see
signals/pipeline/scan.py's no-setup path). Zero events across a multi-hour
window is a strong signal that scans are silently crashing before they reach
storage, not that the strategy is simply quiet.

This is exactly the failure mode that let the 15m cloud_mss session sit at
zero signals for five days (2026-07-31 to 2026-08-05): composer.py crashed
on every single scan with KeyError('ema9'), the crash was swallowed by a
broad except in scan.py, and nothing was left behind to notice — no error,
no ai_events row, nothing. This module exists so that goes unnoticed for
minutes, not days.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from signals.models import TRADING_SESSIONS, TradingSession

DEFAULT_LOOKBACK_HOURS = 3


@dataclass(frozen=True)
class SessionHealth:
    session: str
    timeframe: str
    # ISO timestamp of the most recent ai_event in the lookback window, or
    # None if the session logged nothing at all.
    last_event_at: str | None

    @property
    def silent(self) -> bool:
        return self.last_event_at is None


def check_session_health(supabase_url: str, service_key: str,
                         sessions: tuple[TradingSession, ...] = TRADING_SESSIONS,
                         lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
                         session=None) -> list[SessionHealth]:
    """One result per distinct timeframe among `sessions`.

    Two sessions never share a timeframe today, but the dedup keeps this
    correct (and the alert non-duplicated) if that ever changes.
    """
    http = session or requests.Session()
    since = (
        datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    ).isoformat()
    results = []
    seen = {}
    for sess in sessions:
        if sess.timeframe in seen:
            continue
        response = http.get(
            f"{supabase_url}/rest/v1/ai_events"
            f"?select=created_at&timeframe=eq.{sess.timeframe}"
            f"&created_at=gte.{quote(since, safe='')}"
            "&order=created_at.desc&limit=1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()
        health = SessionHealth(
            session=sess.name,
            timeframe=sess.timeframe,
            last_event_at=rows[0]["created_at"] if rows else None,
        )
        seen[sess.timeframe] = health
        results.append(health)
    return results


def format_healthcheck_alert(results: list[SessionHealth],
                             lookback_hours: int = DEFAULT_LOOKBACK_HOURS
                             ) -> str | None:
    """Telegram HTML message, or None when every session is healthy (caller
    should send nothing in that case — this check is silent when passing)."""
    silent = [r for r in results if r.silent]
    if not silent:
        return None
    lines = [
        "⚠️ <b>SESSION HEALTHCHECK</b>",
        "",
        f"No ai_events (no_setup/reject/confirm) in the last {lookback_hours}h for:",
    ]
    for r in silent:
        lines.append(f"• <b>{r.session}</b> ({r.timeframe})")
    lines.append("")
    lines.append(
        "A session logging zero events usually means every scan is "
        "crashing before it reaches storage — check the engine.yml run logs."
    )
    return "\n".join(lines)
