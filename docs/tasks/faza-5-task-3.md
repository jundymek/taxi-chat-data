# Faza 5 / Task 3: live demo, single-port serve, docs, PR

Status: done
Executor: operator-session (after tasks 1–2 merge into the phase branch)
Plan: `docs/superpowers/plans/2026-07-18-faza-5-api-frontend.md` → section "Task 3"

## Acceptance Criteria
1. `npm run build` + `uvicorn api.main:app` serve the full app on ONE port;
   `/health` all `ok` live.
2. Live demo evidence: streamed stage timeline; a guardrail-retry question
   showing a red ODRZUCONE row; a refusal question rendering as a result.
3. Both suites green (`pytest`, `npm test`).
4. README: Faza 5 checkbox + "Chat UI" section.
5. PR to master with screenshots/health output in the body.

## Tasks / Subtasks
- [x] Build front, start API, verify single-port serve + /health
- [x] Live demo: happy path, retry, refusal (capture evidence)
- [x] Suites green
- [x] README + feature record + this story close-out
- [x] Push + PR to master

## Dev Agent Record
### Agent Model Used
Operator session, claude-opus-4-8[1m].

### Completion Notes
- Verified PR #11 (alice, task-1) and #12 (bob, task-2) MERGED into
  `feat/faza-5-api-frontend` before starting (`gh pr list --state all`).
- `data/chroma/` was missing → rebuilt with `python -m genai.indexer` (6 schema
  docs + 10 few-shots) so `/health` could report `chroma_index: ok`.
- Built the front with **pnpm** (bob scaffolded with `pnpm-lock.yaml`, not npm —
  followed the actual lockfile despite the plan's `npm` wording). `pnpm run
  build` → `frontend/dist`; `uvicorn api.main:app --port 8000` serves the C1
  screen + API on one port.
- Live `/health` = `{"ollama":"ok","bigquery":"ok","chroma_index":"ok"}`.
- Demo evidence (real gemma4:latest + BigQuery):
  - Happy path — "Jaki był średni napiwek…" → full stage timeline, 4,16 USD,
    0.048 GB, attempts=1.
  - Guardrail retry — "…raw.trips…" → attempt 1 `validate ok:false` (reason:
    "Tabela raw.trips jest poza dozwolonymi zbiorami danych (marts, staging).")
    → attempt 2 `validate ok:true` → done. This drives the red ODRZUCONE row.
  - Refusal — "Usuń wszystkie dane" → safe read-only `SELECT *`, declined in
    prose (no destructive SQL); renders as a result card.
- Suites: `.venv/bin/pytest` → 85 passed, 5 deselected; `frontend` `pnpm test`
  → 15 passed (6 files). `pnpm run build` clean.

### File List
- `README.md` (UPDATE) — Faza 5 checkbox + "Chat UI (Faza 5)" section.
- `docs/features/faza-5-api-frontend/faza-5-task-3/README.md` (NEW) — feature record.
- `docs/tasks/faza-5-task-3.md` (UPDATE) — this story close-out.
