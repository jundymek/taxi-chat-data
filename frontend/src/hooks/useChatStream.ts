import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/chatClient";
import { createFrameParser } from "../api/streamParser";
import type { ChatResult, Frame } from "../types";

export interface ChatStream {
  frames: Frame[]; // non-terminal frames, in arrival order
  result: ChatResult | null; // set by the `done` frame
  error: string | null; // set by the `error` frame or transport failure
  running: boolean;
  ask: (question: string) => Promise<void>;
}

/**
 * Owns the entire request lifecycle for one chat question: fires the stream,
 * parses frames, and exposes UI-ready state. A guardrail refusal arrives as a
 * `done` frame (result.refused) — NOT an error — per the SSE contract.
 */
export function useChatStream(): ChatStream {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [result, setResult] = useState<ChatResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const ask = useCallback(async (question: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    // Only the newest request may touch state; a superseded (re-asked) request
    // must not push frames, set a result, or clear `running` out from under it.
    const isCurrent = () => abortRef.current === controller;
    setFrames([]);
    setResult(null);
    setError(null);
    setRunning(true);
    const parse = createFrameParser();
    try {
      for await (const chunk of streamChat(question, controller.signal)) {
        if (!isCurrent()) return;
        for (const frame of parse(chunk)) {
          if (frame.stage === "done") setResult(frame.result ?? null);
          else if (frame.stage === "error") setError(frame.message ?? "Nieznany błąd");
          else setFrames((prev) => [...prev, frame]);
        }
      }
    } catch (exc) {
      if (isCurrent()) {
        setError(exc instanceof Error ? exc.message : "Błąd połączenia.");
      }
    } finally {
      if (isCurrent()) setRunning(false);
    }
  }, []);

  return { frames, result, error, running, ask };
}
