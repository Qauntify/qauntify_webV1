"""Client for the SEA-LION chat completions API (OpenAI-compatible)."""
import requests

DEFAULT_BASE_URL = "https://api.sea-lion.ai/v1"
DEFAULT_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
DEFAULT_EMBED_MODEL = "aisingapore/SEA-LION-ModernBERT-Embedding-600M"


class SeaLionClient:
    def __init__(self, api_key, model=DEFAULT_MODEL,
                 base_url=DEFAULT_BASE_URL, session=None,
                 embed_model=DEFAULT_EMBED_MODEL):
        self._api_key = api_key
        self._model = model
        self._embed_model = embed_model
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()

    def embed(self, text: str) -> list:
        """Return one embedding vector for playbook retrieval."""
        response = self._session.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._embed_model, "input": [text]},
            timeout=60,
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
        response = self._session.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=60,
        )
        # Some SEA-LION deployments reject response_format — retry plain.
        if response.status_code >= 400 and "response_format" in (getattr(response, "text", "") or ""):
            payload.pop("response_format", None)
            response = self._session.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=60,
            )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
