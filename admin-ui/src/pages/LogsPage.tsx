import { startTransition, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Circle, Search } from "lucide-react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { parseSSE } from "@/lib/sseReader";
import { cn } from "@/lib/utils";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
const HISTORY_LIMIT = 500;
const LIVE_TAIL_CAP = 5000;

type LogLevel = (typeof LEVELS)[number];

type LogRecord = {
  id: number;
  timestamp: string;
  level: LogLevel;
  logger: string;
  message: string;
  exception?: string | null;
  extra?: Record<string, unknown> | null;
};

const levelRowClass: Record<LogLevel, string> = {
  DEBUG: "text-muted-foreground",
  INFO: "",
  WARNING: "text-yellow-500",
  ERROR: "text-red-500",
  CRITICAL: "font-bold text-red-500",
};

const levelBadgeVariant: Record<LogLevel, React.ComponentProps<typeof Badge>["variant"]> = {
  DEBUG: "outline",
  INFO: "secondary",
  WARNING: "default",
  ERROR: "destructive",
  CRITICAL: "destructive",
};

function formatLogTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatFullTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function isLogLevel(value: unknown): value is LogLevel {
  return typeof value === "string" && (LEVELS as readonly string[]).includes(value);
}

function isLogRecord(value: unknown): value is LogRecord {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number"
    && typeof candidate.timestamp === "string"
    && isLogLevel(candidate.level)
    && typeof candidate.logger === "string"
    && typeof candidate.message === "string"
  );
}

function mergeLogs(existing: LogRecord[], incoming: LogRecord[], cap?: number): LogRecord[] {
  if (incoming.length === 0) {
    return existing;
  }
  const seen = new Set(existing.map((record) => record.id));
  const next = [...existing];
  for (const record of incoming) {
    if (seen.has(record.id)) {
      continue;
    }
    seen.add(record.id);
    next.push(record);
  }
  return cap && next.length > cap ? next.slice(-cap) : next;
}

export function LogsPage() {
  const [level, setLevel] = useState<LogLevel>("INFO");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [liveTail, setLiveTail] = useState(false);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [search]);

  useEffect(() => {
    setLogs([]);
    setExpandedId(null);
  }, [level, debouncedSearch]);

  const logsQuery = useQuery({
    queryKey: ["admin", "logs", level, debouncedSearch, HISTORY_LIMIT],
    queryFn: () =>
      api.get<LogRecord[]>("/api/admin/logs", {
        level,
        search: debouncedSearch || undefined,
        limit: HISTORY_LIMIT,
      }),
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!logsQuery.data) {
      return;
    }
    setLogs(logsQuery.data);
  }, [logsQuery.data]);

  useEffect(() => {
    if (!liveTail) {
      abortRef.current?.abort();
      abortRef.current = null;
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const run = async () => {
      try {
        const params = new URLSearchParams({
          level,
          limit: String(HISTORY_LIMIT),
        });
        if (debouncedSearch) {
          params.set("search", debouncedSearch);
        }

        const response = await fetch(`/api/admin/logs/stream?${params.toString()}`, {
          credentials: "include",
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        for await (const event of parseSSE(response)) {
          if (!isLogRecord(event)) {
            continue;
          }
          startTransition(() => {
            setLogs((current) => mergeLogs(current, [event], LIVE_TAIL_CAP));
          });
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        console.error("logs live-tail stream failed", error);
      }
    };

    void run();

    return () => {
      controller.abort();
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    };
  }, [debouncedSearch, level, liveTail]);

  useEffect(() => {
    if (!liveTail || logs.length === 0) {
      return;
    }
    virtuosoRef.current?.scrollToIndex({
      index: logs.length - 1,
      align: "end",
      behavior: "auto",
    });
  }, [liveTail, logs.length]);

  const isLoading = logsQuery.isLoading && logs.length === 0;
  const isError = logsQuery.isError;
  const queryError = logsQuery.error instanceof Error ? logsQuery.error.message : null;

  return (
    <div className="flex min-h-[calc(100svh-8rem)] flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Logs</h1>
          <p className="text-sm text-muted-foreground">
            Inspect recent admin logs, filter by severity, and follow the live tail.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground md:self-auto">
          <span>{logs.length} loaded</span>
          <span className="text-border">/</span>
          <span>{liveTail ? "live tail on" : "history mode"}</span>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border bg-card/70 p-3 backdrop-blur-sm md:grid-cols-[160px_minmax(0,1fr)_auto]">
        <div className="space-y-1">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Severity
          </div>
          <Select value={level} onValueChange={(value) => setLevel(value as LogLevel)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEVELS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Search
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9"
              placeholder="message, logger, exception"
            />
          </div>
        </div>

        <div className="flex items-end">
          <Button
            variant={liveTail ? "default" : "outline"}
            className="w-full md:w-auto"
            onClick={() => setLiveTail((current) => !current)}
          >
            <Circle
              className={cn(
                "mr-2 h-3.5 w-3.5",
                liveTail ? "animate-pulse fill-current text-red-500" : "text-muted-foreground",
              )}
            />
            Live tail
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border bg-card shadow-sm">
        {isLoading ? (
          <div className="p-4 text-sm text-muted-foreground">Loading logs…</div>
        ) : isError ? (
          <div className="p-4 text-sm text-destructive">
            Failed to load logs{queryError ? `: ${queryError}` : "."}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">No log records match the current filters.</div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={logs}
            style={{ height: "100%" }}
            itemContent={(_index, record) => (
              <article
                className={cn(
                  "cursor-pointer border-b border-border/70 px-4 py-3 transition-colors hover:bg-muted/40",
                  levelRowClass[record.level],
                  expandedId === record.id && "bg-muted/30",
                )}
                onClick={() => {
                  setExpandedId((current) => (current === record.id ? null : record.id));
                }}
              >
                <div className="flex items-start gap-3 text-sm">
                  <div className="w-22 shrink-0 pt-0.5 font-mono text-[11px] tracking-wide text-muted-foreground">
                    {formatLogTime(record.timestamp)}
                  </div>
                  <Badge
                    variant={levelBadgeVariant[record.level]}
                    className="mt-0.5 shrink-0 font-mono text-[10px] tracking-[0.18em]"
                  >
                    {record.level}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="break-words">{record.message}</div>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                      {record.logger}
                    </div>
                  </div>
                </div>

                {expandedId === record.id && (
                  <div className="mt-3 rounded-lg border bg-background/80 p-3 text-xs">
                    <div className="grid gap-1 md:grid-cols-[110px_minmax(0,1fr)]">
                      <span className="font-semibold text-muted-foreground">Logger</span>
                      <span className="font-mono break-all">{record.logger}</span>
                      <span className="font-semibold text-muted-foreground">Timestamp</span>
                      <span className="font-mono">{formatFullTimestamp(record.timestamp)}</span>
                    </div>

                    {record.exception && (
                      <div className="mt-3 space-y-1">
                        <div className="font-semibold text-muted-foreground">Exception</div>
                        <pre className="overflow-x-auto rounded-md bg-destructive/10 p-3 font-mono text-[11px] text-red-500">
                          {record.exception}
                        </pre>
                      </div>
                    )}

                    {record.extra && Object.keys(record.extra).length > 0 && (
                      <div className="mt-3 space-y-1">
                        <div className="font-semibold text-muted-foreground">Extra</div>
                        <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-[11px] text-foreground">
                          {JSON.stringify(record.extra, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </article>
            )}
          />
        )}
      </div>
    </div>
  );
}
