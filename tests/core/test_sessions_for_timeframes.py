"""Tests for TRADING_SESSION resolution helpers."""
from signals.models import TRADING_SESSIONS, sessions_for_timeframes


def test_sessions_for_timeframes_single():
    due = sessions_for_timeframes(["15m"])
    assert len(due) == 1
    assert due[0].name == "scalp"
    assert due[0].timeframe == "15m"


def test_sessions_for_timeframes_multiple_preserve_order():
    due = sessions_for_timeframes(["1h", "15m"])
    assert [s.timeframe for s in due] == ["15m", "1h"]


def test_sessions_for_timeframes_ignores_unknown():
    assert sessions_for_timeframes(["15m", "bogus"]) == sessions_for_timeframes(["15m"])


def test_sessions_for_timeframes_empty_when_all_unknown():
    assert sessions_for_timeframes(["4h", "bbma"]) == ()


def test_sessions_for_timeframes_excludes_paused_super_scalp():
    """super_scalp (5m) was pulled to AUXILIARY_SESSIONS -- see
    docs/ict-fvg-backtest-results.md -- so "5m" resolves to nothing until a
    replacement strategy is designed and it's re-added to TRADING_SESSIONS."""
    assert sessions_for_timeframes(["5m"]) == ()


def test_sessions_for_timeframes_dedupes():
    due = sessions_for_timeframes(["15m", "15m"])
    assert len(due) == 1
    assert due[0].timeframe == "15m"


def test_all_trading_sessions_have_unique_timeframes():
    tfs = [s.timeframe for s in TRADING_SESSIONS]
    assert len(tfs) == len(set(tfs))
