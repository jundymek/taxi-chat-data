import type { Health } from "../hooks/useHealth";

interface HealthBarProps {
  health: Health | null;
}

const LABEL: Record<string, string> = {
  ollama: "Ollama",
  bigquery: "BigQuery",
  chroma_index: "Indeks",
};

/** Dependency status line in the sign bar (green = ok, red = down/missing). */
export function HealthBar({ health }: HealthBarProps) {
  if (!health) {
    return <small className="ml-auto text-[0.72rem] text-[#99a]">Sprawdzam status…</small>;
  }
  return (
    <small className="ml-auto text-[0.72rem] text-[#99a]">
      {Object.entries(health).map(([key, value]) => (
        <span key={key}>
          {LABEL[key]}{" "}
          <b className={value === "ok" ? "text-[#7ed488]" : "text-[#ff8484]"}>
            {value.toUpperCase()}
          </b>{" "}
        </span>
      ))}
    </small>
  );
}
