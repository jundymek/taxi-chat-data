# Manual testing — Faza 5 / Task 2 (React chat screen C1)

The component/hook/parser behavior is covered by 10 vitest specs. This document
lists the in-browser checks. The full streaming flow needs the API
(faza-5-task-1) running on `:8000`; that end-to-end demo is Task 3. What can be
verified in isolation is listed under "Without the API".

## Setup
```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:3002 (falls back to next free port)
```
Full flow (Task 3): build the front and serve it from the API on one port:
```bash
cd frontend && pnpm build && cd ..
.venv/bin/uvicorn api.main:app --port 8000   # open http://localhost:8000
```

## Without the API (this task, standalone)
1. **Screen renders (C1 identity):** black sign bar, yellow round "M" bullet,
   title "Chat with data — NYC Taxi", ask box with a 2px ink border and a flush
   yellow "Zapytaj" button.
2. **HealthBar:** shows "Sprawdzam status…" (API absent) — no crash.
3. **Empty question:** the "Zapytaj" button is disabled until non-whitespace
   text is entered.
4. **Transport error path:** type a question and submit with no API running →
   after the failed fetch, a red bordered error banner appears
   (`role="alert"`), and `running` clears (button re-enabled).

## With the API (Task 3, end-to-end)
5. **Live timeline:** ask "Jaki był średni napiwek przy płatności kartą?" →
   stations stream in order (Kontekst schematu → SQL — próba 1 → Guardraile →
   BigQuery — wykonanie → Piszę odpowiedź), each with a green dot and monospace
   `OK`; a pending "…" row shows while running.
6. **Guardrail rejection (C1 signature):** ask something that tempts the model
   toward `raw.trips` → a red station with `ODRZUCONE` and the Polish reason
   under the row, followed by a retry (`SQL — próba 2`). A **multi-line** reason
   must push the next station down (flow layout), not overlap it.
7. **Result card:** answer in large type, chips (`2 próby`, `0.0480 GB`,
   `gemma4`), collapsible "Użyty SQL", rows table.
8. **Refusal:** ask "Usuń wszystkie dane" → result card with the refusal answer
   and reason, **no** rows table (not the error banner).

## Accessibility checks
- Input has `aria-label="Pytanie"`; the error banner has `role="alert"`.
- Keyboard: Tab reaches input → button; Enter submits the form; the disabled
  button is skipped appropriately.
- Focus-visible: input and button show a yellow/ink focus outline.
- `prefers-reduced-motion`: the station "arrive" animation is gated behind
  `@media (prefers-reduced-motion: no-preference)`.
- Color is not the only signal: OK / ODRZUCONE carry text labels, not just
  green/red dots.
