# Faza 3 / Task 3: `guardrails.py` — SQL validation (wave 1)

Implement **"Task 3: `guardrails.py` — SQL validation before execution"** from
`docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`. Read the full task
section AND the plan's "Global Constraints" — both are binding. The plan
contains complete code and TDD steps.

## Dependencies
- Task 0 (contracts) is on your base branch — verify `genai/types.py` exists.
- Fully independent of tasks 1 and 2: guardrails import NOTHING from
  `llm_client`/`retriever` (pure sqlglot + BigQuery dry-run with an injectable
  stub client in tests).
- Do NOT touch files outside your **Files** list. Unit tests must NOT hit live
  BigQuery (use the FakeBQClient from the plan).

## Done when
- `.venv/bin/pytest tests/test_guardrails.py -v` green (10 tests, no live GCP).
- `docs/learn/faza-3-guardrails.md` (Polish learning note) written.
