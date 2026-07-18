# Faza 5 / Task 2: React chat screen (approved mockup C1)

## What was built
A Vite + React 19 + TypeScript single-screen SPA in `frontend/` that renders the
OWNER-APPROVED mockup **C1** ("Linia M"): the live SSE stage timeline (yellow
route line, green station dots + `OK`, red `ODRZUCONE` with the guardrail reason
beneath the row), then the answer card (chips: attempts / GB scanned / model, a
collapsible SQL block, rows table). It consumes the Faza 5 SSE protocol over
`fetch` + `ReadableStream` with a pure stream parser; all stateful logic lives
in the `useChatStream` hook and every component is presentational.

## Files touched
- `frontend/package.json`, `frontend/pnpm-lock.yaml` (NEW) — pnpm project, React
  19, Vite 8, Vitest 4, Tailwind v4, Testing Library.
- `frontend/vite.config.ts` (NEW) — react + `@tailwindcss/vite` plugins, dev
  proxy `/chat` + `/health` → `:8000`, port 3002, vitest (jsdom) config.
- `frontend/index.html` (NEW) — `lang="pl"`, title "Chat with data — NYC Taxi".
- `frontend/src/main.tsx` (NEW) — mounts `<App />`, imports `app/styles.css`.
- `frontend/src/setupTests.ts` (NEW) — registers jest-dom matchers on vitest.
- `frontend/src/types.ts` (NEW) — protocol transcribed 1:1 from `api/schemas.py`.
- `frontend/src/api/streamParser.ts` (NEW) — pure `createFrameParser` (buffer,
  `\n\n` boundary, `data:`-only, ignores keep-alives).
- `frontend/src/api/chatClient.ts` (NEW) — `streamChat` async generator over
  `fetch`/`ReadableStream`.
- `frontend/src/hooks/useChatStream.ts` (NEW) — owns the request lifecycle:
  frames / result / error / running, AbortController on re-ask.
- `frontend/src/hooks/useHealth.ts` (NEW) — one-shot `/health` fetch, exposes a
  `loading | ready | error` state so the bar shows "Status niedostępny" when the
  API is unreachable instead of a permanent "Sprawdzam status…".
- `frontend/src/components/{StageTimeline,QuestionForm,ResultCard,HealthBar}.tsx`
  (NEW) — presentational, each with a named `*Props` interface at file top.
- `frontend/src/app/App.tsx` (NEW) — composition only.
- `frontend/src/app/styles.css` (NEW) — Tailwind v4 `@theme` C1 tokens + custom
  CSS layer for the metro timeline.
- `frontend/src/__tests__/{streamParser,useChatStream,StageTimeline,ResultCard}`
  (NEW) — 10 tests.
- `docs/learn/faza-5-react-sse-front.md` (NEW) — Polish learning note.
- `docs/tasks/faza-5-task-2.md` (UPDATE) — story close-out.

## Key decisions
Full log in `DECISIONS.md` (worktree). Highlights (operator-flagged):
- **Styling = Tailwind v4 + custom CSS for the timeline** (operator call this
  session). Binding C1 tokens declared once in Tailwind `@theme`; the metro
  timeline's pseudo-element route line / dots / dotted leader stay in a small
  plain-CSS layer for pixel fidelity to the approved mockup.
- **React 19 + Vite 8 + Vitest 4** (newest, operator: "biblioteki maja byc
  najnowsze"). The plan doc said "React 18"; the current Vite scaffold is React
  19 and the plan's code runs unchanged on it. Vitest upgraded to 4 so its Vite
  peer matches Vite 8 (the v2 default pins Vite 5 and its config types clash).
- **pnpm** as package manager (operator call) instead of the plan's npm.
- **Props as a named interface at the top of each component file** (operator
  convention) rather than inline destructured types.
- **Protocol mirrored, never changed** — `types.ts` transcribes `api/schemas.py`
  1:1; cohort intent-sync with the API agent (faza-5-task-1) confirmed the
  frame semantics (one terminal frame `done` XOR `error`; refusal = `done` with
  `refused:true`, not `error`) before any code.

## Verification
- `cd frontend && pnpm test` → **15 passed** (parser 4, chatClient 2, hook 3,
  QuestionForm 2, StageTimeline 2, ResultCard 2); no live services touched
  (fetch stubbed, streams faked).
- Codex review (base `feat/faza-5-api-frontend`), 3 findings across two rounds,
  all fixed with regression tests: (P1) superseded-request race in
  `useChatStream` (guard state mutations on the current controller); (P2)
  `TextDecoder` not flushed at EOF in `chatClient` (flush on `done`); (P2)
  `QuestionForm` submit ignored `disabled`, letting Enter restart an in-flight
  request (guard `onSubmit` on `disabled`).
- `cd frontend && pnpm build` → clean (`tsc -b && vite build`; CSS ~9.8 kB
  gzip 3 kB, JS ~196 kB gzip 62 kB).
- Full end-to-end through the running API (streaming timeline, guardrail
  ODRZUCONE row, refusal path) is exercised in Task 3 after the API merges.
  See `MANUAL_TESTING.md`.
