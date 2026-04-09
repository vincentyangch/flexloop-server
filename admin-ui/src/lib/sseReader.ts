/**
 * Minimal SSE (server-sent events) parser for fetch-based POST streams.
 *
 * EventSource only supports GET, so we use fetch() + ReadableStream to
 * carry a POST body AND read SSE responses. This parser accumulates
 * bytes from the reader and emits parsed JSON payloads from each
 * ``data: <json>\n\n`` line.
 *
 * Usage:
 *
 *   const res = await fetch("/api/admin/playground/run", {
 *     method: "POST",
 *     headers: {"Content-Type": "application/json"},
 *     body: JSON.stringify(payload),
 *     credentials: "same-origin",
 *   });
 *   for await (const event of parseSSE(res)) {
 *     if (event.type === "content") ...
 *   }
 */
export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

export async function* parseSSE(
  response: Response,
): AsyncGenerator<SSEEvent, void, unknown> {
  if (!response.body) {
    throw new Error("response has no body");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line (\n\n)
    const lines = buffer.split("\n\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const json = trimmed.slice("data:".length).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as SSEEvent;
      } catch {
        // Malformed event — skip
      }
    }
  }
  // Flush any bytes held by the decoder for incomplete multibyte sequences
  buffer += decoder.decode();
  // Flush any remaining buffer
  const trimmed = buffer.trim();
  if (trimmed.startsWith("data:")) {
    const json = trimmed.slice("data:".length).trim();
    if (json) {
      try {
        yield JSON.parse(json) as SSEEvent;
      } catch {
        // Malformed event — skip
      }
    }
  }
}
