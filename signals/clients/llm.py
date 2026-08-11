"""Client for the SEA-LION chat completions API (OpenAI-compatible)."""
import time

import requests

DEFAULT_BASE_URL = "https://api.sea-lion.ai/v1"
DEFAULT_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
DEFAULT_EMBED_MODEL = "aisingapore/SEA-LION-ModernBERT-Embedding-600M"
DEFAULT_TIMEOUT = 60
# Total attempts (1 original + retries) for a single request.
DEFAULT_MAX_ATTEMPTS = 3
# Seconds to wait before retry N (linear: backoff, 2*backoff, ...).
DEFAULT_RETRY_BACKOFF = 1.5

# Transient faults worth retrying: a slow/dropped connection is not a verdict.
# HTTP status errors (4xx/5xx) surface via raise_for_status and are NOT retried
# here — a 4xx is a real answer, and confirm_setup fail-closes on the rest.
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


class SeaLionClient:
    def __init__(self, api_key, model=DEFAULT_MODEL,
                 base_url=DEFAULT_BASE_URL, session=None,
                 embed_model=DEFAULT_EMBED_MODEL,
                 timeout=DEFAULT_TIMEOUT,
                 max_attempts=DEFAULT_MAX_ATTEMPTS,
                 retry_backoff=DEFAULT_RETRY_BACKOFF):
        self._api_key = api_key
        self._model = model
        self._embed_model = embed_model
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        self._retry_backoff = retry_backoff

    def _post(self, path: str, payload: dict):
        """POST `payload` to `path`, retrying transient network faults.

        A read timeout or dropped connection is retried up to `max_attempts`
        total, with linear backoff — so one slow SEA-LION response no longer
        turns a valid setup into a reject. Non-transient failures (and the
        final transient one) propagate to the caller.
        """
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_exc = None
        for attempt in range(self._max_attempts):
            try:
                return self._session.post(
                    url, headers=headers, json=payload, timeout=self._timeout,
                )
            except RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(self._retry_backoff * (attempt + 1))
        raise last_exc

    def embed(self, text: str) -> list:
        """Return one embedding vector for playbook retrieval."""
        response = self._post(
            "/embeddings", {"model": self._embed_model, "input": [text]},
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    def chat(self, messages, temperature=0.2):
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            # Prefer structured JSON when the gateway supports it; ignored
            # by models that don't — parse_confirmation still fail-closes.
            "response_format": {"type": "json_object"},
        }
        response = self._post("/chat/completions", payload)
        # Some SEA-LION deployments reject response_format — retry plain.
        if response.status_code >= 400 and "response_format" in (getattr(response, "text", "") or ""):
            payload.pop("response_format", None)
            response = self._post("/chat/completions", payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
