import pytest

from signals.llm_client import SeaLionClient


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
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeResponse(self._payload, self._status)


COMPLETION = {"choices": [{"message": {"content": '{"verdict": "confirm"}'}}]}


def test_chat_returns_message_content():
    session = FakeSession(COMPLETION)
    client = SeaLionClient(api_key="sk-test", session=session)
    result = client.chat([{"role": "user", "content": "hello"}])
    assert result == '{"verdict": "confirm"}'


def test_chat_sends_auth_and_model():
    session = FakeSession(COMPLETION)
    client = SeaLionClient(api_key="sk-test", session=session)
    client.chat([{"role": "user", "content": "hello"}])
    assert session.last_url == "https://api.sea-lion.ai/v1/chat/completions"
    assert session.last_headers["Authorization"] == "Bearer sk-test"
    assert session.last_json["model"] == "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
    assert session.last_json["messages"] == [{"role": "user", "content": "hello"}]


def test_chat_raises_on_http_error():
    session = FakeSession({}, status=429)
    client = SeaLionClient(api_key="sk-test", session=session)
    with pytest.raises(RuntimeError):
        client.chat([{"role": "user", "content": "hello"}])
