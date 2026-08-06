"""Bar-close scheduling for the live scanner."""
from datetime import datetime, timezone

from signals.bar_close import (
    closed_bar_open_ms,
    just_closed,
    sessions_due,
)
from signals.models import TRADING_SESSIONS


def test_closed_bar_open_ms_aligns_to_prior_bucket():
    # 2026-08-06 12:07:30 UTC → prior 5m bar opened 12:00
    now = datetime(2026, 8, 6, 12, 7, 30, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    open_ms = closed_bar_open_ms(now_ms, "5m")
    assert datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc) == datetime(
        2026, 8, 6, 12, 0, tzinfo=timezone.utc,
    )


def test_just_closed_true_early_in_new_bar():
    now = datetime(2026, 8, 6, 12, 0, 20, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    assert just_closed(now_ms, "5m", window_ms=45_000) is True


def test_just_closed_false_mid_bar():
    now = datetime(2026, 8, 6, 12, 2, 30, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    assert just_closed(now_ms, "5m", window_ms=45_000) is False


def test_sessions_due_fires_once_per_bar():
    now = datetime(2026, 8, 6, 13, 0, 10, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    last_fired: dict[str, int] = {}
    due = sessions_due(now_ms, TRADING_SESSIONS, last_fired)
    names = {s.name for s in due}
    # 13:00 is a 5m, 15m, and 1h boundary
    assert "super_scalp" in names
    assert "scalp" in names
    assert "swing" in names
    # Second call in the same window must not re-fire
    due2 = sessions_due(now_ms, TRADING_SESSIONS, last_fired)
    assert due2 == []
