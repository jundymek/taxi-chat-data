import type { Frame } from "../types";

/**
 * Stateful chunk-to-frames parser for our SSE stream. Pure w.r.t. I/O: feed it
 * text chunks, get complete frames back. Buffers partial chunks until the
 * event terminator (`\n\n`) arrives; parses only `data:` lines and ignores
 * comment/keep-alive lines (e.g. `: ping`).
 */
export function createFrameParser(): (chunk: string) => Frame[] {
  let buffer = "";
  return (chunk: string): Frame[] => {
    buffer += chunk;
    const frames: Frame[] = [];
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = rawEvent
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("");
      if (data) frames.push(JSON.parse(data) as Frame);
    }
    return frames;
  };
}
