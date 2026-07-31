"""Which sessions may scan which symbols.

GBPUSD is swing-only: retail FX spread is a large fraction of a 5m or 15m stop
and a small fraction of a 1h one, so the fast sessions cannot pay for
themselves on it.
"""
from signals.models import SESSION_SYMBOLS, TRADING_SESSIONS, session_scans

SESSION_NAMES = tuple(s.name for s in TRADING_SESSIONS)


def test_gbpusd_is_scanned_by_the_swing_session():
    assert session_scans("swing", "GBPUSD") is True


def test_gbpusd_is_not_scanned_by_the_fast_sessions():
    assert session_scans("scalp", "GBPUSD") is False
    assert session_scans("super_scalp", "GBPUSD") is False


def test_unrestricted_symbols_are_scanned_by_every_session():
    for name in SESSION_NAMES:
        assert session_scans(name, "BTCUSD") is True
        assert session_scans(name, "ETHUSD") is True
        assert session_scans(name, "XAUUSD") is True


def test_legacy_usdt_symbols_follow_the_same_rule():
    """Stored rows and older settings use the USDT form. Keying on the raw
    string would let GBPUSDT slip past the restriction."""
    assert session_scans("swing", "GBPUSDT") is True
    assert session_scans("scalp", "GBPUSDT") is False


def test_symbol_matching_is_case_and_whitespace_insensitive():
    assert session_scans("scalp", " gbpusd ") is False


def test_every_restricted_session_name_actually_exists():
    """A typo in SESSION_SYMBOLS would silently scan the symbol nowhere."""
    for symbol, allowed in SESSION_SYMBOLS.items():
        assert allowed, f"{symbol} is allowed on no session at all"
        for name in allowed:
            assert name in SESSION_NAMES, f"{symbol} -> unknown session {name!r}"
