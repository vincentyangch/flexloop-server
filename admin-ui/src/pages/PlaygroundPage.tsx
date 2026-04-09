/**
 * Admin AI Playground page.
 *
 * Two-panel layout: PlaygroundInput on the left, PlaygroundOutput on the
 * right. Send button fires a POST to /api/admin/playground/run and reads
 * the SSE response via parseSSE from lib/sseReader.
 *
 * Phase 4c Chunk 3: free-form mode only. Chunk 4 adds template mode and
 * the "Open in playground →" query param handler.
 */
import { useState } from "react";

import { PlaygroundInput } from "@/components/playground/PlaygroundInput";
import type { PlaygroundRunPayload } from "@/components/playground/PlaygroundInput";
import { PlaygroundOutput } from "@/components/playground/PlaygroundOutput";
import type { PlaygroundUsage } from "@/components/playground/PlaygroundOutput";
import { parseSSE } from "@/lib/sseReader";

export function PlaygroundPage() {
  const [content, setContent] = useState("");
  const [usage, setUsage] = useState<PlaygroundUsage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const send = async (payload: PlaygroundRunPayload) => {
    setContent("");
    setUsage(null);
    setError(null);
    setIsStreaming(true);
    try {
      const res = await fetch("/api/admin/playground/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      });
      if (!res.ok) {
        const text = await res.text();
        setError(`HTTP ${res.status}: ${text}`);
        setIsStreaming(false);
        return;
      }
      for await (const event of parseSSE(res)) {
        if (event.type === "content") {
          setContent((prev) => prev + (event.delta as string));
        } else if (event.type === "usage") {
          setUsage({
            input_tokens: (event.input_tokens as number) ?? 0,
            output_tokens: (event.output_tokens as number) ?? 0,
            cache_read_tokens: (event.cache_read_tokens as number) ?? 0,
            latency_ms: (event.latency_ms as number) ?? 0,
          });
        } else if (event.type === "error") {
          setError((event.error as string) ?? "unknown error");
        } else if (event.type === "done") {
          // Done — nothing to do, the stream will end on its own
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Playground</h1>
        <p className="text-sm text-muted-foreground">
          Test prompts against the configured AI provider. The "Try parse as
          JSON" toggle is your friend for catching malformed responses.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <PlaygroundInput onSend={send} isStreaming={isStreaming} />
        <PlaygroundOutput
          content={content}
          usage={usage}
          error={error}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
