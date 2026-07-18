// Mirrors api/schemas.py 1:1 (Task 0, the SSE protocol contract) — do not
// improvise fields. Intent-synced with the API agent (faza-5-task-1).
export type Stage =
  | "retrieve"
  | "generate_sql"
  | "validate"
  | "execute"
  | "summarize"
  | "done"
  | "error";

export interface ChatResult {
  answer: string;
  sql: string;
  rows: Record<string, unknown>[];
  scanned_gb: number;
  attempts: number;
  refused: boolean;
  reason?: string;
  model: string;
}

export interface Frame {
  stage: Stage;
  attempt?: number; // generate_sql
  ok?: boolean; // validate
  reason?: string; // validate, ok === false (Polish)
  message?: string; // error (Polish)
  result?: ChatResult; // done
}
