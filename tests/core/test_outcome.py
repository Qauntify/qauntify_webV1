from datetime import datetime, timedelta, timezone

import pytest

from signals import outcome_tracker
from signals.config import Config
from signals.models import Candle
from signals.outcome_tracker import check_outcome, track_open_signals
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
    outcome, closed_at = check_outcome(_row(), [_candle(high=111.0)])
    assert outcome == "tp_hit"
    assert closed_at.startswith("2026-07-07T13:00:00")


def test_long_sl_hit():
    outcome, _ = check_outcome(_row(), [_candle(low=94.0)])
    assert outcome == "sl_hit"


def test_short_tp_hit():
    row = _row(direction="short", stop=105.0, target=90.0)
    outcome, _ = check_outcome(row, [_candle(high=100.0, low=89.0)])
    assert outcome == "tp_hit"


def test_short_sl_hit():
    row = _row(direction="short", stop=105.0, target=90.0)
    outcome, _ = check_outcome(row, [_candle(high=106.0)])
    assert outcome == "sl_hit"


def test_still_open_when_neither_level_reached():
    assert check_outcome(_row(), [_candle(high=105.0, low=99.0)]) is None


def test_candle_spanning_both_levels_counts_as_stop():
    outcome, _ = check_outcome(_row(), [_candle(high=111.0, low=94.0)])
    assert outcome == "sl_hit"


def test_candles_before_creation_are_ignored():
    old_candle = _candle(hours_after=-2, high=120.0, low=90.0)
    assert check_outcome(_row(), [old_candle]) is None


def test_first_hit_wins_across_candles():
    candles = [_candle(hours_after=1, high=111.0), _candle(hours_after=2, low=94.0)]
    outcome, closed_at = check_outcome(_row(), candles)
    assert outcome == "tp_hit"
    assert "T13:00:00" in closed_at


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
    assert "status=in.(open,tp1_hit,tp2_hit)" in session.last_url


def test_close_signal_patches_status_and_closed_at():
    session = FakeSession()
    close_signal("sig-1", "tp_hit", "2026-07-07T13:00:00+00:00",
                 "https://abc.supabase.co", "key", session=session)
    assert session.last_method == "PATCH"
    assert "id=eq.sig-1" in session.last_url
    assert session.last_json == {
        "status": "tp_hit",
        "tp3_hit_at": "2026-07-07T13:00:00+00:00",
        "closed_at": "2026-07-07T13:00:00+00:00",
    }


def test_close_signal_raises_on_http_error():
    with pytest.raises(RuntimeError):
        close_signal("sig-1", "sl_hit", "t", "https://abc.supabase.co", "key",
                     session=FakeSession(status=500))


def _config(telegram=False):
    return Config(
        sealion_api_key="sk-test",
        supabase_url="https://abc.supabase.co",
        supabase_service_key="service-key",
        telegram_bot_token="bot-token" if telegram else "",
        telegram_channel_id="chat-id" if telegram else "",
    )


def _live_row(days_old, **overrides):
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    row = {
        "id": f"sig-{days_old}d",
        "symbol": "BTCUSDT",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "created_at": created.isoformat(),
    }
    row.update(overrides)
    return row


def _candles_from(start_dt, hours, high=105.0, low=99.0):
    return [
        Candle(
            open_time=int((start_dt + timedelta(hours=i)).timestamp() * 1000),
            open=100.0, high=high, low=low, close=100.0, volume=1.0,
        )
        for i in range(hours)
    ]


def _track(monkeypatch, rows, cfg=None, prefetched=None,
           fetched_candles=None):
    """Run track_open_signals with storage/telegram/binance stubbed out.
    Returns (closed_pairs, recorded_fetches, recorded_closes, alerts)."""
    fetches, closes, alerts = [], [], []

    monkeypatch.setattr(outcome_tracker, "list_open_signals",
                        lambda url, key, session=None: rows)

    def fake_fetch(symbol, interval, limit, start_time=None, session=None):
        fetches.append({"symbol": symbol, "limit": limit,
                        "start_time": start_time})
        return fetched_candles if fetched_candles is not None else []

    monkeypatch.setattr(outcome_tracker, "fetch_candles", fake_fetch)
    monkeypatch.setattr(
        outcome_tracker, "update_signal_outcome",
        lambda sig_id, status, closed_at, url, key, session=None, terminal=True:
        closes.append((sig_id, status)))
    monkeypatch.setattr(
        outcome_tracker, "send_outcome_alert",
        lambda row, outcome, token, chat_id: alerts.append((row, outcome)))

    closed = track_open_signals(cfg or _config(), prefetched=prefetched)
    return closed, fetches, closes, alerts


def test_track_fetches_history_from_signal_creation(monkeypatch):
    # A 9-day-old signal is past the trailing 201-candle window: candles must
    # be fetched forward from created_at, not from a recent trailing window.
    row = _live_row(days_old=9)
    created_ms = datetime.fromisoformat(row["created_at"]).timestamp() * 1000
    hit_candles = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=9), hours=48, high=111.0)

    closed, fetches, closes, _ = _track(
        monkeypatch, [row], fetched_candles=hit_candles)

    assert len(fetches) == 1
    assert fetches[0]["start_time"] == int(created_ms)
    assert closes == [("sig-9d", "tp_hit")]
    assert [(r["id"], o) for r, o in closed] == [("sig-9d", "tp_hit")]


def test_track_uses_prefetched_candles_that_cover_creation(monkeypatch):
    row = _live_row(days_old=1)
    covering = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=2), hours=48, high=111.0)

    closed, fetches, closes, _ = _track(
        monkeypatch, [row], prefetched={("BTCUSDT", "1h"): covering})

    assert fetches == []  # no refetch: scan candles already cover the signal
    assert closes == [(row["id"], "tp_hit")]


def test_track_refetches_when_prefetched_starts_too_late(monkeypatch):
    row = _live_row(days_old=9)
    too_short = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=2), hours=48, high=111.0)
    full = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=9), hours=48, high=111.0)

    closed, fetches, closes, _ = _track(
        monkeypatch, [row], prefetched={("BTCUSDT", "1h"): too_short},
        fetched_candles=full)

    assert len(fetches) == 1  # prefetch misses the signal's early life
    assert closes == [(row["id"], "tp_hit")]


def test_track_expires_signal_open_beyond_max_days(monkeypatch):
    row = _live_row(days_old=20)
    quiet = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=20), hours=48)

    closed, fetches, closes, alerts = _track(
        monkeypatch, [row], cfg=_config(telegram=True),
        fetched_candles=quiet)

    assert closes == [(row["id"], "expired")]
    assert [(r["id"], o) for r, o in closed] == [(row["id"], "expired")]
    assert alerts == []  # expiry is bookkeeping, not a tradeable outcome


def test_track_prefers_real_outcome_over_expiry(monkeypatch):
    # TP was hit on day 2; the signal is now 20 days old. The recorded
    # outcome must be the hit, not the expiry.
    row = _live_row(days_old=20)
    hit_early = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=20), hours=48, high=111.0)

    closed, _, closes, alerts = _track(
        monkeypatch, [row], cfg=_config(telegram=True),
        fetched_candles=hit_early)

    assert closes == [(row["id"], "tp_hit")]
    assert len(alerts) == 1
    assert alerts[0][0]["id"] == row["id"]
    assert alerts[0][1] == "tp_hit"


def test_track_ignores_hits_after_expiry_window(monkeypatch):
    # The only TP-crossing candle is 16 days after creation — outside the
    # 14-day window, so the signal expires instead of counting a stale win.
    row = _live_row(days_old=20)
    created = datetime.now(timezone.utc) - timedelta(days=20)
    late_hit = (_candles_from(created, hours=24)
                + _candles_from(created + timedelta(days=16), hours=24,
                                high=111.0))

    closed, _, closes, _ = _track(monkeypatch, [row],
                                  fetched_candles=late_hit)

    assert closes == [(row["id"], "expired")]


def test_format_outcome_alert_long_tp():
    text = format_outcome_alert(_row(), "tp_hit")
    assert "TAKE PROFIT" in text
    assert "<b>BTCUSDT</b>" in text
    assert "LONG" in text
    assert "+10.00%" in text
    assert "Entry  <code>100</code>  →  <code>110</code>" in text


def test_format_outcome_alert_short_sl_is_negative():
    row = _row(direction="short", stop=105.0, target=90.0)
    text = format_outcome_alert(row, "sl_hit")
    assert "STOP LOSS" in text
    assert "<b>BTCUSDT</b>" in text
    assert "SHORT" in text
    assert "-5.00%" in text


def test_track_fetches_candles_in_the_rows_own_timeframe(monkeypatch):
    row = _live_row(days_old=1, timeframe="15m", id="scalp-1")
    intervals = []

    monkeypatch.setattr(outcome_tracker, "list_open_signals",
                        lambda url, key, session=None: [row])

    def fake_fetch(symbol, interval, limit, start_time=None, session=None):
        intervals.append(interval)
        return _candles_from(
            datetime.now(timezone.utc) - timedelta(days=1), hours=24,
            high=111.0)

    monkeypatch.setattr(outcome_tracker, "fetch_candles", fake_fetch)
    closes = []
    monkeypatch.setattr(
        outcome_tracker, "update_signal_outcome",
        lambda sig_id, status, closed_at, url, key, session=None, terminal=True:
        closes.append((sig_id, status)))

    track_open_signals(_config())

    assert intervals == ["15m"]
    assert closes == [("scalp-1", "tp_hit")]


def test_track_prefetch_key_includes_timeframe(monkeypatch):
    # 1h candles must never settle a 15m signal: the prefetch for
    # ("BTCUSDT", "1h") does not apply to a 15m row.
    row = _live_row(days_old=1, timeframe="15m")
    covering = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=2), hours=48, high=111.0)

    closed, fetches, closes, _ = _track(
        monkeypatch, [row],
        prefetched={("BTCUSDT", "1h"): covering},
        fetched_candles=covering)

    assert len(fetches) == 1  # wrong-timeframe prefetch ignored, refetched

    closed, fetches, closes, _ = _track(
        monkeypatch, [row],
        prefetched={("BTCUSDT", "15m"): covering})

    assert fetches == []  # right-timeframe prefetch is used


def test_track_scalp_signals_expire_faster_than_swing(monkeypatch):
    quiet = _candles_from(
        datetime.now(timezone.utc) - timedelta(days=4), hours=48)

    scalp = _live_row(days_old=3, timeframe="15m", id="scalp-old")
    closed, _, closes, _ = _track(monkeypatch, [scalp],
                                  fetched_candles=quiet)
    assert closes == [("scalp-old", "expired")]

    swing = _live_row(days_old=3, timeframe="1h", id="swing-young")
    closed, _, closes, _ = _track(monkeypatch, [swing],
                                  fetched_candles=quiet)
    assert closes == []  # 3 days is nothing on the 1h session


def test_cloned_tp_levels_collapse_to_single_target():
    from signals.outcome_tracker import _targets
    row = {
        "take_profit": 110.0,
        "take_profit_1": 110.0,
        "take_profit_2": 110.0,
        "take_profit_3": 110.0,
    }
    assert _targets(row) == [110.0]


def test_distinct_tp_ladder_kept():
    from signals.outcome_tracker import _targets
    row = {
        "take_profit": 102.0,
        "take_profit_1": 102.0,
        "take_profit_2": 104.0,
        "take_profit_3": 106.0,
    }
    assert _targets(row) == [102.0, 104.0, 106.0]
