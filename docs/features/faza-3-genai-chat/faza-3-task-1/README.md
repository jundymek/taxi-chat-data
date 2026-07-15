# Faza 3 / Task 1 — `llm_client.py` (Ollama HTTP client)

## What was built

A thin, dependency-free (beyond `requests`) HTTP client for the local Ollama
server, providing the two LLM operations the rest of the Faza 3 pipeline needs:

- `LLMClient.generate(prompt, system=None) -> str` — non-streaming text
  generation via `POST /api/generate` using `config.GENERATION_MODEL`.
- `LLMClient.embed(texts) -> list[list[float]]` — batch embeddings via
  `POST /api/embed`, always using `config.EMBEDDING_MODEL` regardless of the
  instance's generation model (indexing and querying must share one embedding
  space).

All network and payload-shape failures are translated into the shared domain
exception `genai.types.LLMError`; a connection failure carries an actionable
Polish hint ("Uruchom `ollama serve`...").

## Files

- `genai/llm_client.py` (NEW) — the client; implements the exact interface
  contract from the plan that Tasks 2 and 4 build against.
- `tests/test_llm_client.py` (NEW) — 5 unit tests, `requests.post` mocked via
  monkeypatch; no live Ollama required.
- `docs/learn/faza-3-llm-client.md` (NEW) — Polish learning note (Ollama API,
  embeddings, domain-error wrapping, why tests mock HTTP).

## Key decisions

- Code taken verbatim from the implementation plan (`docs/superpowers/plans/
  2026-07-15-faza-3-genai-chat.md`, Task 1) — the Interfaces block is a
  binding contract for peer tasks, so no redesign.
- The shared plan file was NOT modified (Global Constraints forbid wave-1
  tasks touching files outside their Files list); story completion is
  documented here instead.

## Verification

- `pytest tests/test_llm_client.py -v` → 5 passed (offline, mocked HTTP).
- Full suite: 20 passed, 1 deselected (integration-marked, excluded by default).
- Live manual smoke against local Ollama: `generate('Reply with exactly: OK')`
  returned `OK`; `embed(2 texts)` returned 2 vectors of dim 768.
