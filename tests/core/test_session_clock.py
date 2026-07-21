"""Tests for Asia / London / New York session labeling."""
from datetime import datetime, timezone

from signals.session_clock import describe_market_session, sessions_at


def test_asia_only_window():
    # 03:00 UTC — Tokyo open, London/NY closed
    now = datetime(2026, 7, 14, 3, 0, tzinfo=timezone.utc)
    assert sessions_at(now) == ("Asia",)


def test_asia_london_overlap():
    now = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)
    assert sessions_at(now) == ("Asia", "London")


def test_london_new_york_overlap():
    now = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
    assert sessions_at(now) == ("London", "New York")


def test_new_york_only_window():
    now = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
    assert sessions_at(now) == ("New York",)


def test_describe_includes_overlap_label():
    now = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
    text = describe_market_session(now)
    assert "London" in text
    assert "New York" in text
    assert "overlap" in text.lower()


def test_describe_single_session():
    now = datetime(2026, 7, 14, 3, 0, tzinfo=timezone.utc)
    text = describe_market_session(now)
    assert "Asia" in text
    assert "03:00 UTC" in text
