"""Which sessions may scan which symbols.

GBPUSD is retired: never scanned on any session, even if still listed in
bot_settings. Historical rows stay in the DB.
"""
from signals.models import (
    RETIRED_SYMBOLS,
    SESSION_SYMBOLS,
    TRADING_SESSIONS,
    session_scans,
)

SESSION_NAMES = tuple(s.name for s in TRADING_SESSIONS)


def test_gbpusd_is_retired_from_every_session():
    for name in SESSION_NAMES:
        assert session_scans(name, "GBPUSD") is False
        assert session_scans(name, "GBPUSDT") is False
        assert session_scans(name, " gbpusd ") is False


def test_retired_set_includes_gbp():
    assert "GBPUSD" in RETIRED_SYMBOLS


def test_live_symbols_are_scanned_by_every_session():
    for name in SESSION_NAMES:
        assert session_scans(name, "BTCUSD") is True
        assert session_scans(name, "ETHUSD") is True
        assert session_scans(name, "XAUUSD") is True


def test_every_restricted_session_name_actually_exists():
    """A typo in SESSION_SYMBOLS would silently scan the symbol nowhere."""
    for symbol, allowed in SESSION_SYMBOLS.items():
        assert allowed, f"{symbol} is allowed on no session at all"
        for name in allowed:
            assert name in SESSION_NAMES, f"{symbol} -> unknown session {name!r}"
