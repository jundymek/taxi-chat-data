import type { Health, HealthState } from "../hooks/useHealth";

interface HealthBarProps {
  state: HealthState;
}

const LABEL: Record<string, string> = {
  ollama: "Ollama",
  bigquery: "BigQuery",
  chroma_index: "Indeks",
};

/** Names of the dependencies that are not "ok", in stable payload order. */
export function downServices(health: Health): string[] {
  return Object.entries(health)
    .filter(([, value]) => value !== "ok")
    .map(([key]) => LABEL[key] ?? key);
}

/** Pill copy for a ready payload: all-clear, or which dependencies are down. */
export function healthSummary(health: Health): string {
  const down = downServices(health);
  if (!down.length) return "wszystkie usługi OK";
  return `${down.join(", ")} — brak połączenia`;
}

/**
 * 1C status pill: a dot plus one line of state, in the console header.
 *
 * Reports dependency availability from GET /health — NOT data freshness. The 1C
 * mockup shows a staleness pill ("yellow_trips · 26h stale"); no endpoint
 * exposes load lag today, so this reports what the API actually knows rather
 * than displaying an invented freshness figure.
 */
export function HealthBar({ state }: HealthBarProps) {
  const base =
    "ml-auto flex items-center gap-1.5 rounded-full border px-[9px] py-[3px] font-mono text-[11px] font-medium";
  if (state.status === "loading") {
    return (
      <span className={`${base} border-hair bg-subtle text-faint`}>
        <span className="h-1.5 w-1.5 rounded-full bg-faint" />
        sprawdzam status…
      </span>
    );
  }
  if (state.status === "error") {
    return (
      <span className={`${base} border-warn-line bg-warn-bg text-warn`}>
        <span className="h-1.5 w-1.5 rounded-full bg-warn-dot" />
        status niedostępny
      </span>
    );
  }
  const healthy = downServices(state.health).length === 0;
  return (
    <span
      className={
        healthy
          ? `${base} border-well-line bg-well-bg text-well`
          : `${base} border-warn-line bg-warn-bg text-warn`
      }
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${healthy ? "bg-well-dot" : "bg-warn-dot"}`}
      />
      {healthSummary(state.health)}
    </span>
  );
}
