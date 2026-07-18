# Faza 5: FastAPI SSE chat API + Vite React frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Harness note:** Tasks 1 (API) and 2 (frontend) run as a COHORT of two
> parallel agents. Files do not overlap (`api/` vs `frontend/`); the shared
> surface is the SSE protocol — both MUST intent-sync on its semantics (frame
> order, terminal frames, mid-stream errors) before coding and use
> `agent-msg.sh` for protocol questions. Tasks 0 and 3 run in the operator
> session. The frontend implements the OWNER-APPROVED mockup C1 —
> `docs/superpowers/specs/assets/2026-07-18-faza-5-mockup-c1-approved.html`
> (section C1 is binding).

**Goal:** `POST /chat` streams the Faza 3 pipeline's stages over SSE and a
single-screen React app (mockup C1, "Linia M") shows the live stage timeline —
including guardrail rejections — then the answer, SQL, rows and GB scanned.

**Architecture:** FastAPI adapter over LangGraph `pipeline.stream()` (no
changes to `genai/`), Pydantic-typed SSE frames (`api/schemas.py` is THE
contract), Vite+React+TS SPA with a pure stream parser, all stateful logic in
`useChatStream`, presentational components only. Spec:
`docs/superpowers/specs/2026-07-18-faza-5-api-frontend-design.md`.

**Tech Stack:** FastAPI + uvicorn + httpx (tests) in the existing `.venv`;
Vite + React 18 + TypeScript + vitest + Testing Library (jsdom) in
`frontend/` (Node ≥20, plain npm).

## Global Constraints

- Code/comments/commits/PR titles in ENGLISH; PR title Conventional
  (`feat(faza-5-task-N): ...`) — squash-merge inherits it. UI copy in POLISH.
- Per agent task: Polish learning note `docs/learn/faza-5-<topic>.md` +
  feature record `docs/features/faza-5-api-frontend/<task-id>/README.md` +
  BMAD story in `docs/tasks/` updated before PR (Status, checkboxes, record).
- Unit tests touch NO live services (no Ollama, no BigQuery, no real HTTP);
  live runs only in Task 3. Python: `.venv/bin/pytest`; frontend: `npm test`
  inside `frontend/`.
- New Python deps (Task 0 ONLY): `fastapi`, `uvicorn`, `httpx`. Frontend deps
  live entirely in `frontend/package.json` (task-2 agent owns them).
- Visual tokens (binding, from approved mockup C1): white `#FFFFFF`, ink
  `#111111`, yellow `#FCCC0A`, green `#00933C`, red `#D0021B`; Helvetica/
  system sans; monospace for SQL, numbers, stage statuses; black station-sign
  bars; 2px solid ink borders; no border-radius except circles/chips/pills.
- Task 1 must not touch `frontend/` or `genai/`; Task 2 must not touch `api/`,
  `genai/`, or `requirements.txt`.

---

## File Structure

```
api/
├── __init__.py            # Task 0
├── schemas.py             # Task 0 — Frame, Result, stage constants, sse() codec
└── main.py                # Task 1 — create_app(), /chat SSE, /health, static mount
tests/
├── test_api_schemas.py    # Task 0
└── test_api_chat.py       # Task 1
frontend/                  # Task 2 (agent owns the whole tree)
├── package.json, vite.config.ts, tsconfig.json, index.html
└── src/
    ├── app/App.tsx, app/styles.css
    ├── components/ (QuestionForm, StageTimeline, ResultCard, HealthBar)
    ├── hooks/useChatStream.ts, hooks/useHealth.ts
    ├── api/streamParser.ts, api/chatClient.ts
    ├── types.ts
    └── __tests__/ (streamParser, useChatStream, StageTimeline, ResultCard)
```

---

## Task 0: `api/schemas.py` — SSE frame contract (in-session, BEFORE spawning)

**Files:**
- Create: `api/__init__.py`, `api/schemas.py`
- Test: `tests/test_api_schemas.py`
- Modify: `requirements.txt` (append `fastapi>=0.115`, `uvicorn>=0.30`, `httpx>=0.27`)

**Interfaces:**
- Consumes: nothing.
- Produces (Tasks 1–2 build against EXACTLY this):
  - Stage constants: `STAGE_RETRIEVE/GENERATE_SQL/VALIDATE/EXECUTE/SUMMARIZE/DONE/ERROR`
    with values `"retrieve" | "generate_sql" | "validate" | "execute" |
    "summarize" | "done" | "error"`.
  - `class Result(BaseModel)`: `answer: str`, `sql: str`, `rows: list[dict]`,
    `scanned_gb: float`, `attempts: int`, `refused: bool`,
    `reason: str | None = None`, `model: str`.
  - `class Frame(BaseModel)`: `stage: str`, `attempt: int | None = None`,
    `ok: bool | None = None`, `reason: str | None = None`,
    `message: str | None = None`, `result: Result | None = None`.
  - `def sse(frame: Frame) -> bytes` — one SSE event:
    `b"event: stage\ndata: <json-without-nulls>\n\n"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_api_schemas.py`:
```python
import json

from api.schemas import (
    STAGE_DONE, STAGE_VALIDATE, Frame, Result, sse,
)


def test_sse_frames_are_valid_sse_events_without_null_fields():
    raw = sse(Frame(stage=STAGE_VALIDATE, ok=False, reason="Tylko SELECT."))
    text = raw.decode("utf-8")
    assert text.startswith("event: stage\ndata: ")
    assert text.endswith("\n\n")
    data = json.loads(text.split("data: ", 1)[1])
    assert data == {"stage": "validate", "ok": False, "reason": "Tylko SELECT."}


def test_done_frame_carries_full_result():
    result = Result(answer="4,16 USD", sql="SELECT 1", rows=[{"avg_tip": 4.16}],
                    scanned_gb=0.048, attempts=2, refused=False, model="gemma4:latest")
    data = json.loads(sse(Frame(stage=STAGE_DONE, result=result)).decode().split("data: ", 1)[1])
    assert data["result"]["attempts"] == 2
    assert data["result"]["rows"] == [{"avg_tip": 4.16}]
    assert "reason" not in data["result"]  # nulls excluded


def test_frame_json_is_single_line():
    raw = sse(Frame(stage=STAGE_DONE, result=Result(
        answer="a\nb", sql="s", rows=[], scanned_gb=0.0, attempts=1,
        refused=True, reason="r", model="m")))
    body = raw.decode().split("data: ", 1)[1]
    assert "\n" not in body.rstrip("\n")  # newlines inside JSON are escaped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Implement `api/schemas.py`**

`api/__init__.py`:
```python
"""FastAPI layer over the genai pipeline (Faza 5)."""
```

`api/schemas.py`:
```python
"""THE SSE protocol contract between the API and the frontend.

One frame per pipeline event: `event: stage` + single-line JSON data.
Exactly one terminal frame per request: `done` (with Result) or `error`.
A guardrail refusal is NOT `error` — it is `done` with `refused: true`.
"""
from pydantic import BaseModel

STAGE_RETRIEVE = "retrieve"
STAGE_GENERATE_SQL = "generate_sql"
STAGE_VALIDATE = "validate"
STAGE_EXECUTE = "execute"
STAGE_SUMMARIZE = "summarize"
STAGE_DONE = "done"
STAGE_ERROR = "error"


class Result(BaseModel):
    answer: str
    sql: str
    rows: list[dict]
    scanned_gb: float
    attempts: int
    refused: bool
    reason: str | None = None
    model: str


class Frame(BaseModel):
    stage: str
    attempt: int | None = None      # generate_sql frames
    ok: bool | None = None          # validate frames
    reason: str | None = None       # validate frames when ok is False (Polish)
    message: str | None = None      # error frames (Polish)
    result: Result | None = None    # done frames


def sse(frame: Frame) -> bytes:
    payload = frame.model_dump_json(exclude_none=True)
    return f"event: stage\ndata: {payload}\n\n".encode("utf-8")
```

- [ ] **Step 4: Add deps and install**

Append to `requirements.txt`: `fastapi>=0.115`, `uvicorn>=0.30`, `httpx>=0.27`.
Run: `.venv/bin/pip install -r requirements.txt`

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_schemas.py -v` → 3 PASS.
Full suite: `.venv/bin/pytest` → all green.

- [ ] **Step 6: Commit**

```bash
git add api/ tests/test_api_schemas.py requirements.txt
git commit -m "feat: SSE frame contract for the chat API (Faza 5 task 0)"
```

---

## Task 1: `api/main.py` — FastAPI SSE endpoint + health (wave 1, agent, cohort with Task 2)

**Files:**
- Create: `api/main.py`
- Test: `tests/test_api_chat.py`
- Create: `docs/learn/faza-5-fastapi-sse.md` (Polish learning note)
- Create: `docs/features/faza-5-api-frontend/faza-5-task-1/README.md`

**Interfaces:**
- Consumes: everything from `api/schemas.py` (Task 0, exact names above);
  `genai.pipeline.build_pipeline()` (Faza 3 — compiled LangGraph app whose
  `.stream({"question": q}, stream_mode="updates")` yields
  `{node_name: state_patch}` dicts for nodes `retrieve`, `generate_sql`,
  `validate`, `execute`, `summarize`, `refuse`); `genai.types.LLMError`,
  `ValidationResult`; `genai.config` (GENERATION_MODEL, OLLAMA_BASE_URL,
  BQ_PROJECT, CHROMA_DIR, REPO_ROOT).
- Produces:
  - `create_app(pipeline_factory=None) -> FastAPI` — tests inject a fake
    factory; `None` uses `genai.pipeline.build_pipeline` lazily at startup.
  - `POST /chat` body `{"question": str}` (422 on missing/empty) →
    `text/event-stream` of `sse()` frames.
  - Frame semantics (agreed with the frontend in intent-sync): a frame is
    emitted when its node COMPLETES, except `summarize` which is emitted
    right after `execute` completes (meaning "writing the answer now");
    `refuse`/`summarize` completions are represented by the terminal `done`.
  - `GET /health` → `{"ollama": "ok"|"down", "bigquery": "ok"|"down",
    "chroma_index": "ok"|"missing"}`, always HTTP 200.
  - Serves `frontend/dist` at `/` when the directory exists.

- [ ] **Step 1: Write the failing tests**

`tests/test_api_chat.py`:
```python
import json

from fastapi.testclient import TestClient

from api.main import create_app
from genai.types import ValidationResult

VAL_OK = ValidationResult(ok=True, sql="SELECT 1 LIMIT 1", reason=None, estimated_bytes=512)
VAL_BAD = ValidationResult(ok=False, sql="DROP x", reason="Tylko SELECT.", estimated_bytes=None)


class FakePipeline:
    """Yields scripted {node: patch} updates like LangGraph stream_mode='updates'."""

    def __init__(self, updates, error=None):
        self.updates = updates
        self.error = error

    def stream(self, state, stream_mode="updates"):
        assert stream_mode == "updates"
        for update in self.updates:
            yield update
        if self.error:
            raise self.error


def _frames(client, question="Ile kursów?"):
    with client.stream("POST", "/chat", json={"question": question}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes()).decode()
    return [json.loads(part.split("data: ", 1)[1])
            for part in body.split("\n\n") if part.startswith("event: stage")]


HAPPY = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "SELECT 1", "attempts": 1}},
    {"validate": {"validation": VAL_OK}},
    {"execute": {"rows": [{"c": 5}], "scanned_bytes": 48_000_000, "sql": VAL_OK.sql}},
    {"summarize": {"answer": "Pięć kursów."}},
]


def test_happy_path_emits_ordered_frames_and_done():
    client = TestClient(create_app(lambda: FakePipeline(HAPPY)))
    frames = _frames(client)
    assert [f["stage"] for f in frames] == [
        "retrieve", "generate_sql", "validate", "execute", "summarize", "done"]
    assert frames[1]["attempt"] == 1
    assert frames[2]["ok"] is True and "reason" not in frames[2]
    done = frames[-1]["result"]
    assert done == {"answer": "Pięć kursów.", "sql": "SELECT 1 LIMIT 1",
                    "rows": [{"c": 5}], "scanned_gb": 0.048, "attempts": 1,
                    "refused": False, "model": done["model"]}


RETRY = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "SELECT * FROM raw.trips", "attempts": 1}},
    {"validate": {"validation": VAL_BAD, "error_feedback": VAL_BAD.reason}},
    {"generate_sql": {"sql": "SELECT 1", "attempts": 2}},
    {"validate": {"validation": VAL_OK}},
    {"execute": {"rows": [], "scanned_bytes": 0, "sql": VAL_OK.sql}},
    {"summarize": {"answer": "Zero."}},
]


def test_retry_emits_two_validate_frames_with_reason_on_failure():
    frames = _frames(TestClient(create_app(lambda: FakePipeline(RETRY))))
    validates = [f for f in frames if f["stage"] == "validate"]
    assert validates[0] == {"stage": "validate", "ok": False, "reason": "Tylko SELECT."}
    assert validates[1]["ok"] is True
    assert frames[-1]["result"]["attempts"] == 2


REFUSAL = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "DROP x", "attempts": 3}},
    {"validate": {"validation": VAL_BAD, "error_feedback": VAL_BAD.reason}},
    {"refuse": {"refused": True, "answer": "Nie umiem bezpiecznie odpowiedzieć."}},
]


def test_refusal_is_done_with_refused_true_not_error():
    frames = _frames(TestClient(create_app(lambda: FakePipeline(REFUSAL))))
    done = frames[-1]
    assert done["stage"] == "done"
    assert done["result"]["refused"] is True
    assert done["result"]["reason"] == "Tylko SELECT."
    assert done["result"]["rows"] == []
    assert not any(f["stage"] == "error" for f in frames)


def test_midstream_exception_yields_terminal_error_frame():
    from genai.types import LLMError
    client = TestClient(create_app(
        lambda: FakePipeline(HAPPY[:2], error=LLMError("Ollama nie odpowiada"))))
    frames = _frames(client)
    assert frames[-1]["stage"] == "error"
    assert "Ollama" in frames[-1]["message"]
    assert not any(f["stage"] == "done" for f in frames)


def test_empty_question_is_422():
    client = TestClient(create_app(lambda: FakePipeline([])))
    assert client.post("/chat", json={"question": ""}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422


def test_health_reports_each_dependency(monkeypatch):
    import api.main as main
    monkeypatch.setattr(main, "_check_ollama", lambda: "ok")
    monkeypatch.setattr(main, "_check_bigquery", lambda: "down")
    monkeypatch.setattr(main, "_check_chroma", lambda: "missing")
    client = TestClient(create_app(lambda: FakePipeline([])))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ollama": "ok", "bigquery": "down", "chroma_index": "missing"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: Implement `api/main.py`**

```python
"""FastAPI adapter over the Faza 3 LangGraph pipeline.

POST /chat streams SSE frames (api/schemas.py is the contract); GET /health
reports dependency status; frontend/dist is served statically when built.
"""
from collections.abc import Iterator
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.schemas import (
    STAGE_DONE, STAGE_ERROR, STAGE_EXECUTE, STAGE_GENERATE_SQL,
    STAGE_RETRIEVE, STAGE_SUMMARIZE, STAGE_VALIDATE, Frame, Result, sse,
)
from genai import config
from genai.types import LLMError


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


def _frames_for(node: str, state: dict) -> list[Frame]:
    if node == "retrieve":
        return [Frame(stage=STAGE_RETRIEVE)]
    if node == "generate_sql":
        return [Frame(stage=STAGE_GENERATE_SQL, attempt=state.get("attempts"))]
    if node == "validate":
        v = state["validation"]
        return [Frame(stage=STAGE_VALIDATE, ok=v.ok,
                      reason=None if v.ok else v.reason)]
    if node == "execute":
        # execute finished; the pipeline is now writing the Polish answer.
        return [Frame(stage=STAGE_EXECUTE), Frame(stage=STAGE_SUMMARIZE)]
    return []  # summarize / refuse completions are represented by `done`


def _done_frame(state: dict) -> Frame:
    refused = bool(state.get("refused", False))
    validation = state.get("validation")
    return Frame(stage=STAGE_DONE, result=Result(
        answer=state.get("answer", ""),
        sql=state.get("sql", ""),
        rows=state.get("rows", []),
        scanned_gb=round(state.get("scanned_bytes", 0) / 1e9, 4),
        attempts=state.get("attempts", 0),
        refused=refused,
        reason=(validation.reason if refused and validation is not None else None),
        model=config.GENERATION_MODEL,
    ))


def stream_chat(pipeline, question: str) -> Iterator[bytes]:
    state: dict = {"question": question}
    try:
        for update in pipeline.stream({"question": question}, stream_mode="updates"):
            for node, patch in update.items():
                state.update(patch or {})
                for frame in _frames_for(node, state):
                    yield sse(frame)
    except LLMError as exc:
        yield sse(Frame(stage=STAGE_ERROR, message=str(exc)))
        return
    except Exception as exc:  # infra failure mid-stream — still end the protocol
        yield sse(Frame(stage=STAGE_ERROR, message=f"Nieoczekiwany błąd: {exc}"))
        return
    yield sse(_done_frame(state))


def _check_ollama() -> str:
    try:
        requests.get(f"{config.OLLAMA_BASE_URL}/api/version", timeout=2).raise_for_status()
        return "ok"
    except requests.RequestException:
        return "down"


def _check_bigquery() -> str:
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=config.BQ_PROJECT)
        client.query("SELECT 1", job_config=bigquery.QueryJobConfig(dry_run=True))
        return "ok"
    except Exception:
        return "down"


def _check_chroma() -> str:
    return "ok" if Path(config.CHROMA_DIR).exists() else "missing"


def create_app(pipeline_factory=None) -> FastAPI:
    app = FastAPI(title="taxi-chat-data API")

    @app.on_event("startup")
    def _build_pipeline():
        nonlocal pipeline_factory
        if pipeline_factory is None:
            from genai.pipeline import build_pipeline
            pipeline_factory = build_pipeline
        app.state.pipeline = pipeline_factory()

    @app.post("/chat")
    def chat(request: ChatRequest):
        return StreamingResponse(
            stream_chat(app.state.pipeline, request.question),
            media_type="text/event-stream",
        )

    @app.get("/health")
    def health():
        return {"ollama": _check_ollama(), "bigquery": _check_bigquery(),
                "chroma_index": _check_chroma()}

    dist = config.REPO_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_chat.py -v` → 6 PASS.
Full suite: `.venv/bin/pytest` → all green.
Manual: `.venv/bin/uvicorn api.main:app --port 8000` starts (needs the Chroma
index for a real pipeline — startup is lazy enough for tests either way).

- [ ] **Step 5: Polish learning note**

`docs/learn/faza-5-fastapi-sse.md` (po polsku, ~60–100 linii): czym jest SSE i
czym różni się od WebSocketów; jak działa `StreamingResponse` z generatorem;
skąd biorą się zdarzenia (LangGraph `stream_mode="updates"` — stan po każdym
węźle) i czemu adapter tylko MAPUJE, nie zmienia grafu; semantyka ramek
(completed vs started, dokładnie jedna ramka terminalna); czemu odmowa
guardraili to `done` z `refused`, a nie `error`; wzorzec `create_app(factory)`
i testowanie strumienia przez `TestClient.stream`.

- [ ] **Step 6: Feature record + story close-out**

Write `docs/features/faza-5-api-frontend/faza-5-task-1/README.md` (What was
built / Files touched / Key decisions / Verification) and update your story
`docs/tasks/faza-5-task-1.md` (Status: done, checkboxes, Dev Agent Record).

- [ ] **Step 7: Commit**

```bash
git add api/main.py tests/test_api_chat.py docs/learn/faza-5-fastapi-sse.md \
        docs/features/faza-5-api-frontend/faza-5-task-1/ docs/tasks/faza-5-task-1.md
git commit -m "feat(faza-5-task-1): FastAPI SSE chat endpoint + health over the genai pipeline"
```

---

## Task 2: `frontend/` — Vite React app per approved mockup C1 (wave 1, agent, cohort with Task 1)

**Files:**
- Create: the whole `frontend/` tree (scaffold + src per File Structure)
- Create: `docs/learn/faza-5-react-sse-front.md` (Polish learning note)
- Create: `docs/features/faza-5-api-frontend/faza-5-task-2/README.md`

**Interfaces:**
- Consumes: the SSE protocol from `api/schemas.py` (Task 0) — transcribe it
  1:1 into `src/types.ts` (below). The VISUAL source of truth is the approved
  mockup C1: `docs/superpowers/specs/assets/2026-07-18-faza-5-mockup-c1-approved.html`
  (section `.c1` — copy its tokens and layout faithfully; C2/C3 in that file
  are REJECTED alternatives).
- Produces: `npm run dev` (proxy to :8000), `npm test` (vitest), `npm run
  build` → `frontend/dist` consumed by the API's static mount (Task 3).

- [ ] **Step 1: Scaffold**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install -D vitest @testing-library/react @testing-library/jest-dom \
              @testing-library/user-event jsdom
```

Replace `vite.config.ts`:
```ts
/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/chat": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
    globals: true,
  },
});
```

`src/setupTests.ts`:
```ts
import "@testing-library/jest-dom";
```

Add to `package.json` scripts: `"test": "vitest run"`.
Delete Vite demo cruft (`App.css`, logo assets, counter demo).

- [ ] **Step 2: `src/types.ts` (protocol transcription — exact)**

```ts
// Mirrors api/schemas.py 1:1 — do not improvise fields.
export type Stage =
  | "retrieve" | "generate_sql" | "validate"
  | "execute" | "summarize" | "done" | "error";

export interface ChatResult {
  answer: string;
  sql: string;
  rows: Record<string, unknown>[];
  scanned_gb: number;
  attempts: number;
  refused: boolean;
  reason?: string;
  model: string;
}

export interface Frame {
  stage: Stage;
  attempt?: number;   // generate_sql
  ok?: boolean;       // validate
  reason?: string;    // validate, ok === false (Polish)
  message?: string;   // error (Polish)
  result?: ChatResult; // done
}
```

- [ ] **Step 3: Failing parser tests**

`src/__tests__/streamParser.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { createFrameParser } from "../api/streamParser";

const EV = (json: string) => `event: stage\ndata: ${json}\n\n`;

describe("createFrameParser", () => {
  it("parses a complete event", () => {
    const parse = createFrameParser();
    expect(parse(EV('{"stage":"retrieve"}'))).toEqual([{ stage: "retrieve" }]);
  });

  it("buffers partial chunks until the event terminator arrives", () => {
    const parse = createFrameParser();
    expect(parse('event: stage\ndata: {"stage":"exe')).toEqual([]);
    expect(parse('cute"}\n\n')).toEqual([{ stage: "execute" }]);
  });

  it("returns multiple frames from one chunk, in order", () => {
    const parse = createFrameParser();
    const frames = parse(EV('{"stage":"validate","ok":false,"reason":"Tylko SELECT."}')
      + EV('{"stage":"generate_sql","attempt":2}'));
    expect(frames.map(f => f.stage)).toEqual(["validate", "generate_sql"]);
    expect(frames[0].reason).toBe("Tylko SELECT.");
  });

  it("ignores keep-alive/comment lines without data", () => {
    const parse = createFrameParser();
    expect(parse(": ping\n\n")).toEqual([]);
  });
});
```

Run: `npm test` → FAIL (`streamParser` missing).

- [ ] **Step 4: Implement `src/api/streamParser.ts` (pure function)**

```ts
import type { Frame } from "../types";

/** Stateful chunk-to-frames parser for our SSE stream. Pure w.r.t. I/O:
 *  feed it text chunks, get complete frames back. */
export function createFrameParser(): (chunk: string) => Frame[] {
  let buffer = "";
  return (chunk: string): Frame[] => {
    buffer += chunk;
    const frames: Frame[] = [];
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = rawEvent
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("");
      if (data) frames.push(JSON.parse(data) as Frame);
    }
    return frames;
  };
}
```

Run: `npm test` → parser tests PASS.

- [ ] **Step 5: `src/api/chatClient.ts` + failing hook tests**

`src/api/chatClient.ts`:
```ts
export async function* streamChat(question: string, signal?: AbortSignal) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Serwer odpowiedział błędem (${response.status}).`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}
```

`src/__tests__/useChatStream.test.tsx`:
```tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChatStream } from "../hooks/useChatStream";

function sseResponse(...events: string[]) {
  const body = new ReadableStream({
    start(controller) {
      for (const e of events) controller.enqueue(new TextEncoder().encode(e));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

const EV = (json: string) => `event: stage\ndata: ${json}\n\n`;

describe("useChatStream", () => {
  it("collects stage frames and the final result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(
      EV('{"stage":"retrieve"}'),
      EV('{"stage":"generate_sql","attempt":1}'),
      EV('{"stage":"validate","ok":true}'),
      EV('{"stage":"execute"}'),
      EV('{"stage":"summarize"}'),
      EV('{"stage":"done","result":{"answer":"Pięć.","sql":"SELECT 1","rows":[],' +
         '"scanned_gb":0.01,"attempts":1,"refused":false,"model":"gemma4"}}'),
    )));
    const { result } = renderHook(() => useChatStream());
    act(() => { void result.current.ask("Ile kursów?"); });
    await waitFor(() => expect(result.current.result?.answer).toBe("Pięć."));
    expect(result.current.frames.map(f => f.stage)).toEqual(
      ["retrieve", "generate_sql", "validate", "execute", "summarize"]);
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("exposes a terminal error frame as error state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(
      EV('{"stage":"retrieve"}'),
      EV('{"stage":"error","message":"Ollama nie odpowiada"}'),
    )));
    const { result } = renderHook(() => useChatStream());
    act(() => { void result.current.ask("Ile?"); });
    await waitFor(() => expect(result.current.error).toBe("Ollama nie odpowiada"));
    expect(result.current.result).toBeNull();
  });
});
```

Run: `npm test` → FAIL (`useChatStream` missing).

- [ ] **Step 6: Implement `src/hooks/useChatStream.ts` (ALL the logic)**

```ts
import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/chatClient";
import { createFrameParser } from "../api/streamParser";
import type { ChatResult, Frame } from "../types";

export interface ChatStream {
  frames: Frame[];              // non-terminal frames, in arrival order
  result: ChatResult | null;    // set by the `done` frame
  error: string | null;         // set by the `error` frame or transport failure
  running: boolean;
  ask: (question: string) => Promise<void>;
}

export function useChatStream(): ChatStream {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [result, setResult] = useState<ChatResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const ask = useCallback(async (question: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setFrames([]); setResult(null); setError(null); setRunning(true);
    const parse = createFrameParser();
    try {
      for await (const chunk of streamChat(question, controller.signal)) {
        for (const frame of parse(chunk)) {
          if (frame.stage === "done") setResult(frame.result ?? null);
          else if (frame.stage === "error") setError(frame.message ?? "Nieznany błąd");
          else setFrames((prev) => [...prev, frame]);
        }
      }
    } catch (exc) {
      if (!controller.signal.aborted) {
        setError(exc instanceof Error ? exc.message : "Błąd połączenia.");
      }
    } finally {
      setRunning(false);
    }
  }, []);

  return { frames, result, error, running, ask };
}
```

Also `src/hooks/useHealth.ts`:
```ts
import { useEffect, useState } from "react";

export interface Health { ollama: string; bigquery: string; chroma_index: string }

export function useHealth(): Health | null {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    fetch("/health").then(r => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);
  return health;
}
```

Run: `npm test` → hook tests PASS.

- [ ] **Step 7: Failing component tests**

`src/__tests__/StageTimeline.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageTimeline } from "../components/StageTimeline";

describe("StageTimeline (mockup C1)", () => {
  it("renders OK status for successful validate and the reason for rejection", () => {
    render(<StageTimeline frames={[
      { stage: "retrieve" },
      { stage: "generate_sql", attempt: 1 },
      { stage: "validate", ok: false, reason: "Tabela raw.trips jest poza dozwolonymi zbiorami danych" },
      { stage: "generate_sql", attempt: 2 },
      { stage: "validate", ok: true },
    ]} running={false} />);
    expect(screen.getByText("ODRZUCONE")).toBeInTheDocument();
    expect(screen.getByText(/raw\.trips/)).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("SQL — próba 2")).toBeInTheDocument();
  });

  it("marks the last row as pending while running", () => {
    render(<StageTimeline frames={[{ stage: "retrieve" }]} running={true} />);
    expect(screen.getByText("…")).toBeInTheDocument();
  });
});
```

`src/__tests__/ResultCard.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultCard } from "../components/ResultCard";

const RESULT = {
  answer: "Średni napiwek wynosił 4,16 USD.", sql: "SELECT 1", rows: [{ avg_tip: 4.16 }],
  scanned_gb: 0.048, attempts: 2, refused: false, model: "gemma4:latest",
};

describe("ResultCard", () => {
  it("shows the answer, chips and the rows table", () => {
    render(<ResultCard result={RESULT} />);
    expect(screen.getByText(/4,16 USD/)).toBeInTheDocument();
    expect(screen.getByText("2 próby")).toBeInTheDocument();
    expect(screen.getByText("0.0480 GB")).toBeInTheDocument();
    expect(screen.getByText("avg_tip")).toBeInTheDocument();
  });

  it("renders a refusal without a rows table", () => {
    render(<ResultCard result={{ ...RESULT, refused: true, rows: [],
      reason: "Tylko SELECT.", answer: "Nie umiem bezpiecznie odpowiedzieć." }} />);
    expect(screen.getByText(/Nie umiem/)).toBeInTheDocument();
    expect(screen.getByText(/Tylko SELECT/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
```

Run: `npm test` → FAIL (components missing).

- [ ] **Step 8: Implement presentational components (props in, JSX out — NO logic)**

`src/components/StageTimeline.tsx` — the C1 signature. Faithful to the
approved mockup: yellow route line, green station dots, dotted leader,
monospace status on the right, red rejected row with the reason beneath:
```tsx
import type { Frame } from "../types";

const LABELS: Record<string, (f: Frame) => string> = {
  retrieve: () => "Kontekst schematu",
  generate_sql: (f) => `SQL — próba ${f.attempt ?? 1}`,
  validate: () => "Guardraile",
  execute: () => "BigQuery — wykonanie",
  summarize: () => "Piszę odpowiedź",
};

export function StageTimeline({ frames, running }: { frames: Frame[]; running: boolean }) {
  return (
    <ol className="timeline">
      {frames.map((frame, i) => {
        const rejected = frame.stage === "validate" && frame.ok === false;
        return (
          <li key={i} className={rejected ? "station err" : "station"}>
            <span className="lbl">{LABELS[frame.stage]?.(frame) ?? frame.stage}</span>
            <span className="dots" />
            <span className="st">{rejected ? "ODRZUCONE" : "OK"}</span>
            {rejected && frame.reason ? <span className="why">{frame.reason}</span> : null}
          </li>
        );
      })}
      {running ? (
        <li className="station pending">
          <span className="lbl">…</span>
        </li>
      ) : null}
    </ol>
  );
}
```

`src/components/QuestionForm.tsx`:
```tsx
import { useState } from "react";

export function QuestionForm({ disabled, onAsk }:
  { disabled: boolean; onAsk: (question: string) => void }) {
  const [question, setQuestion] = useState("");
  return (
    <form
      className="ask"
      onSubmit={(e) => { e.preventDefault(); if (question.trim()) onAsk(question.trim()); }}
    >
      <input
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Zadaj pytanie o przejazdy taxi…"
        aria-label="Pytanie"
      />
      <button type="submit" disabled={disabled || !question.trim()}>Zapytaj</button>
    </form>
  );
}
```

`src/components/ResultCard.tsx`:
```tsx
import type { ChatResult } from "../types";

export function ResultCard({ result }: { result: ChatResult }) {
  const columns = result.rows.length ? Object.keys(result.rows[0]) : [];
  return (
    <section className="result">
      <header className="rhead">Wynik kursu</header>
      <div className="rbody">
        <p className="ans">{result.answer}</p>
        {result.refused && result.reason ? <p className="refusal">{result.reason}</p> : null}
        <div className="chips">
          <span className="chip y">{result.attempts} {result.attempts === 1 ? "próba" : "próby"}</span>
          <span className="chip">{result.scanned_gb.toFixed(4)} GB</span>
          <span className="chip">{result.model.split(":")[0]}</span>
        </div>
        {result.sql ? (
          <details>
            <summary>Użyty SQL</summary>
            <pre>{result.sql}</pre>
          </details>
        ) : null}
        {columns.length ? (
          <table>
            <thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {result.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>{columns.map(c => <td key={c}>{String(row[c])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
```

`src/components/HealthBar.tsx`:
```tsx
import type { Health } from "../hooks/useHealth";

const LABEL: Record<string, string> = { ollama: "Ollama", bigquery: "BigQuery", chroma_index: "Indeks" };

export function HealthBar({ health }: { health: Health | null }) {
  if (!health) return <small className="health">Sprawdzam status…</small>;
  return (
    <small className="health">
      {Object.entries(health).map(([key, value]) => (
        <span key={key}>{LABEL[key]} <b className={value === "ok" ? "up" : "down"}>{value.toUpperCase()}</b> </span>
      ))}
    </small>
  );
}
```

`src/app/App.tsx`:
```tsx
import { HealthBar } from "../components/HealthBar";
import { QuestionForm } from "../components/QuestionForm";
import { ResultCard } from "../components/ResultCard";
import { StageTimeline } from "../components/StageTimeline";
import { useChatStream } from "../hooks/useChatStream";
import { useHealth } from "../hooks/useHealth";
import "./styles.css";

export default function App() {
  const { frames, result, error, running, ask } = useChatStream();
  const health = useHealth();
  return (
    <main className="screen">
      <header className="signbar">
        <span className="bullet">M</span>
        <h1>Chat with data — NYC Taxi</h1>
        <HealthBar health={health} />
      </header>
      <div className="inner">
        <QuestionForm disabled={running} onAsk={ask} />
        {frames.length || running ? <StageTimeline frames={frames} running={running} /> : null}
        {error ? <p className="error" role="alert">{error}</p> : null}
        {result ? <ResultCard result={result} /> : null}
      </div>
    </main>
  );
}
```

`src/app/styles.css` — transcribe the C1 mockup styles (binding tokens):
```css
:root {
  --ink: #111111; --paper: #ffffff; --line: #fccc0a;
  --ok: #00933c; --err: #d0021b;
  --sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 var(--sans); }
.screen { min-height: 100vh; }
.signbar { background: var(--ink); color: #fff; padding: 14px 22px; display: flex; align-items: center; gap: 12px; }
.signbar h1 { margin: 0; font-size: 1.05rem; font-weight: 700; }
.bullet { width: 30px; height: 30px; border-radius: 50%; background: var(--line); color: var(--ink);
          display: inline-flex; align-items: center; justify-content: center; font-weight: 700; flex: none; }
.health { margin-left: auto; font-size: .72rem; color: #99a; }
.health .up { color: #7ed488; } .health .down { color: #ff8484; }
.inner { max-width: 620px; margin: 0 auto; padding: 22px 22px 60px; }
.ask { display: flex; border: 2px solid var(--ink); }
.ask input { flex: 1; border: 0; padding: 12px 14px; font: 1rem var(--sans); }
.ask input:focus-visible, .ask button:focus-visible { outline: 3px solid var(--line); outline-offset: -3px; }
.ask button { border: 0; background: var(--line); color: var(--ink); font-weight: 700; padding: 12px 20px; cursor: pointer; }
.ask button:disabled { opacity: .5; cursor: default; }
.timeline { list-style: none; margin: 26px 0 6px; padding: 0 0 0 34px; position: relative;
            display: flex; flex-direction: column; gap: 15px; }
.timeline::before { content: ""; position: absolute; left: 10px; top: 4px; bottom: 4px;
                    width: 8px; background: var(--line); border-radius: 4px; }
.station { position: relative; font-size: .95rem; display: flex; align-items: baseline; gap: 8px; }
.station::before { content: ""; position: absolute; left: -30px; top: .28em; width: 12px; height: 12px;
                   border-radius: 50%; background: var(--ok); border: 3px solid var(--ok); }
.station.err::before { background: var(--err); border-color: var(--err); }
.station.err { margin-bottom: 16px; }
.station.pending::before { background: #fff; border-color: #bbb; }
.station .dots { flex: 1; border-bottom: 1px dotted #bbb; transform: translateY(-4px); }
.station .st { font: 700 .75rem var(--mono); color: var(--ok); letter-spacing: .08em; }
.station.err .st { color: var(--err); }
.station .why { position: absolute; top: 1.35em; left: 0; font-size: .78rem; color: var(--err); }
.error { border: 2px solid var(--err); color: var(--err); padding: 12px 14px; font-weight: 700; }
.result { border: 2px solid var(--ink); margin-top: 22px; }
.rhead { background: var(--ink); color: #fff; padding: 8px 14px; font-size: .78rem;
         letter-spacing: .12em; text-transform: uppercase; }
.rbody { padding: 16px 18px; }
.ans { font-size: 1.3rem; margin: 0 0 12px; line-height: 1.4; }
.refusal { color: var(--err); font-size: .9rem; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.chip { border: 1.5px solid var(--ink); border-radius: 999px; padding: 2px 12px; font-size: .75rem; font-weight: 700; }
.chip.y { background: var(--line); border-color: var(--line); }
details summary { cursor: pointer; font-size: .8rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
pre { background: #f4f4f4; padding: 12px; overflow-x: auto; font: .8rem/1.5 var(--mono); }
table { width: 100%; font-size: .85rem; margin-top: 8px; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { text-align: left; background: var(--ink); color: #fff; padding: 5px 8px; font-size: .75rem; letter-spacing: .08em; }
td { padding: 6px 8px; border-bottom: 1px solid #ddd; font-family: var(--mono); }
@media (prefers-reduced-motion: no-preference) {
  .station { animation: arrive .2s ease-out; }
  @keyframes arrive { from { opacity: 0; transform: translateY(4px); } }
}
```

Update `index.html` title to `Chat with data — NYC Taxi` and `lang="pl"`;
`src/main.tsx` renders `<App />`.

- [ ] **Step 9: Run all frontend tests + build**

Run: `npm test` → parser 4, hook 2, StageTimeline 2, ResultCard 2 — all PASS.
Run: `npm run build` → `dist/` builds clean. `npm run dev` renders the screen
(manual sanity — API may be absent; health shows "Sprawdzam status…").

- [ ] **Step 10: Polish learning note**

`docs/learn/faza-5-react-sse-front.md` (po polsku, ~60–100 linii): czytanie
strumienia przez `fetch` + `ReadableStream` (i czemu nie `EventSource` przy
POST); wzorzec czystego parsera (bufor, granica `\n\n`, częściowe chunki);
podział prezentacja/logika (hook jako właściciel cyklu życia żądania,
komponenty bez logiki); AbortController przy ponownym pytaniu; testowanie
strumienia w vitest przez sztuczny `Response(ReadableStream)`.

- [ ] **Step 11: Feature record + story close-out**

`docs/features/faza-5-api-frontend/faza-5-task-2/README.md` + update
`docs/tasks/faza-5-task-2.md` (Status: done, checkboxes, Dev Agent Record).

- [ ] **Step 12: Commit**

```bash
git add frontend/ docs/learn/faza-5-react-sse-front.md \
        docs/features/faza-5-api-frontend/faza-5-task-2/ docs/tasks/faza-5-task-2.md
git commit -m "feat(faza-5-task-2): Vite React chat screen per approved mockup C1"
```

---

## Task 3: Live run, single-port demo, docs, PR (in-session, after Tasks 1–2 merge)

**Files:**
- Modify: `README.md` (Faza 5 checkbox + "Chat UI" section)
- Create: `docs/features/faza-5-api-frontend/faza-5-task-3/README.md`
- Modify: `docs/tasks/faza-5-task-3.md` (story close-out)

- [ ] **Step 1: Build the front and start the API**

```bash
cd frontend && npm ci && npm run build && cd ..
.venv/bin/uvicorn api.main:app --port 8000
```
Open `http://localhost:8000` — the C1 screen loads from `frontend/dist`;
`/health` shows all three deps `ok` (Ollama running, ADC valid, index built).

- [ ] **Step 2: Live demo (evidence for the PR)**

Ask: `Jaki był średni napiwek przy płatności kartą?` — watch stages stream;
confirm answer + SQL + rows + GB. Ask a question that triggers a guardrail
retry (e.g. one that tempts the model toward `raw.trips`) and screenshot the
red ODRZUCONE row. Ask `Usuń wszystkie dane` — refusal path renders.

- [ ] **Step 3: Suites green**

`.venv/bin/pytest` (unit) and `cd frontend && npm test` — all green.

- [ ] **Step 4: README + records**

README: check Faza 5, add "Chat UI (Faza 5)" section (build + uvicorn + one
URL; SSE protocol pointer to `api/schemas.py`). Feature record for task-3;
story close-out.

- [ ] **Step 5: Commit, push, PR**

```bash
git add README.md docs/
git commit -m "docs: README chat UI section + Faza 5 verification record"
git push -u origin feat/faza-5-api-frontend
gh pr create --base master --title "Faza 5: chat UI — FastAPI SSE + React (mockup C1)" \
  --body "$(cat <<'EOF'
## What
Product layer over the Faza 3 pipeline: FastAPI `POST /chat` streams pipeline
stages over SSE (LangGraph `stream()` adapter — no genai/ changes), `GET
/health` reports Ollama/BigQuery/Chroma, and a Vite+React+TS single-screen app
(owner-approved mockup C1 "Linia M") renders the live stage timeline with
guardrail rejections, then the answer, SQL, rows and GB scanned. Senior front
conventions: pure stream parser, all logic in `useChatStream`, presentational
components only.

## Evidence
(screenshots: live timeline with a red ODRZUCONE row + final result card;
paste /health output)

## Tests
- Python: pytest all green (SSE frame sequences incl. retry/refusal/error, no live services)
- Frontend: vitest all green (parser chunking, hook stream lifecycle, C1 components)
- Live: full demo through http://localhost:8000 (single port, static dist)
EOF
)"
```

---

## Harness execution notes (operator)

- Task 0 in-session FIRST; commit + push `feat/faza-5-api-frontend`; bump
  `DEFAULT_BASE` in the harness profile.
- Wave 1: `launch-task.sh --project taxi-chat-data --autonomous --names <a>,<b>
  faza-5-task-1 faza-5-task-2` — stories declare the cohort; intent-sync on
  protocol semantics before any code.
- Task-2 agent needs Node ≥20 (`nvm use 22`); everything Node-side stays in
  `frontend/`.
- Task 3 in-session after both PRs merge into the phase branch.
