/**
 * Right-panel output display for the playground.
 *
 * Shows:
 * - Accumulated streaming response text in a <pre>
 * - Token counts (input, output, cache_read) and latency
 * - "Try parse as JSON" toggle — attempts JSON.parse and shows either the
 *   formatted tree or the parse error
 * - Error banner if the stream emitted an ``error`` event
 */
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type PlaygroundUsage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  latency_ms: number;
};

type Props = {
  content: string;
  usage: PlaygroundUsage | null;
  error: string | null;
  isStreaming: boolean;
};

export function PlaygroundOutput({ content, usage, error, isStreaming }: Props) {
  const [tryJson, setTryJson] = useState(false);

  const jsonResult = useMemo(() => {
    if (!tryJson || !content) return null;
    try {
      const parsed = JSON.parse(content);
      return { ok: true, value: JSON.stringify(parsed, null, 2) };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }, [tryJson, content]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Response</CardTitle>
          <div className="flex items-center gap-2">
            {isStreaming && <Badge>streaming…</Badge>}
            {usage && (
              <Badge variant="secondary" className="tabular-nums">
                {usage.latency_ms} ms
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <pre className="text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-2 rounded mb-3 whitespace-pre-wrap">
              {error}
            </pre>
          )}
          <pre className="font-mono text-xs whitespace-pre-wrap min-h-[200px] max-h-[50vh] overflow-auto bg-muted/30 p-3 rounded">
            {content || (
              <span className="text-muted-foreground">
                (No response yet — click Send)
              </span>
            )}
          </pre>
        </CardContent>
      </Card>

      {usage && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Usage</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1 tabular-nums">
            <div>Input tokens: {usage.input_tokens}</div>
            <div>Output tokens: {usage.output_tokens}</div>
            <div>Cache read: {usage.cache_read_tokens}</div>
            <div>Latency: {usage.latency_ms} ms</div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Try parse as JSON</CardTitle>
          <Button
            size="sm"
            variant={tryJson ? "default" : "outline"}
            onClick={() => setTryJson((v) => !v)}
          >
            {tryJson ? "On" : "Off"}
          </Button>
        </CardHeader>
        {tryJson && jsonResult && (
          <CardContent>
            {jsonResult.ok ? (
              <pre className="font-mono text-xs whitespace-pre-wrap max-h-[40vh] overflow-auto bg-muted/30 p-3 rounded">
                {jsonResult.value}
              </pre>
            ) : (
              <pre className="font-mono text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-3 rounded whitespace-pre-wrap">
                Parse error: {jsonResult.error}
              </pre>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
