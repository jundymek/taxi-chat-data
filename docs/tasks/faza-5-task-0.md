# Faza 5 / Task 0: SSE frame contract (`api/schemas.py`)

Status: done
Executor: operator-session
Plan: `docs/superpowers/plans/2026-07-18-faza-5-api-frontend.md` → section "Task 0"

## Acceptance Criteria
1. `.venv/bin/pytest tests/test_api_schemas.py -v` → 3 passed; full suite green.
2. `api/schemas.py` defines stage constants, `Frame`, `Result`, `sse()` codec
   exactly as the plan's Interfaces block (Tasks 1–2 build against it).
3. `fastapi`, `uvicorn`, `httpx` added to `requirements.txt` and installed.
4. Committed + pushed to the phase branch BEFORE spawning wave 1.

## Tasks / Subtasks
- [x] Failing contract tests
- [x] Implement `api/__init__.py` + `api/schemas.py`
- [x] Deps + install
- [x] Tests green (3), full suite green (77 passed, 5 deselected)
- [x] Feature record `faza-5-task-0/README.md` + this story close-out + commit

## Dev Agent Record
### Agent Model Used
Claude Fable 5 (claude-fable-5), operator session.
### Completion Notes
- Contract implemented exactly per the plan's Interfaces block; one flat
  `Frame` model with `exclude_none` serialization (see feature record for the
  rationale vs a discriminated union).
### File List
`api/__init__.py`, `api/schemas.py`, `tests/test_api_schemas.py`,
`requirements.txt`, `docs/features/faza-5-api-frontend/faza-5-task-0/README.md`,
`docs/tasks/faza-5-task-0.md`
