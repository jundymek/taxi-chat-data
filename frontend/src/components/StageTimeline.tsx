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
