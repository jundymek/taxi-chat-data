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

/**
 * C1 "Linia M" stage timeline: yellow route line, green station dots, dotted
 * leader, monospace status on the right, and a red ODRZUCONE row with the
 * guardrail reason beneath it. Presentational only — no logic, no state.
 * The metro visuals live in the custom `.timeline`/`.station` CSS layer;
 * everything else is Tailwind.
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
            {rejected && frame.reason ? <span className="why">{frame.reason}</span> : null}
          </li>
        );
      })}
      {running ? (
        <li className="station pending">
          <span className="lbl">…</span>
        </li>
      ) : null}
    </ol>
  );
}
