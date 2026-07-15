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

## Tasks / Subtasks (plan Task 2 steps; checkboxes tracked here, not in the
shared plan file, to avoid cross-agent merge conflicts)
- [x] Step 1: Write the failing indexer tests (`tests/test_indexer.py`)
- [x] Step 2: Run indexer tests to verify they fail (ModuleNotFoundError)
- [x] Step 3: Implement `genai/indexer.py`
- [x] Step 4: Run indexer tests to verify they pass (4 PASS)
- [x] Step 5: Write `genai/examples.yml` (10 curated PL → BigQuery few-shots)
- [x] Step 6: Write the failing retriever tests (`tests/test_retriever.py`)
- [x] Step 7: Run retriever tests to verify they fail (ModuleNotFoundError)
- [x] Step 8: Implement `genai/retriever.py`
- [x] Step 9: Run all Task 2 tests to verify they pass (6 PASS)
- [x] Step 10: Write the Polish learning note (`docs/learn/faza-3-rag-retriever.md`)
- [x] Step 11: Commit

## Dev Agent Record

### Agent Model Used
Claude Fable 5 (claude-fable-5), Claude Code, autonomous mode (agent: bob).

### Debug Log References
None — all six tests passed on first implementation; full unit suite
(21 passed, integration deselected) green in the mainline venv.

### Completion Notes List
- Implemented exactly per the plan's Task 2 section (code was fully specified
  there); no deviations from the specified interfaces.
- `SCHEMA_COLLECTION`/`EXAMPLES_COLLECTION` constants live in `indexer.py` and
  are imported by `retriever.py`, as the cross-task contract requires.
- Tests inject a deterministic `FakeEmbedder`; `genai.llm_client` is never
  imported by tests (type-only dependency on Task 1 honored).
- `python -m genai.indexer` was deliberately NOT run — live index build
  happens in Task 5.
- Checkboxes for Task 2 in the shared plan file were intentionally left
  untouched (three wave-1 agents share that file; edits would collide) —
  completion is tracked in this story file instead.

### File List
- `genai/indexer.py` (NEW)
- `genai/examples.yml` (NEW)
- `genai/retriever.py` (NEW)
- `tests/test_indexer.py` (NEW)
- `tests/test_retriever.py` (NEW)
- `docs/learn/faza-3-rag-retriever.md` (NEW)
- `docs/tasks/faza-3-task-2.md` (UPDATE — this record)
- `docs/features/faza-3-genai-chat/faza-3-task-2/README.md` (NEW)
