# Faza 3 / Task 1: `llm_client.py` — Ollama HTTP client (wave 1)

Implement **"Task 1: `llm_client.py` — Ollama HTTP client"** from
`docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`. Read the full task
section AND the plan's "Global Constraints" — both are binding. The plan
contains complete code and TDD steps; follow them.

## Dependencies
- Task 0 (contracts in `genai/types.py` + `genai/config.py`) is already on your
  base branch — verify `genai/config.py` exists before starting.
- Fully independent of tasks 2 and 3 — no peer coordination needed, but do NOT
  touch any file outside your task's **Files** list (especially
  `requirements.txt`, `genai/config.py`, `genai/types.py`).

## Done when
- `.venv/bin/pytest tests/test_llm_client.py -v` green (5 tests, no live Ollama needed).
- `docs/learn/faza-3-llm-client.md` (Polish learning note) written.
