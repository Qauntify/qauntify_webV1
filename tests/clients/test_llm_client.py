import pytest
import requests

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
        self.calls = 0
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls += 1
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeResponse(self._payload, self._status)


class FlakySession:
    """Raises `exc` for the first `fail_times` posts, then returns success."""
    def __init__(self, payload, fail_times, exc=None):
        self._payload = payload
        self._fail_times = fail_times
        self._exc = exc or requests.exceptions.Timeout("read timed out")
        self.calls = 0

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return FakeResponse(self._payload)


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


def test_chat_retries_on_timeout_then_succeeds():
    """A transient read timeout must not kill the call — retry and recover."""
    session = FlakySession(COMPLETION, fail_times=2)
    client = SeaLionClient(api_key="sk-test", session=session, retry_backoff=0)
    result = client.chat([{"role": "user", "content": "hi"}])
    assert result == '{"verdict": "confirm"}'
    assert session.calls == 3  # two timeouts, then success


def test_chat_retries_on_connection_error():
    session = FlakySession(
        COMPLETION, fail_times=1,
        exc=requests.exceptions.ConnectionError("connection reset"),
    )
    client = SeaLionClient(api_key="sk-test", session=session, retry_backoff=0)
    assert client.chat([{"role": "user", "content": "hi"}]) == '{"verdict": "confirm"}'
    assert session.calls == 2


def test_chat_raises_after_exhausting_retries():
    session = FlakySession(COMPLETION, fail_times=99)
    client = SeaLionClient(
        api_key="sk-test", session=session, retry_backoff=0, max_attempts=3,
    )
    with pytest.raises(requests.exceptions.Timeout):
        client.chat([{"role": "user", "content": "hi"}])
    assert session.calls == 3  # capped at max_attempts, not infinite


def test_chat_does_not_retry_http_error_status():
    """A 4xx response is a real answer, not a transient fault — no retry."""
    session = FakeSession({}, status=429)
    client = SeaLionClient(
        api_key="sk-test", session=session, retry_backoff=0, max_attempts=3,
    )
    with pytest.raises(RuntimeError):
        client.chat([{"role": "user", "content": "hi"}])
    assert session.calls == 1
