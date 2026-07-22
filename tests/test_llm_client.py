import pytest
import requests

from genai.llm_client import LLMClient
from genai.types import LLMError


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_generate_returns_response_text(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "SELECT 1"})

    monkeypatch.setattr(requests, "post", fake_post)
    client = LLMClient()
    out = client.generate("write sql", system="you are a sql bot")
    assert out == "SELECT 1"
    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["stream"] is False
    assert captured["json"]["system"] == "you are a sql bot"


def test_generate_sends_deterministic_options(monkeypatch):
    # Temperature 0 + fixed seed is what makes the eval reproducible; without
    # it Ollama defaults to 0.8 and every run scores differently.
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse({"response": "SELECT 1"})

    monkeypatch.setattr(requests, "post", fake_post)
    LLMClient().generate("write sql")
    assert captured["json"]["options"]["temperature"] == 0.0
    assert captured["json"]["options"]["seed"] == 42


def test_generate_raises_llm_error_when_ollama_down(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(LLMError, match="ollama serve"):
        LLMClient().generate("hi")


def test_generate_raises_llm_error_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({}, status=404))
    with pytest.raises(LLMError):
        LLMClient().generate("hi")


def test_embed_uses_embedding_model_and_returns_vectors(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    monkeypatch.setattr(requests, "post", fake_post)
    vectors = LLMClient().embed(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"].endswith("/api/embed")
    assert captured["json"]["model"] == "nomic-embed-text:latest"
    assert captured["json"]["input"] == ["a", "b"]


def test_embed_raises_llm_error_on_malformed_payload(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"weird": True}))
    with pytest.raises(LLMError):
        LLMClient().embed(["a"])


def test_generate_raises_llm_error_on_non_json_body(monkeypatch):
    class NonJSONResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            raise requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)

    monkeypatch.setattr(requests, "post", lambda *a, **k: NonJSONResponse())
    with pytest.raises(LLMError):
        LLMClient().generate("hi")
