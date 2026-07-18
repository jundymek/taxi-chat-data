# Faza 5 / Task 2: React chat screen (approved mockup C1)

Status: planned
Executor: agent (wave 1, cohort with faza-5-task-1)
Plan: `docs/superpowers/plans/2026-07-18-faza-5-api-frontend.md` → section
"Task 2" (technical source of truth — complete code + TDD steps; read it AND
"Global Constraints" first)

## Acceptance Criteria
1. `cd frontend && npm test` → all vitest suites pass (parser 4, hook 2,
   StageTimeline 2, ResultCard 2); `npm run build` clean.
2. Visual fidelity to the OWNER-APPROVED mockup **C1** in
   `docs/superpowers/specs/assets/2026-07-18-faza-5-mockup-c1-approved.html`
   (section `.c1` only; C2/C3 are rejected). Binding tokens: `#FCCC0A` route
   line, `#00933C` green station dots + `OK`, `#D0021B` rejection + reason
   under the row, black station-sign bars, 2px ink borders.
3. Senior conventions: presentational components with NO logic; ALL stateful
   logic in `useChatStream`; `streamParser` pure and unit-tested; flat layout
   (`app/ components/ hooks/ api/ types.ts`) — no `features/` indirection.
4. UI copy in Polish; code/comments in English.
5. `docs/learn/faza-5-react-sse-front.md` + feature record written.
6. THIS story updated before PR (Status: done, checkboxes, Dev Agent Record).

## Tasks / Subtasks
- [ ] Intent-sync with the API agent (see Coordination) BEFORE any code
- [ ] Scaffold Vite+React+TS + vitest (plan Step 1)
- [ ] types.ts + failing parser tests → streamParser (pure)
- [ ] chatClient + failing hook tests → useChatStream
- [ ] Failing component tests → StageTimeline/QuestionForm/ResultCard/HealthBar + styles.css (C1)
- [ ] All tests green + build clean
- [ ] Polish learning note + feature record
- [ ] Update this story + commit

## Coordination
- **Cohort with faza-5-task-1 (API) — REQUIRED:** configure the cohort, write
  `intent.md` declaring your reading of the SSE protocol (you parse ONLY
  `data:` lines, buffer on `\n\n`, treat `done`/`error` as terminal, render
  refusal as a result not an error), run intent-sync (mutual acks). Protocol
  doubts → `agent-msg.sh send <peer> ...`, never guess. If you finish first,
  `agent-wait.sh --background <peer>:pr-opened` and react to their PR.
- Node ≥20 (`nvm use 22`). You own the ENTIRE `frontend/` tree (incl.
  package.json + lockfile). Do NOT touch `api/`, `genai/`, `requirements.txt`.

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
