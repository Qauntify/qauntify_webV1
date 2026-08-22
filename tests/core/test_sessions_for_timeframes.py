"""Tests for TRADING_SESSION resolution helpers."""
from signals.models import TRADING_SESSIONS, sessions_for_timeframes


def test_sessions_for_timeframes_single():
    due = sessions_for_timeframes(["5m"])
    assert len(due) == 1
    assert due[0].name == "super_scalp"
    assert due[0].timeframe == "5m"


def test_sessions_for_timeframes_multiple_preserve_order():
    due = sessions_for_timeframes(["1h", "5m", "15m"])
    assert [s.timeframe for s in due] == ["5m", "15m", "1h"]


def test_sessions_for_timeframes_ignores_unknown():
    assert sessions_for_timeframes(["5m", "bogus"]) == sessions_for_timeframes(["5m"])


def test_sessions_for_timeframes_empty_when_all_unknown():
    assert sessions_for_timeframes(["4h", "bbma"]) == ()


def test_sessions_for_timeframes_dedupes():
    due = sessions_for_timeframes(["5m", "5m"])
    assert len(due) == 1
    assert due[0].timeframe == "5m"


def test_all_trading_sessions_have_unique_timeframes():
    tfs = [s.timeframe for s in TRADING_SESSIONS]
    assert len(tfs) == len(set(tfs))
