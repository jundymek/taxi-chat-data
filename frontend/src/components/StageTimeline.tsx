import type { Frame } from "../types";

interface StageTimelineProps {
  frames: Frame[];
  running: boolean;
}

// Polish user-facing labels per stage (direction 1C keeps C1's wording).
const LABELS: Record<string, (f: Frame) => string> = {
  retrieve: () => "Kontekst schematu",
  generate_sql: (f) => `SQL — próba ${f.attempt ?? 1}`,
  validate: () => "Guardraile",
  execute: () => "BigQuery — wykonanie",
  summarize: () => "Piszę odpowiedź",
};

// Label of the stage EXPECTED next, shown on the pulsing in-flight row.
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
  // If stripping left nothing, show the wrapper alone rather than re-exposing
  // the raw URL/Job-ID noise this function exists to remove.
  return cleaned ? `${WRAPPER} ${cleaned}` : WRAPPER;
}

/** Flexing middle column: the substance of what a completed stage did. Only
 *  guardrails carry per-frame detail in the SSE contract; other stages have
 *  nothing to add, so their cell stays empty rather than inventing filler. */
export function frameDetail(frame: Frame): string {
  if (frame.stage !== "validate") return "";
  return frame.ok === false && frame.reason ? cleanReason(frame.reason) : "dry-run OK";
}

/**
 * 1C stage stream: a dense status ledger inside a white panel. Each row is a
 * status glyph (✓ / ✕ / ●), the stage label, a detail that flexes to fill, and
 * a right-aligned state word. While running, a pulsing row shows the predicted
 * next stage. Presentational only — logic lives in the pure helpers above.
 */
export function StageTimeline({ frames, running }: StageTimelineProps) {
  return (
    <section className="mt-3.5 rounded-lg border border-hair bg-panel px-4 py-1.5">
      <ol className="m-0 list-none p-0">
        {frames.map((frame, i) => {
          const rejected = frame.stage === "validate" && frame.ok === false;
          return (
            <li key={i} className={rejected ? "frame-row err" : "frame-row"}>
              <span className="glyph" aria-hidden="true">
                {rejected ? "✕" : "✓"}
              </span>
              <span className="lbl">{LABELS[frame.stage]?.(frame) ?? frame.stage}</span>
              <span className="detail">{frameDetail(frame)}</span>
              <span className="dur">{rejected ? "ODRZUCONE" : "OK"}</span>
            </li>
          );
        })}
        {running ? (
          <li className="frame-row run" data-testid="pending-station">
            <span className="glyph" aria-hidden="true">
              ●
            </span>
            <span className="lbl">{nextStageLabel(frames)}</span>
            <span className="detail" />
          </li>
        ) : null}
      </ol>
    </section>
  );
}
