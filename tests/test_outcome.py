from datetime import datetime, timedelta, timezone

import pytest

from signals.models import Candle
from signals.outcome_tracker import check_outcome
from signals.storage import close_signal, list_open_signals
from signals.telegram_client import format_outcome_alert

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def _row(direction="long", entry=100.0, stop=95.0, target=110.0,
         created=NOW):
    return {
        "id": "sig-1",
        "symbol": "BTCUSDT",
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "created_at": created.isoformat(),
    }


def _candle(hours_after=1, high=105.0, low=99.0):
    open_time = int((NOW + timedelta(hours=hours_after)).timestamp() * 1000)
    return Candle(open_time=open_time, open=100.0, high=high, low=low,
                  close=100.0, volume=1.0)


def test_long_tp_hit():
    assert check_outcome(_row(), [_candle(high=111.0)]) == "tp_hit"


def test_long_sl_hit():
    assert check_outcome(_row(), [_candle(low=94.0)]) == "sl_hit"


def test_short_tp_hit():
    row = _row(direction="short", stop=105.0, target=90.0)
    assert check_outcome(row, [_candle(high=100.0, low=89.0)]) == "tp_hit"


def test_short_sl_hit():
    row = _row(direction="short", stop=105.0, target=90.0)
    assert check_outcome(row, [_candle(high=106.0)]) == "sl_hit"


def test_still_open_when_neither_level_reached():
    assert check_outcome(_row(), [_candle(high=105.0, low=99.0)]) is None


def test_candle_spanning_both_levels_counts_as_stop():
    assert check_outcome(_row(), [_candle(high=111.0, low=94.0)]) == "sl_hit"


def test_candles_before_creation_are_ignored():
    old_candle = _candle(hours_after=-2, high=120.0, low=90.0)
    assert check_outcome(_row(), [old_candle]) is None


def test_first_hit_wins_across_candles():
    candles = [_candle(hours_after=1, high=111.0), _candle(hours_after=2, low=94.0)]
    assert check_outcome(_row(), candles) == "tp_hit"


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self._status = status
        self.last_method = None
        self.last_url = None
        self.last_json = None

    def get(self, url, headers=None, timeout=None):
        self.last_method, self.last_url = "GET", url
        return FakeResponse(self._status, self._payload)

    def patch(self, url, headers=None, json=None, timeout=None):
        self.last_method, self.last_url, self.last_json = "PATCH", url, json
        return FakeResponse(self._status)


def test_list_open_signals_queries_open_only():
    session = FakeSession(payload=[_row()])
    rows = list_open_signals("https://abc.supabase.co", "key", session=session)
    assert rows == [_row()]
    assert "status=eq.open" in session.last_url


def test_close_signal_patches_status_and_closed_at():
    session = FakeSession()
    close_signal("sig-1", "tp_hit", "2026-07-07T13:00:00+00:00",
                 "https://abc.supabase.co", "key", session=session)
    assert session.last_method == "PATCH"
    assert "id=eq.sig-1" in session.last_url
    assert session.last_json == {
        "status": "tp_hit",
        "closed_at": "2026-07-07T13:00:00+00:00",
    }


def test_close_signal_raises_on_http_error():
    with pytest.raises(RuntimeError):
        close_signal("sig-1", "sl_hit", "t", "https://abc.supabase.co", "key",
                     session=FakeSession(status=500))


def test_format_outcome_alert_long_tp():
    text = format_outcome_alert(_row(), "tp_hit")
    assert "TP HIT BTCUSDT" in text
    assert "LONG +10.00%" in text
    assert "Entry 100 → 110" in text


def test_format_outcome_alert_short_sl_is_negative():
    row = _row(direction="short", stop=105.0, target=90.0)
    text = format_outcome_alert(row, "sl_hit")
    assert "SL HIT BTCUSDT" in text
    assert "SHORT -5.00%" in text
