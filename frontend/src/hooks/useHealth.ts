import { useEffect, useState } from "react";

export interface Health {
  ollama: string;
  bigquery: string;
  chroma_index: string;
}

/** Fetches dependency status once on mount; null until the first response. */
export function useHealth(): Health | null {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);
  return health;
}
