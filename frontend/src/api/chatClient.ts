/**
 * POSTs the question and yields raw text chunks of the SSE stream. We use
 * `fetch` + `ReadableStream` (not `EventSource`, which is GET-only) so we can
 * send a JSON body. The pure parser turns these chunks into frames.
 */
export async function* streamChat(question: string, signal?: AbortSignal) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`The server returned an error (${response.status}).`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      // Flush any bytes the streaming decoder is still buffering (e.g. a
      // multibyte UTF-8 char split across the final chunks), else the last
      // frame can be truncated.
      const tail = decoder.decode();
      if (tail) yield tail;
      break;
    }
    yield decoder.decode(value, { stream: true });
  }
}
