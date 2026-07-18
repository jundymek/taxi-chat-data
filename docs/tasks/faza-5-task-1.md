# Faza 5 / Task 1: FastAPI SSE chat endpoint + health

Status: done
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
- [x] Intent-sync with the frontend agent (see Coordination) BEFORE any code
- [x] Failing tests (`tests/test_api_chat.py`)
- [x] Implement `api/main.py` (plan has the full code)
- [x] Tests green + full suite green
- [x] Polish learning note + feature record
- [x] Update this story + commit

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
Claude Opus 4.8 (1M context) — `claude-opus-4-8[1m]`.

### Debug Log References
- Verified the plan's literal `@app.on_event("startup")` pipeline builder would
  fail the tests: `TestClient(app)` is used WITHOUT the `with` context manager,
  so Starlette's lifespan/startup never runs and `app.state.pipeline` stays
  unset. Empirical probe: `without with: NOT-SET`, `with with: startup-ran`.
  Resolved by building the pipeline lazily on the first `/chat` request
  (memoized on `app.state`). See DECISIONS.md D5.
- Cross-checked the plan code against the live pipeline (`genai/pipeline.py`):
  `execute` returns the amended `validation.sql` (so `done.result.sql` is the
  LIMIT-appended SQL); `refuse` sets `refused=True` while `validation.reason`
  supplies the Polish reason; graph edge `execute → summarize → END` confirms
  the "summarize after execute" mapping.

### Completion Notes List
- Implemented `api/main.py` as a thin adapter over the Faza 3 LangGraph
  pipeline; `genai/` untouched. Frame contract per `api/schemas.py` (Task 0).
- SSE semantics: frame = node completed; happy order retrieve → generate_sql →
  validate → execute → summarize → done; `summarize` emitted right after
  `execute`; exactly one terminal frame; guardrail refusal = `done` with
  `refused:true` (never `error`); 422 on empty question.
- `/health` always returns HTTP 200 with `{ollama, bigquery, chroma_index}`;
  probes are module-level for offline stubbing.
- One deliberate deviation from the plan's literal code (lazy pipeline build vs
  startup event) — behaviourally equivalent, strictly more correct; flagged in
  DECISIONS.md D5 and PR summary.
- Cohort intent-sync with bob (Task 2) completed before any code; SSE wire
  format agreed 1:1.
- Tests: `tests/test_api_chat.py` → 7 passed (6 from the plan + 1 regression
  for a codex P2: first-request pipeline build failure → terminal `error` frame,
  not a raw 500); full suite → 84 passed, 5 deselected (integration). Manual
  smoke green (import, /health 200, /chat SSE, empty→422).
- Codex review (session 019f75b3): 1 finding [P2], fixed (build resolver moved
  inside the streamed try + regression test); re-run clean.

### File List
- `api/main.py` (NEW)
- `tests/test_api_chat.py` (NEW)
- `docs/learn/faza-5-fastapi-sse.md` (NEW)
- `docs/features/faza-5-api-frontend/faza-5-task-1/README.md` (NEW)
- `docs/tasks/faza-5-task-1.md` (UPDATE)
