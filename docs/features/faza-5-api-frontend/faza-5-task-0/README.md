# Faza 5 / Task 0: SSE frame contract

## What was built
The protocol contract both wave-1 agents (API, frontend) build against:
`api/schemas.py` with stage-name constants, the `Frame` and `Result` Pydantic
models, and the `sse()` codec producing `event: stage` + single-line JSON
events with nulls excluded. Executed in the operator session BEFORE spawning,
so the cohort forks with the contract in place.

## Files touched
- `api/__init__.py`, `api/schemas.py` (NEW) — the contract module.
- `tests/test_api_schemas.py` (NEW, 3 tests) — SSE framing, null exclusion,
  single-line JSON (newlines escaped).
- `requirements.txt` (UPDATE) — `fastapi`, `uvicorn`, `httpx`.

## Key decisions
- **One flat `Frame` model with optional fields** instead of a union of
  per-stage models — the protocol has 6 optional fields total; a discriminated
  union would be ceremony without safety gain at this size. `exclude_none`
  keeps the wire format tight.
- **Refusal-vs-error split lives in the contract docstring**: guardrail
  refusal is `done` with `refused: true`; `error` is reserved for
  infrastructure failure. The frontend renders them differently.

## Verification
- `.venv/bin/pytest tests/test_api_schemas.py -v` — 3 passed (TDD: failed
  with `ModuleNotFoundError` first).
- Full suite: 77 passed, 5 integration deselected.
