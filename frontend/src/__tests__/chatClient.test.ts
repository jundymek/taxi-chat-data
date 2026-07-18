import { describe, expect, it, vi } from "vitest";
import { streamChat } from "../api/chatClient";

function byteStream(...chunks: number[][]) {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const bytes of chunks) controller.enqueue(new Uint8Array(bytes));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

describe("streamChat", () => {
  it("reassembles a multibyte UTF-8 char split across chunks", async () => {
    // "ó" = 0xC3 0xB3, delivered one byte per read (and flushed at EOF).
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(byteStream([0xc3], [0xb3])));
    let out = "";
    for await (const chunk of streamChat("q")) out += chunk;
    expect(out).toBe("ó");
  });

  it("throws a Polish error when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
    await expect(streamChat("q").next()).rejects.toThrow(/Serwer odpowiedział błędem \(500\)/);
  });
});
