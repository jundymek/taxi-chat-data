# Faza 3 / Task 2: RAG — indexer + examples + retriever (wave 1)

Implement **"Task 2: RAG — `indexer.py` + `examples.yml` + `retriever.py`"**
from `docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`. Read the full
task section AND the plan's "Global Constraints" — both are binding. The plan
contains complete code (including the curated `examples.yml`) and TDD steps.

## Dependencies
- Task 0 (contracts) is on your base branch — verify `genai/types.py` exists.
- Type-only dependency on Task 1's `LLMClient` — inject a fake embedder in
  tests (see plan); do NOT wait for the task-1 agent and do NOT import
  `genai.llm_client` in your tests.
- Do NOT touch files outside your **Files** list (no `requirements.txt`,
  no `genai/config.py`). Do NOT run `python -m genai.indexer` against live
  Ollama — that happens in Task 5.

## Done when
- `.venv/bin/pytest tests/test_indexer.py tests/test_retriever.py -v` green
  (6 tests, no live services).
- `docs/learn/faza-3-rag-retriever.md` (Polish learning note) written.
