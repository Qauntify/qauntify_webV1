"""Tests for free ForexFactory-style economic calendar client."""
from datetime import datetime, timezone

from signals.calendar_client import (
    calendar_block_for_symbol,
    fetch_calendar_events,
    filter_events_for_symbol,
)


SAMPLE_EVENTS = [
    {
        "title": "CPI m/m",
        "country": "USD",
        "date": "2026-07-14T08:30:00-04:00",
        "impact": "High",
        "forecast": "0.2%",
        "previous": "0.1%",
    },
    {
        "title": "BoE Bank Rate",
        "country": "GBP",
        "date": "2026-07-14T07:00:00-04:00",
        "impact": "High",
        "forecast": "5.25%",
        "previous": "5.25%",
    },
    {
        "title": "BusinessNZ Services Index",
        "country": "NZD",
        "date": "2026-07-14T18:30:00-04:00",
        "impact": "Low",
        "forecast": "",
        "previous": "47.5",
    },
    {
        "title": "Building Permits",
        "country": "USD",
        "date": "2026-07-20T08:30:00-04:00",
        "impact": "Medium",
        "forecast": "1.4M",
        "previous": "1.5M",
    },
]


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload=None, error=None):
        self._payload = payload if payload is not None else SAMPLE_EVENTS
        self._error = error
        self.calls = 0

    def get(self, url, timeout=10, headers=None):
        self.calls += 1
        if self._error:
            raise self._error
        return _FakeResponse(self._payload)


def test_fetch_calendar_events_parses_iso_times():
    session = _FakeSession()
    events = fetch_calendar_events(session=session)
    assert len(events) == 4
    by_title = {e["title"]: e for e in events}
    assert by_title["CPI m/m"]["impact"] == "High"
    assert by_title["CPI m/m"]["currency"] == "USD"
    assert by_title["CPI m/m"]["when"].tzinfo is not None
    assert events == sorted(events, key=lambda e: e["when"])


def test_fetch_calendar_events_raises_on_failure():
    session = _FakeSession(error=RuntimeError("down"))
    try:
        fetch_calendar_events(session=session)
        assert False, "expected raise"
    except RuntimeError:
        pass


def test_filter_btc_keeps_usd_high_near_now():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    events = fetch_calendar_events(session=_FakeSession())
    filtered = filter_events_for_symbol(events, "BTCUSDT", now=now)
    titles = [e["title"] for e in filtered]
    assert "CPI m/m" in titles
    assert "BoE Bank Rate" not in titles
    assert "BusinessNZ Services Index" not in titles
    # Far-future Medium USD outside window is dropped.
    assert "Building Permits" not in titles


def test_filter_gbp_includes_gbp_and_usd():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    events = fetch_calendar_events(session=_FakeSession())
    filtered = filter_events_for_symbol(events, "GBPUSDT", now=now)
    titles = [e["title"] for e in filtered]
    assert "CPI m/m" in titles
    assert "BoE Bank Rate" in titles


def test_calendar_block_formats_events():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    events = fetch_calendar_events(session=_FakeSession())
    block = calendar_block_for_symbol(events, "BTCUSDT", now=now)
    assert "CPI m/m" in block
    assert "High" in block
    assert "USD" in block


def test_calendar_block_empty_when_none_relevant():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    events = fetch_calendar_events(session=_FakeSession(
        payload=[{
            "title": "Holiday",
            "country": "JPY",
            "date": "2026-07-10T00:00:00-04:00",
            "impact": "Holiday",
            "forecast": "",
            "previous": "",
        }],
    ))
    block = calendar_block_for_symbol(events, "BTCUSDT", now=now)
    assert "No nearby high/medium-impact" in block
