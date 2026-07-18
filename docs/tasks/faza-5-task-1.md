# Faza 5 / Task 1: FastAPI SSE chat endpoint + health

Status: planned
Executor: agent (wave 1, cohort with faza-5-task-2)
Plan: `docs/superpowers/plans/2026-07-18-faza-5-api-frontend.md` → section
"Task 1" (technical source of truth — complete code + TDD steps; read it AND
"Global Constraints" first)

## Acceptance Criteria
1. `.venv/bin/pytest tests/test_api_chat.py -v` → 6 passed (fake pipeline, no
   live services); full suite stays green.
2. `create_app(pipeline_factory=None)`; `POST /chat` streams `sse()` frames
   with the plan's exact frame semantics (completed-node frames; `summarize`
   emitted after `execute`; exactly one terminal `done`/`error`); guardrail
   refusal = `done` with `refused:true`, NEVER `error`; 422 on empty question.
3. `GET /health` → `{"ollama","bigquery","chroma_index"}`, always HTTP 200.
4. `frontend/dist` mounted when present. No changes to `genai/` or `frontend/`.
5. `docs/learn/faza-5-fastapi-sse.md` + feature record written.
6. THIS story updated before PR (Status: done, checkboxes, Dev Agent Record).

## Tasks / Subtasks
- [ ] Intent-sync with the frontend agent (see Coordination) BEFORE any code
- [ ] Failing tests (`tests/test_api_chat.py`)
- [ ] Implement `api/main.py` (plan has the full code)
- [ ] Tests green + full suite green
- [ ] Polish learning note + feature record
- [ ] Update this story + commit

## Coordination
- **Cohort with faza-5-task-2 (frontend) — REQUIRED:** configure the cohort,
  write `intent.md` declaring your reading of the SSE protocol (frame order,
  when `summarize` fires, one terminal frame, refusal-vs-error), run
  intent-sync (`intent-ready.sh`, mutual acks). Protocol doubts →
  `agent-msg.sh send <peer> ...`, never guess.
- Task 0 (`api/schemas.py`) is on your base branch — verify before starting.
  Do NOT touch `frontend/`, `genai/`, or `requirements.txt`.

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
