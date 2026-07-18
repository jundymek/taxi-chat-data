# Faza 5 / Task 2: React chat screen (approved mockup C1)

Status: done
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
- [x] Intent-sync with the API agent (see Coordination) BEFORE any code
- [x] Scaffold Vite+React+TS + vitest (plan Step 1)
- [x] types.ts + failing parser tests → streamParser (pure)
- [x] chatClient + failing hook tests → useChatStream
- [x] Failing component tests → StageTimeline/QuestionForm/ResultCard/HealthBar + styles.css (C1)
- [x] All tests green + build clean
- [x] Polish learning note + feature record
- [x] Update this story + commit

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
claude-opus-4-8[1m] (Claude Opus 4.8, 1M context), autonomous mode.

### Debug Log References
- `pnpm build` initially failed with a deep Vite type conflict: vitest 2.x pins
  Vite 5, but the scaffold installed Vite 8, so `vitest/config`'s `defineConfig`
  typed the config against Vite 5 while `@tailwindcss/vite`/`@vitejs/plugin-react`
  were Vite 8 → incompatible `PluginOption`/`ProxyOptions`. Fixed by upgrading
  vitest to v4 (Vite-8-compatible peer). Tests + build green after.
- Harness intent-gate mis-fired once because a persistent `cd frontend` drifted
  the shell CWD; the gate checks `$CWD/intent.synced` (marker is at the worktree
  root). Resolved by keeping the shell at the worktree root and wrapping
  frontend commands in `( cd frontend && … )` subshells.

### Completion Notes List
- Cohort intent-sync with the API agent (faza-5-task-1) completed BEFORE any
  code; both intents declared identical SSE semantics (one terminal frame
  `done` XOR `error`; guardrail refusal = `done` with `refused:true`, not
  `error`; nulls omitted on the wire). `types.ts` mirrors `api/schemas.py` 1:1.
- TDD per the plan: parser → hook → components, each with failing tests first.
  Final suite: **15 passed** (parser 4, chatClient 2, hook 3, QuestionForm 2,
  StageTimeline 2, ResultCard 2). `pnpm build` clean.
- Codex review (3 findings across two rounds, all fixed with regression tests):
  (P1) `useChatStream` cleared `running` from a superseded request — now all
  state mutations are guarded on the current AbortController (`isCurrent`); (P2)
  `chatClient` didn't flush the `TextDecoder` at EOF, risking a truncated final
  frame on a split multibyte char — now flushed; (P2) `QuestionForm` submit
  ignored `disabled`, so Enter could restart an in-flight request — now guarded.
- HealthBar UX: `useHealth` now distinguishes `loading` / `ready` / `error`, so
  running the front without the API shows "Status niedostępny" rather than a
  permanent "Sprawdzam status…".
- Deviations from the plan doc (all recorded in `DECISIONS.md`, operator-driven):
  React 19 + Vite 8 + Vitest 4 (newest libs) instead of "React 18"; **pnpm**
  instead of npm; **Tailwind v4 + a custom CSS layer for the metro timeline**
  instead of a single hand-written `styles.css`; component props as a named
  `*Props` interface at file top. Binding C1 visual tokens are unchanged and
  declared once in Tailwind `@theme`.
- Full streaming end-to-end (live timeline, ODRZUCONE row, refusal) requires the
  API and is exercised in Task 3; see `docs/features/.../faza-5-task-2/MANUAL_TESTING.md`.

### File List
NEW (all under `frontend/`):
- `package.json`, `pnpm-lock.yaml`, `vite.config.ts`, `index.html`
- `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` (from scaffold)
- `src/main.tsx`, `src/setupTests.ts`, `src/types.ts`
- `src/api/streamParser.ts`, `src/api/chatClient.ts`
- `src/hooks/useChatStream.ts`, `src/hooks/useHealth.ts`
- `src/components/StageTimeline.tsx`, `src/components/QuestionForm.tsx`,
  `src/components/ResultCard.tsx`, `src/components/HealthBar.tsx`
- `src/app/App.tsx`, `src/app/styles.css`
- `src/__tests__/streamParser.test.ts`, `src/__tests__/chatClient.test.ts`,
  `src/__tests__/useChatStream.test.tsx`, `src/__tests__/QuestionForm.test.tsx`,
  `src/__tests__/StageTimeline.test.tsx`, `src/__tests__/ResultCard.test.tsx`

NEW (docs):
- `docs/learn/faza-5-react-sse-front.md`
- `docs/features/faza-5-api-frontend/faza-5-task-2/README.md`
- `docs/features/faza-5-api-frontend/faza-5-task-2/MANUAL_TESTING.md`

UPDATE:
- `docs/tasks/faza-5-task-2.md` (this story)
