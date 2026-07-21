import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChatStream } from "../hooks/useChatStream";

function sseResponse(...events: string[]) {
  const body = new ReadableStream({
    start(controller) {
      for (const e of events) controller.enqueue(new TextEncoder().encode(e));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

const EV = (json: string) => `event: stage\ndata: ${json}\n\n`;

describe("useChatStream", () => {
  it("collects stage frames and the final result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse(
          EV('{"stage":"retrieve"}'),
          EV('{"stage":"generate_sql","attempt":1}'),
          EV('{"stage":"validate","ok":true}'),
          EV('{"stage":"execute"}'),
          EV('{"stage":"summarize"}'),
          EV(
            '{"stage":"done","result":{"answer":"Five.","sql":"SELECT 1","rows":[],' +
              '"scanned_gb":0.01,"attempts":1,"refused":false,"model":"gemma4"}}',
          ),
        ),
      ),
    );
    const { result } = renderHook(() => useChatStream());
    act(() => {
      void result.current.ask("How many trips?");
    });
    await waitFor(() => expect(result.current.result?.answer).toBe("Five."));
    expect(result.current.frames.map((f) => f.stage)).toEqual([
      "retrieve",
      "generate_sql",
      "validate",
      "execute",
      "summarize",
    ]);
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("exposes a terminal error frame as error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse(
          EV('{"stage":"retrieve"}'),
          EV('{"stage":"error","message":"Ollama is not responding"}'),
        ),
      ),
    );
    const { result } = renderHook(() => useChatStream());
    act(() => {
      void result.current.ask("How many?");
    });
    await waitFor(() => expect(result.current.error).toBe("Ollama is not responding"));
    expect(result.current.result).toBeNull();
  });

  it("ignores a superseded request: only the latest ask sets state", async () => {
    const enc = (s: string) => new TextEncoder().encode(s);
    // First request: emits one frame then hangs; its stream errors on abort.
    const firstFetch = (_url: string, opts: { signal?: AbortSignal }) =>
      Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(enc(EV('{"stage":"retrieve"}')));
              opts.signal?.addEventListener("abort", () =>
                controller.error(new DOMException("Aborted", "AbortError")),
              );
            },
          }),
          { status: 200 },
        ),
      );
    // Second request completes normally.
    const secondFetch = () =>
      Promise.resolve(
        sseResponse(
          EV('{"stage":"validate","ok":true}'),
          EV(
            '{"stage":"done","result":{"answer":"Second.","sql":"","rows":[],' +
              '"scanned_gb":0,"attempts":1,"refused":false,"model":"m"}}',
          ),
        ),
      );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementationOnce(firstFetch).mockImplementationOnce(secondFetch),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      void result.current.ask("First?");
    });
    await waitFor(() =>
      expect(result.current.frames.map((f) => f.stage)).toContain("retrieve"),
    );
    act(() => {
      void result.current.ask("Second?");
    });
    await waitFor(() => expect(result.current.result?.answer).toBe("Second."));
    // The abandoned first stream must not leak its frame or clear `running`.
    expect(result.current.frames.map((f) => f.stage)).toEqual(["validate"]);
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
