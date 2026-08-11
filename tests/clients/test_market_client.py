import pytest

from signals.clients.market import (
    canonical_symbol,
    fetch_candles,
    is_gold_symbol,
    kraken_pair,
)


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
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.last_url = None
        self.last_params = None

    def get(self, url, params=None, timeout=None, headers=None):
        self.last_url = url
        self.last_params = params
        return FakeResponse(self._payload, self._status)


OHLC_PAYLOAD = {
    "error": [],
    "result": {
        "XXBTZUSD": [
            [1720000000, "100.0", "102.0", "99.0", "101.0", "100.5", "1500.5", 10],
            [1720003600, "101.0", "103.0", "100.5", "102.5", "101.5", "1200.0", 8],
        ],
        "last": 1720003600,
    },
}

def test_canonical_symbol_renames_usdt_and_paxg_to_xau():
    assert canonical_symbol("btcusdt") == "BTCUSD"
    assert canonical_symbol("ETHUSD") == "ETHUSD"
    assert canonical_symbol("PAXGUSD") == "XAUUSD"
    assert canonical_symbol("PAXGUSDT") == "XAUUSD"
    assert canonical_symbol("XAUUSD") == "XAUUSD"


def test_kraken_pair_maps_usd_and_legacy_usdt():
    assert kraken_pair("BTCUSD") == "XBTUSD"
    assert kraken_pair("BTCUSDT") == "XBTUSD"
    assert kraken_pair("GBPUSD") == "GBPUSD"


def test_is_gold_symbol():
    assert is_gold_symbol("XAUUSD")
    assert is_gold_symbol("PAXGUSD")
    assert not is_gold_symbol("BTCUSD")


def test_fetch_candles_parses_kraken_ohlc():
    session = FakeSession(OHLC_PAYLOAD)
    candles = fetch_candles("BTCUSD", session=session)
    assert len(candles) == 2
    first = candles[0]
    assert first.open_time == 1720000000 * 1000
    assert first.open == 100.0
    assert first.high == 102.0
    assert first.low == 99.0
    assert first.close == 101.0
    assert first.volume == 1500.5


def test_fetch_candles_sends_kraken_params():
    session = FakeSession(OHLC_PAYLOAD)
    fetch_candles("ETHUSD", interval="1h", limit=200, session=session)
    assert session.last_url == "https://api.kraken.com/0/public/OHLC"
    assert session.last_params["pair"] == "ETHUSD"
    assert session.last_params["interval"] == 60
    assert "since" not in session.last_params


def test_fetch_candles_maps_legacy_usdt_symbol():
    session = FakeSession(OHLC_PAYLOAD)
    fetch_candles("BTCUSDT", interval="5m", session=session)
    assert session.last_params["pair"] == "XBTUSD"
    assert session.last_params["interval"] == 5


def test_fetch_candles_sends_since_when_start_time_given():
    session = FakeSession(OHLC_PAYLOAD)
    fetch_candles(
        "BTCUSD", interval="1h", limit=1000,
        start_time=1720000000000, session=session,
    )
    assert session.last_params["since"] == 1720000000 - 3600


def test_fetch_candles_filters_by_start_time():
    session = FakeSession(OHLC_PAYLOAD)
    candles = fetch_candles(
        "BTCUSD", start_time=1720003600 * 1000, session=session,
    )
    assert len(candles) == 1
    assert candles[0].open_time == 1720003600 * 1000


def test_fetch_xauusd_uses_kraken_paxg():
    session = FakeSession(OHLC_PAYLOAD)
    candles = fetch_candles("XAUUSD", interval="1h", session=session)
    assert session.last_url == "https://api.kraken.com/0/public/OHLC"
    assert session.last_params["pair"] == "PAXGUSD"
    assert session.last_params["interval"] == 60
    assert len(candles) == 2
    assert candles[-1].close == 102.5


def test_fetch_legacy_paxg_routes_to_kraken_paxg():
    session = FakeSession(OHLC_PAYLOAD)
    candles = fetch_candles("PAXGUSD", interval="5m", session=session)
    assert session.last_params["pair"] == "PAXGUSD"
    assert session.last_params["interval"] == 5
    assert candles[0].open == 100.0


def test_fetch_xauusd_1m_uses_kraken_1m_interval():
    session = FakeSession(OHLC_PAYLOAD)
    fetch_candles("XAUUSD", interval="1m", session=session)
    assert session.last_params["pair"] == "PAXGUSD"
    assert session.last_params["interval"] == 1


def test_fetch_xauusd_1m_refuses_paxg_when_mt5_cold(monkeypatch):
    session = FakeSession(OHLC_PAYLOAD)

    def _empty(*_a, **_k):
        return []

    monkeypatch.setattr(
        "signals.persistence.mt5.fetch_mt5_candles", _empty,
    )
    with pytest.raises(RuntimeError, match="refusing PAXG"):
        fetch_candles(
            "XAUUSD",
            interval="1m",
            session=session,
            supabase_url="https://example.supabase.co",
            service_key="service-key",
        )
    # Without Supabase creds, Kraken PAXG still works (offline / legacy).
    candles = fetch_candles("XAUUSD", interval="1m", session=session)
    assert session.last_params["pair"] == "PAXGUSD"
    assert len(candles) == 2


def _fresh_mt5_1m_rows(n: int, *, close: float = 2650.0):
    """n closed M1 rows ending one minute ago (usable / fresh)."""
    from datetime import datetime, timezone

    now = int(datetime.now(timezone.utc).timestamp())
    end = now - (now % 60) - 60
    rows = []
    for i in range(n):
        t = end - (n - 1 - i) * 60
        rows.append({
            "open_time": t,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close + (i % 3) * 0.1,
            "volume": 1.0,
        })
    return rows


def test_fetch_xauusd_5m_resamples_mt5_1m_when_warm(monkeypatch):
    """Gold 5m/15m/1h structure must come from broker M1, not PAXG."""
    session = FakeSession(OHLC_PAYLOAD)
    rows = _fresh_mt5_1m_rows(600)  # → 120 five-minute bars

    monkeypatch.setattr(
        "signals.persistence.mt5.fetch_mt5_candles",
        lambda *a, **k: rows,
    )
    candles = fetch_candles(
        "XAUUSD",
        interval="5m",
        limit=50,
        session=session,
        supabase_url="https://example.supabase.co",
        service_key="service-key",
    )
    # Synthetic forming bar appended; closed history is MT5-resampled.
    assert len(candles) == 51
    assert session.last_url is None or "kraken" not in (session.last_url or "")
    # 5m bucket width
    assert candles[1].open_time - candles[0].open_time == 5 * 60_000


def test_fetch_xauusd_5m_falls_back_to_paxg_when_mt5_shallow(monkeypatch):
    session = FakeSession(OHLC_PAYLOAD)
    monkeypatch.setattr(
        "signals.persistence.mt5.fetch_mt5_candles",
        lambda *a, **k: _fresh_mt5_1m_rows(80),  # only ~16 five-minute bars
    )
    # Warm-but-shallow must refuse PAXG mix (structure vs broker entry).
    with pytest.raises(RuntimeError, match="refusing PAXG"):
        fetch_candles(
            "XAUUSD",
            interval="5m",
            limit=50,
            session=session,
            supabase_url="https://example.supabase.co",
            service_key="service-key",
        )


def test_fetch_candles_raises_on_http_error():
    session = FakeSession({}, status=500)
    with pytest.raises(RuntimeError):
        fetch_candles("BTCUSD", session=session)


def test_fetch_candles_raises_on_kraken_error_payload():
    session = FakeSession({"error": ["EQuery:Unknown asset pair"], "result": {}})
    with pytest.raises(RuntimeError, match="Unknown asset pair"):
        fetch_candles("BTCUSD", session=session)


def test_gold_4h_uses_kraken_native_240m_bucket():
    session = FakeSession(OHLC_PAYLOAD)
    fetch_candles("XAUUSD", "4h", 100, session=session)
    assert session.last_params["pair"] == "PAXGUSD"
    assert session.last_params["interval"] == 240


def test_gold_1h_uses_kraken_hourly():
    session = FakeSession(OHLC_PAYLOAD)
    candles = fetch_candles("XAUUSD", "1h", 100, session=session)
    assert session.last_params["interval"] == 60
    assert len(candles) == 2


def test_parse_kraken_last_price():
    from signals.clients.market import _parse_kraken_last_price

    price = _parse_kraken_last_price(
        {"error": [], "result": {"PAXGUSD": {"c": ["4115.45", "0.1"]}}},
        "PAXGUSD",
    )
    assert price == 4115.45


def test_gold_entry_live_ok_within_cap():
    from signals.clients.market import gold_entry_live_ok

    ok, msg = gold_entry_live_ok(4115.0, 4116.0, "1m", atr=2.0)
    assert ok and msg == ""


def test_gold_entry_live_ok_rejects_stale():
    from signals.clients.market import gold_entry_live_ok

    ok, msg = gold_entry_live_ok(4154.0, 4115.0, "1m", atr=2.0)
    assert not ok
    assert "stale" in msg.lower() or "refusing" in msg.lower()


def test_gold_5m_allows_paxg_mt5_basis_drift():
    """PAXG fallback vs MT5 mid can sit ~10pt apart — still publishable."""
    from signals.clients.market import gold_entry_live_ok, max_gold_entry_drift

    assert max_gold_entry_drift("5m", atr=3.0) >= 15.0
    ok, msg = gold_entry_live_ok(4250.07, 4259.80, "5m", atr=3.0)
    assert ok and msg == ""


def test_setup_stop_risk_ok_rejects_tight_stop():
    from signals.clients.market import setup_stop_risk_ok, stop_risk_fraction

    entry = 4100.0
    stop = entry * (1 - 0.0005)
    assert stop_risk_fraction(entry, stop) < 0.00097
    ok, msg = setup_stop_risk_ok(entry, stop)
    assert not ok
    assert "tight stop" in msg.lower()


def test_setup_stop_risk_ok_accepts_wide_enough_stop():
    from signals.clients.market import setup_stop_risk_ok

    entry = 4100.0
    stop = entry * (1 - 0.002)
    ok, msg = setup_stop_risk_ok(entry, stop)
    assert ok and msg == ""
