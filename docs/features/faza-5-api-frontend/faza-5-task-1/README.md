# Faza 5 / Task 1: FastAPI SSE chat endpoint + health

## What was built
A thin FastAPI adapter (`api/main.py`) that streams the Faza 3 LangGraph
pipeline's stages to the browser over Server-Sent Events, plus a dependency
health endpoint. No changes to `genai/` — the adapter only MAPS LangGraph
`stream_mode="updates"` patches onto the SSE frame contract from `api/schemas.py`
(Task 0). Cohort with the frontend (Task 2, bob); the SSE wire format was
intent-synced 1:1 before any code.

- `create_app(pipeline_factory=None) -> FastAPI` — app factory; tests inject a
  fake pipeline, production lazily uses `genai.pipeline.build_pipeline`. The
  pipeline is built on the FIRST `/chat` request (memoized on `app.state`),
  never at import.
- `POST /chat` `{"question": str}` → `text/event-stream` of `sse()` frames.
  Frame = node COMPLETED; happy order `retrieve → generate_sql → validate →
  execute → summarize → done`; `summarize` emitted right after `execute`;
  exactly one terminal frame (`done` XOR `error`). Guardrail refusal = `done`
  with `result.refused:true` (+ Polish `reason`), NEVER `error`. 422 on empty
  question (`Field(min_length=1)`).
- `GET /health` → `{"ollama","bigquery","chroma_index"}`, always HTTP 200;
  probes are module-level functions (`_check_ollama/_check_bigquery/_check_chroma`)
  so tests can stub them offline.
- `frontend/dist` mounted at `/` when the directory exists (consumed in Task 3;
  this task only mounts, never builds it).

## Files touched
- `api/main.py` (NEW) — SSE adapter, `/chat`, `/health`, static mount.
- `tests/test_api_chat.py` (NEW, 7 tests) — fake pipeline + stubbed probes, no
  live services: happy-path frame order + done, retry with two validate frames,
  refusal-is-done-not-error, mid-stream LLMError → terminal error, first-request
  pipeline build failure → terminal error (codex P2 regression), empty→422,
  health reports each dependency.
- `docs/learn/faza-5-fastapi-sse.md` (NEW) — Polish learning note.
- `docs/tasks/faza-5-task-1.md` (UPDATE) — story close-out.

## Key decisions
- **Adapter only maps, never mutates the graph.** `genai/` untouched;
  `stream_mode="updates"` state patches are accumulated and translated to
  frames. Keeps the pipeline the single source of business logic.
- **`summarize` synthesized in the `execute` branch** (`_frames_for`): when
  `execute` completes we emit both `execute` and `summarize` ("writing the
  answer now"); `summarize`/`refuse` node completion is represented by the
  terminal `done`. Cohort-agreed with bob (his intent point 6).
- **Refusal is `done{refused:true}`, not `error`.** `error` is reserved for
  infra failures (`LLMError`/`Exception` mid-stream). This distinction drives
  the frontend rendering (result card vs error banner).
- **Lazy pipeline build on first request, not `@app.on_event("startup")`.**
  Deviation from the plan's literal code: `TestClient(app)` without the `with`
  context manager does not run Starlette's lifespan, so a startup builder would
  leave `app.state.pipeline` unset and fail every test (verified empirically).
  Lazy-on-first-request keeps the same public contract (no build at import) and
  works under both TestClient and uvicorn. See `DECISIONS.md` D5.

## Verification
- `.venv/bin/pytest tests/test_api_chat.py -v` → **7 passed** (6 from the plan +
  1 codex-P2 regression; fake pipeline, no live services).
- `.venv/bin/pytest` (full suite) → **84 passed, 5 deselected** (integration).
- Manual smoke: module imports without building anything; `GET /health` → 200
  with the three-key body (probes stubbed); `POST /chat` → `text/event-stream`
  emitting ordered frames; empty question → 422.
- Full live run (real SSE through the UI, single-port demo) is Task 3's scope,
  after Tasks 1 & 2 merge into the phase branch.
