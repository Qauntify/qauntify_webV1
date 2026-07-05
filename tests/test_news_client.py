from signals.news_client import fetch_headlines


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
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        return FakeResponse(self._payload, self._status)


def test_fetch_headlines_returns_titles():
    payload = {"results": [
        {"title": "Bitcoin breaks resistance"},
        {"title": "ETF inflows surge"},
        {"title": None},
        {"no_title_key": True},
    ]}
    session = FakeSession(payload)
    headlines = fetch_headlines("BTCUSDT", api_key="cp-key", session=session)
    assert headlines == ["Bitcoin breaks resistance", "ETF inflows surge"]
    assert session.last_params["currencies"] == "BTC"
    assert session.last_params["auth_token"] == "cp-key"


def test_fetch_headlines_respects_limit():
    payload = {"results": [{"title": f"headline {i}"} for i in range(20)]}
    session = FakeSession(payload)
    headlines = fetch_headlines("ETHUSDT", api_key="cp-key", limit=10, session=session)
    assert len(headlines) == 10
    assert session.last_params["currencies"] == "ETH"


def test_fetch_headlines_unknown_symbol_returns_empty():
    session = FakeSession({"results": []})
    assert fetch_headlines("DOGEUSDT", api_key="cp-key", session=session) == []
