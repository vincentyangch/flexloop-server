import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";
import { cn } from "@/lib/utils";

type CodexStatus = components["schemas"]["CodexStatusResponse"];

const CODEX_STATUS_KEY = ["admin", "config", "codex-status"];

type Props = {
  className?: string;
  title?: string;
  size?: "default" | "sm";
};

export function CodexStatusPanel({
  className,
  title = "Codex session",
  size = "sm",
}: Props) {
  const query = useQuery({
    queryKey: CODEX_STATUS_KEY,
    queryFn: () => api.get<CodexStatus>("/api/admin/config/codex-status"),
  });

  const statusTone = getStatusTone(query.data?.status);
  const refreshTone = getRefreshTone(query.data?.status);
  const authMode = getAuthModeBadge(query.data?.auth_mode);
  const queryError =
    query.isError && query.error instanceof Error
      ? query.error.message
      : "Failed to load Codex status.";

  return (
    <Card size={size} className={className}>
      <CardHeader className="border-b">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-sm">
              <span
                className={cn("size-2.5 rounded-full", statusTone.dotClass)}
                aria-hidden="true"
              />
              <span>{title}</span>
            </CardTitle>
            <p className={cn("text-xs capitalize", statusTone.textClass)}>
              {query.data?.status?.replaceAll("_", " ") ??
                (query.isLoading ? "Checking…" : "Unavailable")}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            {query.isFetching ? "Checking…" : "Recheck"}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <Field
          label="File path"
          value={
            <code className="font-mono text-xs break-all">
              {query.data?.file_path ?? "—"}
            </code>
          }
        />
        <Field
          label="File exists"
          value={
            <span
              className={cn(
                "font-medium",
                query.data?.file_exists
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-destructive",
              )}
            >
              {query.data?.file_exists ? "✓" : "✗"}
            </span>
          }
        />
        <Field
          label="Auth mode"
          value={
            <Badge variant="outline" className={authMode.className}>
              {authMode.label}
            </Badge>
          }
        />
        <Field
          label="Last refresh"
          value={
            query.data?.last_refresh ? (
              <div className={cn("text-right", refreshTone)}>
                <div className="tabular-nums">
                  {new Date(query.data.last_refresh).toLocaleString()}
                </div>
                <div className="text-xs">
                  {formatDaysAgo(query.data.days_since_refresh)}
                </div>
              </div>
            ) : (
              "—"
            )
          }
        />
        <Field label="Account email" value={query.data?.account_email ?? "—"} />

        {(query.data?.error || queryError) && (
          <div className="rounded-md bg-destructive/10 p-3 text-xs text-destructive whitespace-pre-wrap">
            {query.data?.error ?? queryError}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b pb-3 text-sm last:border-b-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <div className="min-w-0 max-w-[70%] text-right font-medium">{value}</div>
    </div>
  );
}

function getStatusTone(status?: string | null) {
  switch (status) {
    case "healthy":
      return {
        dotClass: "bg-emerald-500",
        textClass: "text-emerald-700 dark:text-emerald-400",
      };
    case "degraded_yellow":
      return {
        dotClass: "bg-amber-500",
        textClass: "text-amber-700 dark:text-amber-400",
      };
    case "degraded_red":
    case "down":
      return {
        dotClass: "bg-red-500",
        textClass: "text-red-700 dark:text-red-400",
      };
    case "unconfigured":
    default:
      return {
        dotClass: "bg-slate-400 dark:bg-slate-500",
        textClass: "text-muted-foreground",
      };
  }
}

function getRefreshTone(status?: string | null) {
  switch (status) {
    case "healthy":
      return "text-emerald-700 dark:text-emerald-400";
    case "degraded_yellow":
      return "text-amber-700 dark:text-amber-400";
    case "degraded_red":
    case "down":
      return "text-red-700 dark:text-red-400";
    default:
      return "text-muted-foreground";
  }
}

function getAuthModeBadge(mode?: string | null) {
  switch (mode) {
    case "chatgpt":
      return {
        label: "chatgpt",
        className:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
      };
    case "api_key":
      return {
        label: "api_key",
        className:
          "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
      };
    case null:
    case undefined:
      return {
        label: "missing",
        className: "border-destructive/30 bg-destructive/10 text-destructive",
      };
    default:
      return {
        label: mode,
        className: "border-border bg-muted text-foreground",
      };
  }
}

function formatDaysAgo(daysSinceRefresh?: number | null) {
  if (daysSinceRefresh == null) {
    return "—";
  }

  const roundedDays = Math.round(daysSinceRefresh);
  return `${roundedDays} ${roundedDays === 1 ? "day" : "days"} ago`;
}
