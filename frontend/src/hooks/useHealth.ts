import { useEffect, useState } from "react";

export interface Health {
  ollama: string;
  bigquery: string;
  chroma_index: string;
}

/** Health of the /health fetch: loading → ready(payload) | error (unreachable). */
export type HealthState =
  | { status: "loading" }
  | { status: "ready"; health: Health }
  | { status: "error" };

/** Fetches dependency status once on mount. Distinguishes "still loading" from
 *  "endpoint unreachable" so the UI doesn't sit on a spinner forever. */
export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    fetch("/health")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Health>;
      })
      .then((health) => {
        if (!cancelled) setState({ status: "ready", health });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}
