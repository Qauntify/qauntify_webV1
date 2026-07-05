import pytest

from signals.binance_client import fetch_candles


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


KLINE_ROWS = [
    [1720000000000, "100.0", "102.0", "99.0", "101.0", "1500.5",
     1720003599999, "0", 0, "0", "0", "0"],
    [1720003600000, "101.0", "103.0", "100.5", "102.5", "1200.0",
     1720007199999, "0", 0, "0", "0", "0"],
]


def test_fetch_candles_parses_klines():
    session = FakeSession(KLINE_ROWS)
    candles = fetch_candles("BTCUSDT", session=session)
    assert len(candles) == 2
    first = candles[0]
    assert first.open_time == 1720000000000
    assert first.open == 100.0
    assert first.high == 102.0
    assert first.low == 99.0
    assert first.close == 101.0
    assert first.volume == 1500.5


def test_fetch_candles_sends_correct_params():
    session = FakeSession(KLINE_ROWS)
    fetch_candles("ETHUSDT", interval="1h", limit=200, session=session)
    assert session.last_url == "https://api.binance.com/api/v3/klines"
    assert session.last_params == {"symbol": "ETHUSDT", "interval": "1h", "limit": 200}


def test_fetch_candles_raises_on_http_error():
    session = FakeSession([], status=500)
    with pytest.raises(RuntimeError):
        fetch_candles("BTCUSDT", session=session)
