# Faza 5 / Task 3: live demo, single-port serve, docs, PR

Status: planned
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
- [ ] Build front, start API, verify single-port serve + /health
- [ ] Live demo: happy path, retry, refusal (capture evidence)
- [ ] Suites green
- [ ] README + feature record + this story close-out
- [ ] Push + PR to master

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
