import pytest

from signals.market_client import (
    canonical_symbol,
    fetch_candles,
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

    def get(self, url, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        return FakeResponse(self._payload, self._status)


# Kraken OHLC row: time, open, high, low, close, vwap, volume, count
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


def test_canonical_symbol_renames_usdt_to_usd():
    assert canonical_symbol("btcusdt") == "BTCUSD"
    assert canonical_symbol("ETHUSD") == "ETHUSD"


def test_kraken_pair_maps_usd_and_legacy_usdt():
    assert kraken_pair("BTCUSD") == "XBTUSD"
    assert kraken_pair("BTCUSDT") == "XBTUSD"
    assert kraken_pair("PAXGUSD") == "PAXGUSD"
    assert kraken_pair("GBPUSD") == "GBPUSD"


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


def test_fetch_candles_raises_on_http_error():
    session = FakeSession({}, status=500)
    with pytest.raises(RuntimeError):
        fetch_candles("BTCUSD", session=session)


def test_fetch_candles_raises_on_kraken_error_payload():
    session = FakeSession({"error": ["EQuery:Unknown asset pair"], "result": {}})
    with pytest.raises(RuntimeError, match="Unknown asset pair"):
        fetch_candles("BTCUSD", session=session)
