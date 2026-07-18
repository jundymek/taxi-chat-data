# Faza 5: chat UI fixes — timeline alignment, loader, readable results

> Front-only polish of the merged Faza 5 chat UI (tasks 1–2), applied on
> `feat/faza-5-api-frontend` before PR #13 merges to `master`. Fixes surfaced
> during operator live-demo review (Task 3).

## Scope

**In scope (front only):** `frontend/src/components/StageTimeline.tsx`,
`frontend/src/components/ResultCard.tsx`, `frontend/src/app/styles.css`, and the
matching `frontend/src/__tests__/`.

**Out of scope (untouched):** `genai/`, `api/`, and the SSE contract
(`api/schemas.py` ↔ `frontend/src/types.ts`). No frame fields change; the
backend behaviour is correct as-is. This is presentational work only.

## Problems (from live-demo screenshots)

1. **Timeline line misaligns.** The yellow route bar (`.timeline::before`) is a
   single continuous rectangle (`top:4px; bottom:4px`), while station dots
   (`.station::before`) anchor per-row at `top:0.28em`. A multi-line rejection
   reason (`.why`, `flex-basis:100%`) grows the `err` row; `gap:15px` then
   measures from the tall row's bottom, so the next station's dot drifts off the
   bar. Visible as the "SQL — próba 2" dot sitting away from the line.
2. **No loader between stages.** `running` renders a static `…` label with no
   motion; there is no "next stage in progress" affordance.
3. **BigQuery dry-run rejection shows raw API noise.** Guardrails run a BigQuery
   dry-run (`genai/guardrails.py:79`); a bad column/name makes the dry-run fail
   and the guardrail returns `reason = "BigQuery odrzucił zapytanie: <full API
   error incl. POST URL + Job ID>"`. On the wire this is a legitimate
   `validate ok:false` (the guardrail correctly caught bad SQL before
   execution), but the UI prints the entire raw message.
4. **`f0_` column header.** BigQuery auto-names unaliased SELECT expressions
   `f0_`, `f1_`, …; `ResultCard` renders `Object.keys(rows[0])` verbatim, so the
   table header shows the technical `f0_`.
5. **`0.0480 GB` chip is unlabelled and over-precise.** `scanned_gb.toFixed(4)`
   with no caption — the user can't tell it's "data scanned".

## Design

### 1. Timeline alignment — per-row line geometry

Remove the global `.timeline::before` bar. Each `.station` owns its own line
**segment** drawn as `::after` (a vertical yellow bar down the left gutter,
spanning the row's full height including any `.why`), and the dot `::before`
anchors to the **first line of the label**, not the vertical centre of a grown
row. Adjacent segments meet regardless of row height → the line is always
continuous and always under the dots. `.why` keeps a left indent aligned to the
text band so it never pushes the dot.

### 2. Loader — pulsing pending station

When `running`, the trailing element is an empty station: a grey dot that
**pulses** (opacity + scale) with a label = the **next** stage name, predicted
from the last completed frame (e.g. after `execute` → "Piszę odpowiedź…";
fallback "Łączenie…" when unpredictable). Under
`prefers-reduced-motion: reduce`, drop the animation but keep the dot and label
so the state stays legible statically. A small pure helper
`nextStageLabel(frames)` computes the predicted label.

### 3. Cleaned rejection reason

Keep the `ODRZUCONE` label (a dry-run failure IS a guardrail rejection). Add a
pure `cleanReason(reason: string): string` in `StageTimeline`: when the text
matches the BigQuery dry-run wrapper (`BigQuery odrzucił zapytanie: …`), strip
the `POST https://…` URL and `Job ID: …` / `Location: …` tail, keeping the
substance (e.g. "Nieznana nazwa: trip_duration; czy chodziło o
trip_duration_min?"). Classic guardrail reasons (allowlist, SELECT-only) pass
through unchanged. Rendered in place of the raw `frame.reason`.

### 4. `f0_` column label — `columnLabel(key)`

Pure `columnLabel(key: string, techCols: string[]): string` in `ResultCard`:
BigQuery technical names `f0_`, `f1_`, … → a readable label. One such column →
"Wynik"; several → "Wynik 1", "Wynik 2", …. Ordinary names (`avg_tip`,
`trip_key`) pass through unchanged. Applies only to the `<th>` header; `<td>`
cell values are unchanged, and row objects are still keyed by the original name.

### 5. Scan chip — labelled, 2-decimal

Scan chip becomes captioned: `Przeskanowano 0.05 GB` — still GB, rounded to 2
decimals (`0.0480` → `0.05`). Values below `0.01 GB` render as `<0.01 GB` to
avoid a misleading `0.00`. The "próby" and "model" chips are unchanged.

## Testing (TDD)

New / updated in `frontend/src/__tests__/`:

- **StageTimeline**
  - Regression: with a wrapped multi-line reason, the timeline stays aligned
    (assert the per-row line structure exists; no reliance on the removed
    global bar).
  - Pulsing pending station renders with the predicted next-stage label while
    `running`.
  - `cleanReason` strips the BigQuery URL and `Job ID` and preserves the
    substance; a classic allowlist reason is returned verbatim.
- **ResultCard**
  - `f0_` → "Wynik"; multiple `fN_` → "Wynik 1"/"Wynik 2"; ordinary names
    unchanged.
  - Scan chip shows the caption + 2-decimal value; a sub-0.01 GB value shows
    `<0.01 GB`.
- **Existing C1 tests** stay green; assertions that pin old copy (`"0.0480 GB"`,
  and any `f0_` expectation) are updated to the new format.

## Verification

- `cd frontend && pnpm test` → all green.
- `cd frontend && pnpm run build` → clean.
- Manual on `http://localhost:8000` (rebuilt `dist`): the three demo paths
  (happy / guardrail-retry with a wrapped reason / dry-run-name-error) render
  with an aligned line, a visible loader, a cleaned reason, a readable column
  header, and the captioned scan chip.
