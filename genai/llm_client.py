"""Thin HTTP client for the local Ollama server. No framework, no magic."""
import requests

from genai import config
from genai.types import LLMError

_CONNECTION_HINT = (
    "Cannot connect to Ollama at {url}. "
    "Run `ollama serve` and check that the model is installed (`ollama list`)."
)


class LLMClient:
    def __init__(
        self,
        model: str = config.GENERATION_MODEL,
        base_url: str = config.OLLAMA_BASE_URL,
        timeout: int = config.OLLAMA_TIMEOUT,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str, system: str | None = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Deterministic by default (see config): NL2SQL wants the most
            # likely SQL, and a reproducible eval score, not sampling variety.
            "options": {
                "temperature": config.GENERATION_TEMPERATURE,
                "seed": config.GENERATION_SEED,
            },
        }
        if system is not None:
            payload["system"] = system
        data = self._post("/api/generate", payload)
        if "response" not in data:
            raise LLMError(f"Unexpected Ollama /api/generate payload: {list(data)}")
        return data["response"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": config.EMBEDDING_MODEL, "input": texts}
        data = self._post("/api/embed", payload)
        if "embeddings" not in data:
            raise LLMError(f"Unexpected Ollama /api/embed payload: {list(data)}")
        return data["embeddings"]

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.ConnectionError as exc:
            raise LLMError(_CONNECTION_HINT.format(url=self.base_url)) from exc
        except requests.RequestException as exc:
            raise LLMError(f"Ollama request to {path} failed: {exc}") from exc
