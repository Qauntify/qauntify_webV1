from signals.healthcheck import (
    SessionHealth,
    check_session_health,
    format_healthcheck_alert,
)
from signals.models import TradingSession


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Maps timeframe -> rows to return, keyed by substring in the URL."""

    def __init__(self, rows_by_timeframe: dict):
        self._rows = rows_by_timeframe
        self.urls = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        for timeframe, rows in self._rows.items():
            if f"timeframe=eq.{timeframe}" in url:
                return FakeResponse(rows)
        return FakeResponse([])


SESSIONS = (
    TradingSession(name="super_scalp", timeframe="5m", max_open_days=1),
    TradingSession(name="scalp", timeframe="15m", max_open_days=2),
    TradingSession(name="swing", timeframe="1h", max_open_days=14),
)


def test_check_session_health_all_healthy():
    session = FakeSession({
        "5m": [{"created_at": "2026-08-05T12:00:00+00:00"}],
        "15m": [{"created_at": "2026-08-05T12:00:00+00:00"}],
        "1h": [{"created_at": "2026-08-05T12:00:00+00:00"}],
    })
    results = check_session_health(
        "https://abc.supabase.co", "service-key",
        sessions=SESSIONS, session=session,
    )
    assert len(results) == 3
    assert all(not r.silent for r in results)
    assert format_healthcheck_alert(results) is None


def test_check_session_health_flags_silent_session():
    session = FakeSession({
        "5m": [{"created_at": "2026-08-05T12:00:00+00:00"}],
        "15m": [],  # no events in the lookback window
        "1h": [{"created_at": "2026-08-05T12:00:00+00:00"}],
    })
    results = check_session_health(
        "https://abc.supabase.co", "service-key",
        sessions=SESSIONS, session=session,
    )
    silent = [r for r in results if r.silent]
    assert len(silent) == 1
    assert silent[0] == SessionHealth(session="scalp", timeframe="15m", last_event_at=None)


def test_check_session_health_dedupes_shared_timeframes():
    """Two sessions on the same timeframe must only be queried once."""
    sessions = SESSIONS + (
        TradingSession(name="scalp_dup", timeframe="15m", max_open_days=1),
    )
    session = FakeSession({
        "5m": [{"created_at": "2026-08-05T12:00:00+00:00"}],
        "15m": [{"created_at": "2026-08-05T12:00:00+00:00"}],
        "1h": [{"created_at": "2026-08-05T12:00:00+00:00"}],
    })
    check_session_health(
        "https://abc.supabase.co", "service-key",
        sessions=sessions, session=session,
    )
    assert len(session.urls) == 3


def test_format_healthcheck_alert_lists_every_silent_session():
    results = [
        SessionHealth(session="scalp", timeframe="15m", last_event_at=None),
        SessionHealth(session="swing", timeframe="1h",
                      last_event_at="2026-08-05T12:00:00+00:00"),
    ]
    text = format_healthcheck_alert(results, lookback_hours=3)
    assert text is not None
    assert "scalp" in text
    assert "15m" in text
    assert "swing" not in text
    assert "3h" in text


def test_format_healthcheck_alert_none_when_all_healthy():
    results = [
        SessionHealth(session="swing", timeframe="1h",
                      last_event_at="2026-08-05T12:00:00+00:00"),
    ]
    assert format_healthcheck_alert(results) is None
