# Faza 5: FastAPI + mini-frontend (SSE chat UI) — Design

**Goal:** wrap the Faza 3 genai pipeline in a product: `POST /chat` streams
pipeline stages over SSE, `GET /health` reports dependency status, and a
single-screen React app lets the user ask a question in Polish and watch the
pipeline work live (retrieve → SQL → guardrails/retry → execute → answer),
then presents the answer, the SQL used, result rows, and gigabytes scanned.

**Out of scope (deliberate):** `GET /eval` (arrives with the evaluation in
Faza 6), auth (local tool), token-level LLM streaming, Playwright e2e (one
screen; a real-browser check happens in the operator's live task),
docker-compose packaging of the API (Faza 7).

**Decisions from brainstorming:**
- Frontend: **React + Vite + TS SPA** (rejected Next.js/SSR: nothing to
  server-render — all content appears after a user POST; a second server
  runtime would blur the FastAPI narrative; Next competence is already
  evidenced in the owner's film project).
- Transport: **SSE stage streaming (variant B)** — the guardrail retry loop is
  the project's strongest asset and becomes visible live. Source of events is
  LangGraph's `app.stream()` — **no changes to `genai/`**.
- `POST` + streamed body read via `fetch` + `ReadableStream` (native
  `EventSource` is GET-only — noted, deliberate).

## Architecture

```
frontend/ (React+Vite+TS SPA)              api/ (FastAPI)
question → POST /chat ────────────────────▶ StreamingResponse (SSE)
live stage timeline ◀── event: stage ────── maps pipeline.stream() nodes
result card (answer, SQL, rows, GB,        GET /health → ollama/bigquery/chroma
retry history)                             serves frontend/dist when built
```

## SSE protocol (THE contract, fixed in Task 0)

Frames: `event: stage` + `data: <json>`; UTF-8; one frame per pipeline node.

| data | meaning |
|---|---|
| `{"stage":"retrieve"}` | RAG context lookup started |
| `{"stage":"generate_sql","attempt":N}` | LLM generating SQL (attempt N of max 3) |
| `{"stage":"validate","ok":bool,"reason":str?}` | guardrail verdict; `reason` Polish, present when `ok:false` |
| `{"stage":"execute"}` | validated SQL sent to BigQuery |
| `{"stage":"summarize"}` | LLM writing the Polish answer |
| `{"stage":"done","result":Result}` | TERMINAL — full result |
| `{"stage":"error","message":str}` | TERMINAL — infrastructure failure (e.g. Ollama down); Polish message |

`Result = {answer, sql, rows, scanned_gb, attempts, refused, reason, model}`.
Exactly ONE terminal frame per request. A guardrail refusal is NOT `error` —
it is `done` with `refused:true` (rows empty, sql of the last rejected
attempt). Client disconnect aborts pipeline work server-side.

## API (`api/`)

- `api/schemas.py` — Pydantic models for every frame + `Result`, stage-name
  constants (Task 0; single Python source of truth).
- `api/main.py` — FastAPI app; builds the pipeline once at startup
  (`app.state`); `POST /chat` validates `{"question": str}` (400 on
  empty/missing), returns the SSE stream; `GET /health` runs three
  independent checks (Ollama `GET /api/version`, BigQuery dry-run `SELECT 1`,
  Chroma dir exists) — always HTTP 200, values tell the truth; mounts
  `frontend/dist` as static files when present.
- New deps (Task 0 only): `fastapi`, `uvicorn`, `httpx` (TestClient).
- API tests: TestClient + fake pipeline with scripted node sequences;
  asserted event sequences: happy path, retry-then-success, refusal,
  mid-stream exception → `error` frame.

## Frontend (`frontend/`) — senior conventions (binding)

One feature (chat), so NO `features/` indirection — a flat, readable layout
grouped by role (it can graduate to feature-based if the app ever grows):

```
frontend/src/
├── app/                # shell: App.tsx, providers, global styles
├── components/         # PRESENTATIONAL ONLY (props in, JSX out):
│                       # QuestionForm, StageTimeline, AnswerCard,
│                       # SqlDisclosure, ResultsTable, ScanBadge,
│                       # RetryHistory, HealthBadge
├── hooks/              # ALL stateful logic:
│                       # useChatStream.ts (request lifecycle + stage state
│                       # machine), useHealth.ts
├── api/                # streamParser.ts — PURE function: bytes → typed
│                       # frames; chatClient.ts — fetch wiring
├── types.ts            # protocol types, mirrors api/schemas.py 1:1
└── shared/             # generic UI primitives (Spinner, Card)
```

- **Presentational components hold NO logic** — no fetching, no stream
  handling, no business rules; they render props and emit callbacks.
- **All stateful logic lives in hooks** (`useChatStream` owns the request
  lifecycle and stage state machine; components consume its return value).
- **`streamParser` is a pure function** (SSE byte chunks → typed frame
  objects) — unit-tested without any network or React.
- UI copy in Polish; code/comments in English (project convention).
- Vite dev proxy `/chat`,`/health` → `localhost:8000`; `vite build` output
  served by FastAPI in the demo (one process).
- Tests: vitest + RTL — parser unit tests (chunk splitting, partial frames),
  hook tests with a mocked stream, component render tests for each stage of
  the timeline and the three endings (answer / refusal / error).
- **Visual design: APPROVED — variant "C1 / Linia M"** (owner-approved
  2026-07-18). Reference file:
  `docs/superpowers/specs/assets/2026-07-18-faza-5-mockup-c1-approved.html`
  (the C1 section is binding; C2/C3 are rejected alternatives kept for
  context). Visual tokens: white ground `#FFFFFF`, ink `#111111`, taxi/subway
  yellow `#FCCC0A` (route line, ask button, brand bullet "M", highlight
  chip), green `#00933C` (completed stage dots + `OK` status), red `#D0021B`
  (rejected stage + `ODRZUCONE`), Helvetica/system sans + monospace for SQL,
  numbers and stage statuses; black station-sign bars (header, result-card
  header), 2px solid `#111` borders, no border-radius except circles/chips.
  Stage rows: green station dot on the yellow route line, label left, dotted
  leader, monospace status right; rejection reason in red under the row.

## Task split (for the ~/.terminal-agents harness)

| Task | Executor | Coordination |
|---|---|---|
| 0 | in-session | `api/schemas.py` + protocol table + deps; mockup approval gate resolved BEFORE spawning wave 1 |
| 1: API | agent, wave 1 | cohort with task-2 agent — intent-sync on protocol semantics (event order, terminal frames, mid-stream errors) |
| 2: frontend | agent, wave 1 | same cohort; owns `frontend/` entirely (scaffold incl. lockfile); builds to the approved mockup |
| 3 | in-session | `vite build` + single-port serve, live demo incl. a retry-visible question, README, stories close-out, PR |

Files do not overlap (`api/` vs `frontend/`); the cohort machinery covers the
shared protocol semantics, as in Faza 4.

## Conventions (binding, as previous phases)

Code/commits/PR titles English + Conventional (PR title becomes the squash
commit subject); UI strings Polish; per task: Polish learning note
(`docs/learn/faza-5-<topic>.md`), feature record
(`docs/features/faza-5-api-frontend/<task-id>/README.md`), BMAD-style story in
`docs/tasks/` updated before PR. Unit tests touch no live services; live runs
only in Task 3. No AI-attribution footers. Secrets stay out (ADC only).
