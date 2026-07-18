# Faza 5 chat UI fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Front-only polish of the merged Faza 5 chat UI — align the metro
timeline, add a real between-stage loader, and make rejection reasons, result
columns, and the scan chip readable — before PR #13 merges to `master`.

**Architecture:** Three presentational React components in `frontend/src/`
(`StageTimeline`, `ResultCard`) plus their custom CSS layer (`app/styles.css`).
Logic added is limited to small **pure helper functions** (`cleanReason`,
`nextStageLabel`, `columnLabel`, `formatScan`) that are trivially unit-testable.
No hooks, no state, no data flow changes.

**Tech Stack:** Vite 8 + React 19 + TypeScript + Tailwind v4 (utilities) with a
small custom CSS layer for the metro visuals; Vitest 4 + Testing Library (jsdom).
Package manager: **pnpm** (`pnpm-lock.yaml` — NOT npm).

## Global Constraints

- Scope is **front only**: `frontend/src/components/StageTimeline.tsx`,
  `frontend/src/components/ResultCard.tsx`, `frontend/src/app/styles.css`, and
  `frontend/src/__tests__/`. Do NOT touch `genai/`, `api/`, `requirements.txt`,
  or the SSE contract (`api/schemas.py` ↔ `frontend/src/types.ts`).
- Code/comments/commit messages in ENGLISH; commits Conventional
  (`fix(faza-5-ui): …`); NO AI footer/co-author line. UI copy in POLISH.
- Run tests with **pnpm** from `frontend/`: `pnpm test`. Build: `pnpm run build`.
- Binding visual tokens (approved mockup C1, already in `@theme`): ink `#111111`,
  paper `#FFFFFF`, line/yellow `#FCCC0A`, ok/green `#00933C`, err/red `#D0021B`;
  Helvetica/system sans; monospace for SQL/numbers/statuses; 2px ink borders;
  no border-radius except circles/chips/pills.
- Components stay presentational: props in, JSX out. New logic lives ONLY in pure
  helper functions co-located in the component file, exported for unit tests.
- Respect `prefers-reduced-motion: reduce` for any animation.

---

## Task 1: Timeline alignment + between-stage loader (`StageTimeline`)

**Files:**
- Modify: `frontend/src/components/StageTimeline.tsx`
- Modify: `frontend/src/app/styles.css:25-109` (the `.timeline`/`.station` layer)
- Test: `frontend/src/__tests__/StageTimeline.test.tsx`

**Interfaces:**
- Consumes: `Frame` from `../types` (unchanged: `stage`, `attempt?`, `ok?`,
  `reason?`, `message?`, `result?`).
- Produces (exported from `StageTimeline.tsx` for tests):
  - `export function cleanReason(reason: string): string` — strips the BigQuery
    dry-run wrapper's URL and `Job ID:`/`Location:` tail; returns other reasons
    verbatim.
  - `export function nextStageLabel(frames: Frame[]): string` — the Polish label
    for the stage expected after the last completed frame.
  - `StageTimeline` component (props `{ frames: Frame[]; running: boolean }`).

- [ ] **Step 1: Write the failing tests**

Replace the body of `frontend/src/__tests__/StageTimeline.test.tsx` with:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageTimeline, cleanReason, nextStageLabel } from "../components/StageTimeline";

describe("StageTimeline (mockup C1)", () => {
  it("renders OK status for successful validate and the reason for rejection", () => {
    render(
      <StageTimeline
        frames={[
          { stage: "retrieve" },
          { stage: "generate_sql", attempt: 1 },
          {
            stage: "validate",
            ok: false,
            reason: "Tabela raw.trips jest poza dozwolonymi zbiorami danych",
          },
          { stage: "generate_sql", attempt: 2 },
          { stage: "validate", ok: true },
        ]}
        running={false}
      />,
    );
    expect(screen.getByText("ODRZUCONE")).toBeInTheDocument();
    expect(screen.getByText(/raw\.trips/)).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("SQL — próba 2")).toBeInTheDocument();
  });

  it("renders a pulsing pending station with the next-stage label while running", () => {
    render(
      <StageTimeline
        frames={[{ stage: "retrieve" }, { stage: "generate_sql", attempt: 1 }]}
        running={true}
      />,
    );
    // after generate_sql, the next stage is validate → "Guardraile"
    const pending = screen.getByTestId("pending-station");
    expect(pending).toHaveTextContent("Guardraile");
    expect(pending.className).toContain("pending");
  });
});

describe("cleanReason", () => {
  it("strips the BigQuery URL and Job ID from a dry-run rejection", () => {
    const raw =
      "BigQuery odrzucił zapytanie: POST https://bigquery.googleapis.com/bigquery/v2/projects/taxi-chat-data/jobs?prettyPrint=false: Unrecognized name: trip_duration; Did you mean trip_duration_min? at [1:12] Location: None Job ID: 065f810b-ba78-4c56-be78-d44451d741ed";
    const cleaned = cleanReason(raw);
    expect(cleaned).toContain("Unrecognized name: trip_duration");
    expect(cleaned).toContain("Did you mean trip_duration_min");
    expect(cleaned).not.toContain("https://");
    expect(cleaned).not.toContain("Job ID");
    expect(cleaned).not.toContain("Location: None");
  });

  it("returns a classic guardrail reason unchanged", () => {
    const reason = "Tabela raw.trips jest poza dozwolonymi zbiorami danych (marts, staging).";
    expect(cleanReason(reason)).toBe(reason);
  });
});

describe("nextStageLabel", () => {
  it("predicts the stage after the last completed frame", () => {
    expect(nextStageLabel([{ stage: "retrieve" }])).toBe("Generowanie SQL");
    expect(nextStageLabel([{ stage: "generate_sql", attempt: 1 }])).toBe("Guardraile");
    expect(nextStageLabel([{ stage: "validate", ok: true }])).toBe("BigQuery — wykonanie");
    expect(nextStageLabel([{ stage: "execute" }])).toBe("Piszę odpowiedź");
  });

  it("falls back to a generic label at the very start", () => {
    expect(nextStageLabel([])).toBe("Łączenie…");
  });

  it("predicts a retry after a failed validate", () => {
    expect(nextStageLabel([{ stage: "validate", ok: false, reason: "x" }])).toBe(
      "Generowanie SQL",
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm test -- StageTimeline`
Expected: FAIL — `cleanReason`/`nextStageLabel` are not exported; no
`pending-station` testid.

- [ ] **Step 3: Rewrite `StageTimeline.tsx`**

Replace `frontend/src/components/StageTimeline.tsx` with:
```tsx
import type { Frame } from "../types";

interface StageTimelineProps {
  frames: Frame[];
  running: boolean;
}

// Polish user-facing labels per stage (approved mockup C1).
const LABELS: Record<string, (f: Frame) => string> = {
  retrieve: () => "Kontekst schematu",
  generate_sql: (f) => `SQL — próba ${f.attempt ?? 1}`,
  validate: () => "Guardraile",
  execute: () => "BigQuery — wykonanie",
  summarize: () => "Piszę odpowiedź",
};

// Label of the stage EXPECTED next, shown on the pulsing pending station.
const NEXT_LABEL: Record<string, string> = {
  retrieve: "Generowanie SQL",
  generate_sql: "Guardraile",
  validate: "BigQuery — wykonanie", // ok:true → execute
  execute: "Piszę odpowiedź",
  summarize: "Piszę odpowiedź",
};

/** Predict the label of the next stage from the last completed frame.
 *  A failed validate loops back to generate_sql (a retry). */
export function nextStageLabel(frames: Frame[]): string {
  const last = frames[frames.length - 1];
  if (!last) return "Łączenie…";
  if (last.stage === "validate" && last.ok === false) return "Generowanie SQL";
  return NEXT_LABEL[last.stage] ?? "Piszę odpowiedź";
}

/** Strip the raw BigQuery dry-run wrapper (POST URL + Job ID/Location tail),
 *  keeping the substance. Other guardrail reasons pass through unchanged. */
export function cleanReason(reason: string): string {
  const WRAPPER = "BigQuery odrzucił zapytanie:";
  if (!reason.startsWith(WRAPPER)) return reason;
  let body = reason.slice(WRAPPER.length);
  // Drop the leading "POST https://…jobs?prettyPrint=false:" segment.
  body = body.replace(/\s*POST\s+https?:\/\/\S+?:\s*/i, " ");
  // Drop the trailing " at [r:c] Location: … Job ID: …" noise.
  body = body.replace(/\s*(at \[\d+:\d+\])?\s*Location:.*$/i, "");
  body = body.replace(/\s*Job ID:.*$/i, "");
  const cleaned = body.trim();
  return cleaned ? `${WRAPPER} ${cleaned}` : reason;
}

/**
 * C1 "Linia M" stage timeline. Each station owns its own line segment and dot
 * (per-row geometry) so a wrapped rejection reason never drifts the line. While
 * running, a pulsing pending station shows the predicted next stage.
 * Presentational only — logic lives in the exported pure helpers above.
 */
export function StageTimeline({ frames, running }: StageTimelineProps) {
  return (
    <ol className="timeline">
      {frames.map((frame, i) => {
        const rejected = frame.stage === "validate" && frame.ok === false;
        return (
          <li key={i} className={rejected ? "station err" : "station"}>
            <span className="lbl">{LABELS[frame.stage]?.(frame) ?? frame.stage}</span>
            <span className="dots" />
            <span className="st">{rejected ? "ODRZUCONE" : "OK"}</span>
            {rejected && frame.reason ? (
              <span className="why">{cleanReason(frame.reason)}</span>
            ) : null}
          </li>
        );
      })}
      {running ? (
        <li className="station pending" data-testid="pending-station">
          <span className="lbl">{nextStageLabel(frames)}</span>
          <span className="dots" />
        </li>
      ) : null}
    </ol>
  );
}
```

- [ ] **Step 4: Rewrite the timeline CSS layer**

Replace `frontend/src/app/styles.css:25-109` (the block from the
`/* ---- C1 metro stage-timeline … */` comment through the closing
`@media (prefers-reduced-motion …)` rule) with:
```css
/* ---- C1 metro stage-timeline (custom layer) ----
   Per-row geometry: each station draws its own vertical line segment (::after)
   and its dot (::before) anchored to the FIRST line of the label, so a wrapped
   rejection reason grows the row without drifting the continuous line. */
.timeline {
  list-style: none;
  margin: 26px 0 6px;
  padding: 0 0 0 34px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 15px;
}
.station {
  position: relative;
  font-size: 0.95rem;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}
/* Vertical yellow line segment for this row: spans the full row height plus the
   gap to the next station, so adjacent segments meet into one continuous line. */
.station::after {
  content: "";
  position: absolute;
  left: -24px;
  top: 0;
  height: calc(100% + 15px); /* row + .timeline gap */
  width: 8px;
  background: var(--color-line);
  border-radius: 4px;
}
.station:last-child::after {
  height: 100%; /* no gap below the last station */
}
/* Green station dot, anchored to the first label line (not the grown row). */
.station::before {
  content: "";
  position: absolute;
  left: -30px;
  top: 0.28em;
  z-index: 1;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-ok);
  border: 3px solid var(--color-ok);
}
.station.err::before {
  background: var(--color-err);
  border-color: var(--color-err);
}
.station.pending::before {
  background: #fff;
  border-color: #bbb;
}
.station .dots {
  flex: 1;
  border-bottom: 1px dotted #bbb;
  transform: translateY(-4px);
}
.station .st {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.75rem;
  color: var(--color-ok);
  letter-spacing: 0.08em;
}
.station.err .st {
  color: var(--color-err);
}
.station .why {
  /* Full-width so a multi-line reason flows below the row; indented to the text
     band so the dot and line stay put. */
  flex-basis: 100%;
  margin-top: 2px;
  font-size: 0.78rem;
  color: var(--color-err);
}
/* Pulsing pending station: the dot breathes while the next stage runs. */
.station.pending::before {
  animation: pulse 1.1s ease-in-out infinite;
}
.station.pending .lbl {
  color: #888;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.8); }
}
@media (prefers-reduced-motion: no-preference) {
  .station { animation: arrive 0.2s ease-out; }
  @keyframes arrive {
    from { opacity: 0; transform: translateY(4px); }
  }
}
@media (prefers-reduced-motion: reduce) {
  .station.pending::before { animation: none; }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm test -- StageTimeline`
Expected: PASS (component + `cleanReason` + `nextStageLabel` suites).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/StageTimeline.tsx frontend/src/app/styles.css \
        frontend/src/__tests__/StageTimeline.test.tsx
git commit -m "fix(faza-5-ui): align metro timeline + pulsing between-stage loader + clean reason"
```

---

## Task 2: Readable result columns + labelled scan chip (`ResultCard`)

**Files:**
- Modify: `frontend/src/components/ResultCard.tsx`
- Test: `frontend/src/__tests__/ResultCard.test.tsx`

**Interfaces:**
- Consumes: `ChatResult` from `../types` (unchanged).
- Produces (exported from `ResultCard.tsx` for tests):
  - `export function columnLabel(key: string, allKeys: string[]): string` —
    BigQuery technical names `f0_`, `f1_`, … → "Wynik" (single) or
    "Wynik 1"/"Wynik 2"/… (multiple); ordinary names pass through.
  - `export function formatScan(gb: number): string` — captioned, 2-decimal GB;
    sub-0.01 GB renders as `<0.01 GB`.
  - `ResultCard` component (props `{ result: ChatResult }`).

- [ ] **Step 1: Write the failing tests**

Replace the body of `frontend/src/__tests__/ResultCard.test.tsx` with:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultCard, columnLabel, formatScan } from "../components/ResultCard";

const RESULT = {
  answer: "Średni napiwek wynosił 4,16 USD.",
  sql: "SELECT 1",
  rows: [{ avg_tip: 4.16 }],
  scanned_gb: 0.048,
  attempts: 2,
  refused: false,
  model: "gemma4:latest",
};

describe("ResultCard", () => {
  it("shows the answer, chips and the rows table", () => {
    render(<ResultCard result={RESULT} />);
    expect(screen.getByText(/4,16 USD/)).toBeInTheDocument();
    expect(screen.getByText("2 próby")).toBeInTheDocument();
    expect(screen.getByText("Przeskanowano 0.05 GB")).toBeInTheDocument();
    expect(screen.getByText("avg_tip")).toBeInTheDocument();
  });

  it("renders a technical f0_ column as a readable label", () => {
    render(<ResultCard result={{ ...RESULT, rows: [{ f0_: 6179 }] }} />);
    expect(screen.getByText("Wynik")).toBeInTheDocument();
    expect(screen.queryByText("f0_")).not.toBeInTheDocument();
    expect(screen.getByText("6179")).toBeInTheDocument();
  });

  it("renders a refusal without a rows table", () => {
    render(
      <ResultCard
        result={{
          ...RESULT,
          refused: true,
          rows: [],
          reason: "Tylko SELECT.",
          answer: "Nie umiem bezpiecznie odpowiedzieć.",
        }}
      />,
    );
    expect(screen.getByText(/Nie umiem/)).toBeInTheDocument();
    expect(screen.getByText(/Tylko SELECT/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("columnLabel", () => {
  it("maps a single technical column to Wynik", () => {
    expect(columnLabel("f0_", ["f0_"])).toBe("Wynik");
  });
  it("numbers multiple technical columns", () => {
    expect(columnLabel("f0_", ["f0_", "f1_"])).toBe("Wynik 1");
    expect(columnLabel("f1_", ["f0_", "f1_"])).toBe("Wynik 2");
  });
  it("passes ordinary names through", () => {
    expect(columnLabel("avg_tip", ["avg_tip"])).toBe("avg_tip");
  });
});

describe("formatScan", () => {
  it("captions and rounds to 2 decimals", () => {
    expect(formatScan(0.048)).toBe("Przeskanowano 0.05 GB");
    expect(formatScan(1.2345)).toBe("Przeskanowano 1.23 GB");
  });
  it("shows <0.01 GB for tiny scans", () => {
    expect(formatScan(0.0004)).toBe("Przeskanowano <0.01 GB");
    expect(formatScan(0)).toBe("Przeskanowano <0.01 GB");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm test -- ResultCard`
Expected: FAIL — `columnLabel`/`formatScan` not exported; chip still reads
`0.0480 GB`; `f0_` rendered verbatim.

- [ ] **Step 3: Rewrite `ResultCard.tsx`**

Replace `frontend/src/components/ResultCard.tsx` with:
```tsx
import type { ChatResult } from "../types";

interface ResultCardProps {
  result: ChatResult;
}

const TECH_COL = /^f\d+_$/; // BigQuery auto-name for an unaliased SELECT expr.

/** Human label for a table column. Technical BigQuery names (f0_, f1_, …)
 *  become "Wynik" (single) or "Wynik N" (several); other names pass through. */
export function columnLabel(key: string, allKeys: string[]): string {
  if (!TECH_COL.test(key)) return key;
  const tech = allKeys.filter((k) => TECH_COL.test(k));
  if (tech.length <= 1) return "Wynik";
  return `Wynik ${tech.indexOf(key) + 1}`;
}

/** Captioned scan size in GB, 2 decimals; tiny scans as "<0.01 GB". */
export function formatScan(gb: number): string {
  const size = gb < 0.01 ? "<0.01 GB" : `${gb.toFixed(2)} GB`;
  return `Przeskanowano ${size}`;
}

/**
 * C1 result card: ink-bordered panel with the Polish answer, metadata chips
 * (attempts / GB scanned / model), a collapsible SQL block, and the rows table.
 * A refusal renders the reason and no table. Presentational only; label logic
 * lives in the exported pure helpers above.
 */
export function ResultCard({ result }: ResultCardProps) {
  const columns = result.rows.length ? Object.keys(result.rows[0]) : [];
  return (
    <section className="mt-[22px] border-2 border-ink">
      <header className="bg-ink px-[14px] py-2 text-[0.78rem] uppercase tracking-[0.12em] text-white">
        Wynik kursu
      </header>
      <div className="px-[18px] py-4">
        <p className="m-0 mb-3 text-[1.3rem] leading-[1.4]">{result.answer}</p>
        {result.refused && result.reason ? (
          <p className="text-[0.9rem] text-err">{result.reason}</p>
        ) : null}
        <div className="mb-3 flex flex-wrap gap-2">
          <span className="rounded-full border-[1.5px] border-line bg-line px-3 py-0.5 text-xs font-bold">
            {result.attempts} {result.attempts === 1 ? "próba" : "próby"}
          </span>
          <span className="rounded-full border-[1.5px] border-ink px-3 py-0.5 text-xs font-bold">
            {formatScan(result.scanned_gb)}
          </span>
          <span className="rounded-full border-[1.5px] border-ink px-3 py-0.5 text-xs font-bold">
            {result.model.split(":")[0]}
          </span>
        </div>
        {result.sql ? (
          <details>
            <summary className="cursor-pointer text-[0.8rem] font-bold uppercase tracking-[0.06em]">
              Użyty SQL
            </summary>
            <pre className="overflow-x-auto bg-[#f4f4f4] p-3 font-mono text-[0.8rem] leading-[1.5]">
              {result.sql}
            </pre>
          </details>
        ) : null}
        {columns.length ? (
          <table className="mt-2 w-full border-collapse text-[0.85rem] [font-variant-numeric:tabular-nums]">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    key={c}
                    className="bg-ink px-2 py-[5px] text-left text-[0.75rem] tracking-[0.08em] text-white"
                  >
                    {columnLabel(c, columns)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c} className="border-b border-[#ddd] px-2 py-1.5 font-mono">
                      {String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm test -- ResultCard`
Expected: PASS (component + `columnLabel` + `formatScan` suites).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ResultCard.tsx \
        frontend/src/__tests__/ResultCard.test.tsx
git commit -m "fix(faza-5-ui): readable result columns (f0_ → Wynik) + labelled scan chip"
```

---

## Task 3: Full-suite verification, build, live re-check, docs

**Files:**
- Modify: `docs/features/faza-5-api-frontend/faza-5-task-3/README.md` (append UI-fix note)
- Modify: `docs/tasks/faza-5-task-3.md` (append UI-fix note to Dev Agent Record)

**Interfaces:**
- Consumes: the finished Task 1 + Task 2 changes.
- Produces: verified green build; no new code interfaces.

- [ ] **Step 1: Full frontend suite**

Run: `cd frontend && pnpm test`
Expected: all files PASS (parser, hook, StageTimeline incl. new helper suites,
ResultCard incl. new helper suites). No failures.

- [ ] **Step 2: Build**

Run: `cd frontend && pnpm run build`
Expected: `tsc -b && vite build` clean, `dist/` written, no type errors.

- [ ] **Step 3: Live re-check on one port**

```bash
cd /Users/jundymek/dev/taxi-chat-data
.venv/bin/uvicorn api.main:app --port 8000   # (background; needs Ollama + ADC + data/chroma)
```
Open `http://localhost:8000` and confirm visually:
- Happy path — the yellow line is continuous and every green dot sits ON it.
- A guardrail-retry question (`Pokaż surowe rekordy z tabeli raw.trips…`) — the
  red ODRZUCONE row shows a wrapped reason and the line stays aligned below it;
  while streaming, a pulsing grey pending station shows the next stage label.
- A dry-run name error (e.g. a question whose SQL references a wrong column) —
  the reason reads cleaned (no `https://…`, no `Job ID:`).
- The result card chip reads `Przeskanowano 0.05 GB`; an unaliased aggregate
  shows a `Wynik` column header, not `f0_`.

- [ ] **Step 4: Append the UI-fix note to the feature record**

Append to `docs/features/faza-5-api-frontend/faza-5-task-3/README.md`:
```markdown

## UI fixes before merge (operator review)
Live-demo review surfaced five presentational issues, fixed front-only (no
`genai/`/`api/` changes) per
`docs/superpowers/specs/2026-07-18-faza-5-timeline-ui-fixes-design.md`:
1. Metro timeline line drifted under a wrapped rejection reason → per-row line
   geometry (each station owns its segment + dot).
2. No between-stage loader → pulsing pending station showing the next-stage
   label (respects `prefers-reduced-motion`).
3. Raw BigQuery dry-run rejection (URL + Job ID) → `cleanReason` keeps the
   substance, drops the noise; still an `ODRZUCONE` guardrail row.
4. `f0_` table header → `columnLabel` renders "Wynik"/"Wynik N".
5. `0.0480 GB` chip → `formatScan` → "Przeskanowano 0.05 GB" (`<0.01 GB` for
   tiny scans).
Suites: `pnpm test` green; `pnpm run build` clean.
```

- [ ] **Step 5: Append the UI-fix note to the story**

Append to the `### Completion Notes` section of `docs/tasks/faza-5-task-3.md`:
```markdown
- Post-review UI fixes (front-only) landed before merge: timeline alignment,
  pulsing between-stage loader, cleaned dry-run rejection reason, `f0_` → "Wynik"
  column labels, labelled scan chip. Spec:
  `docs/superpowers/specs/2026-07-18-faza-5-timeline-ui-fixes-design.md`.
```

- [ ] **Step 6: Commit and push (updates PR #13)**

```bash
git add docs/
git commit -m "docs: record Faza 5 UI fixes in task-3 feature record + story"
git push
```
The push updates the existing PR #13 (branch `feat/faza-5-api-frontend`).

---

## Self-review notes

- **Spec coverage:** all five spec problems map to tasks — timeline align (T1),
  loader (T1), cleaned reason (T1 `cleanReason`), `f0_` (T2 `columnLabel`),
  scan chip (T2 `formatScan`); verification + docs (T3).
- **Type consistency:** helper names identical across plan and tests
  (`cleanReason`, `nextStageLabel`, `columnLabel`, `formatScan`); component
  props unchanged; `Frame`/`ChatResult` imported, not redefined.
- **pnpm** used throughout (not npm); front-only scope held (no `api/`/`genai/`).
