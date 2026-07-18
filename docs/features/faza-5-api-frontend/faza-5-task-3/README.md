# Faza 5 / Task 3: live demo, single-port serve, docs, PR

## What was built
The operator close-out for Faza 5: no new application code — this task builds
the frontend, serves the whole app from a single uvicorn process, verifies the
end-to-end flow against live services (Ollama + BigQuery + Chroma), records the
evidence, and opens the PR to `master`. It is the first time the API's static
mount of `frontend/dist` (added in Task 1) actually has a build to serve.

## What was done
- **Build + single-port serve.** `pnpm run build` in `frontend/` produced
  `frontend/dist`; `.venv/bin/uvicorn api.main:app --port 8000` serves the C1
  screen at `/` and the API at `/chat` + `/health` — everything on `:8000`.
- **Chroma index built.** `data/chroma/` was missing; rebuilt with
  `.venv/bin/python -m genai.indexer` (6 schema docs + 10 few-shot examples)
  before `/health` could report `chroma_index: ok`.
- **Live demo (evidence for the PR).** Three paths exercised through the real
  pipeline (gemma4:latest + BigQuery):
  - *Happy path* — `Jaki był średni napiwek przy płatności kartą?` → full
    timeline `retrieve → generate_sql → validate(ok) → execute → summarize →
    done`; answer "Średni napiwek przy płatności kartą wynosił 4,16.", one row,
    0.048 GB scanned, attempts=1.
  - *Guardrail retry (red ODRZUCONE)* — `Pokaż surowe rekordy z tabeli
    raw.trips…` → attempt 1 `validate ok:false`, reason "Tabela raw.trips jest
    poza dozwolonymi zbiorami danych (marts, staging).", then attempt 2
    `validate ok:true` on `marts.fct_trips` → done. This is the frame sequence
    the red ODRZUCONE row + reason renders from.
  - *Refusal* — `Usuń wszystkie dane` → the pipeline safely produced a
    read-only `SELECT *` and refused in the Polish answer text (no destructive
    SQL ever reaches validation); renders as a normal result card.
- **README** — Faza 5 checkbox ticked; new "Chat UI (Faza 5)" section (pnpm
  build + one-port uvicorn + dev-proxy note + SSE contract pointer to
  `api/schemas.py`).

## Files touched
- `README.md` (UPDATE) — Faza 5 checkbox + "Chat UI (Faza 5)" section.
- `docs/features/faza-5-api-frontend/faza-5-task-3/README.md` (NEW) — this record.
- `docs/tasks/faza-5-task-3.md` (UPDATE) — story close-out.

## Key decisions
- **pnpm, not npm.** The plan text says `npm ci`/`npm run build`, but the Task 2
  agent (bob) scaffolded the frontend with pnpm (`pnpm-lock.yaml`, no
  `package-lock.json`). Followed the actual lockfile — used `pnpm install` +
  `pnpm run build` + `pnpm test` throughout.
- **`Usuń wszystkie dane` did not hit the guardrail-rejection path.** gemma4
  never emitted destructive SQL for it — it produced a safe `SELECT *` and
  declined in prose. That is correct, safe behaviour, but it does not exercise a
  red ODRZUCONE row. The `raw.trips` question is the reliable trigger for the
  `validate ok:false` → retry sequence, so it is the retry-evidence path.

## Verification
- `.venv/bin/pytest` → 85 passed, 5 deselected (integration).
- `cd frontend && pnpm test` → 15 passed (6 files).
- `pnpm run build` → clean (`dist/index.html` + hashed assets).
- Live `/health` on `:8000` → `{"ollama":"ok","bigquery":"ok","chroma_index":"ok"}`.
- Live `/chat` SSE → all three demo paths above, captured verbatim.

## UI fixes before merge (operator review + live user testing)
Live-demo review and hands-on user testing surfaced UI issues, all fixed
front-only (no `genai/`/`api/` changes) per
`docs/superpowers/specs/2026-07-18-faza-5-timeline-ui-fixes-design.md`:
1. Metro timeline line drifted under a wrapped rejection reason. First attempt
   (per-row line segments) regressed — segment height was content-dependent and
   drifted vertically on unequal row heights. Root-caused via
   systematic-debugging and fixed properly: one continuous `.timeline::before`
   with its centre aligned to the dot centre (both at 10px).
2. No between-stage loader → pulsing pending station showing the next-stage
   label (`nextStageLabel`); keyframe named `station-pulse` to avoid colliding
   with Tailwind's own `@keyframes pulse`; respects `prefers-reduced-motion`.
3. Raw BigQuery dry-run rejection (URL + Job ID) → `cleanReason` keeps the
   substance, drops the noise; still an `ODRZUCONE` guardrail row.
4. `f0_` table header → `columnLabel` renders "Wynik"/"Wynik N".
5. `0.0480 GB` chip → `formatScan` → "Przeskanowano 0.05 GB" (`<0.01 GB` for
   tiny scans).
6. A wide `SELECT *` result table broke the card border → wrapped in
   `overflow-x-auto` (+ `whitespace-nowrap`) so it scrolls inside the card.

Verified live with Playwright against the running dev server (real gemma4 +
BigQuery): all 7 timeline dots centred on the line (0.0px off) including the
wrapped-reason row; the pending dot on the line with label "Generowanie SQL" and
an active pulse; a 16-column `SELECT *` table (scrollWidth 2059px) clipped inside
the card. Suites: `pnpm test` 26/26 green; `pnpm run build` clean.
