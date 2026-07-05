"""Client for the SEA-LION chat completions API (OpenAI-compatible)."""
import requests

DEFAULT_BASE_URL = "https://api.sea-lion.ai/v1"
DEFAULT_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


class SeaLionClient:
    def __init__(self, api_key, model=DEFAULT_MODEL,
                 base_url=DEFAULT_BASE_URL, session=None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()

    def chat(self, messages, temperature=0.2):
        response = self._session.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
