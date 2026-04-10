import type { ReactNode } from "react";
import { useHealth } from "@/hooks/useHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "healthy"
      ? "default"
      : status === "degraded" || status === "unconfigured"
        ? "secondary"
        : "destructive";
  return <Badge variant={variant}>{status}</Badge>;
}

export function HealthPage() {
  const health = useHealth();
  const qc = useQueryClient();

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "health"] });

  if (health.isLoading) return <div>Loading...</div>;
  if (health.isError || !health.data)
    return <div className="text-destructive">Failed to load health data.</div>;

  const h = health.data;
  const { database, ai_provider, disk, memory, backups, migrations } =
    h.components;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Health</h1>
        <Button onClick={refresh} variant="outline" size="sm">
          Re-check now
        </Button>
      </div>

      {/* Database */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Database
            <StatusBadge status={database.status} />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Query latency" value={`${database.ms ?? 0} ms`} />
          <KV
            label="Size"
            value={formatBytes(database.db_size_bytes ?? 0)}
          />
          {database.error && (
            <KV label="Error" value={<span className="text-destructive">{database.error}</span>} />
          )}
          <div className="mt-3">
            <div className="text-xs uppercase text-muted-foreground mb-1">
              Table row counts
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              {Object.entries(database.table_row_counts ?? {}).map(
                ([k, v]) => (
                  <div key={k} className="flex justify-between border-b py-1">
                    <span className="text-muted-foreground">{k}</span>
                    <span>{v}</span>
                  </div>
                )
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* AI Provider */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            AI Provider
            <StatusBadge status={ai_provider.status} />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Provider" value={ai_provider.provider} />
          <KV label="Model" value={ai_provider.model} />
          <KV label="API key configured" value={ai_provider.has_key ? "Yes" : "No"} />
          <KV label="Base URL reachable" value={ai_provider.reachable ? "Yes" : "No"} />
          {ai_provider.cached && (
            <KV label="Cached" value="Yes (60s TTL)" />
          )}
          {ai_provider.error && (
            <KV label="Error" value={<span className="text-destructive">{ai_provider.error}</span>} />
          )}
        </CardContent>
      </Card>

      {/* Disk & Memory side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Disk</CardTitle>
          </CardHeader>
          <CardContent>
            {disk.error ? (
              <div className="text-sm text-destructive">{disk.error}</div>
            ) : (
              <>
                <KV label="Free" value={formatBytes(disk.free_bytes ?? 0)} />
                <KV label="Total" value={formatBytes(disk.total_bytes ?? 0)} />
                <KV label="Used" value={`${disk.used_pct ?? 0}%`} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Memory</CardTitle>
          </CardHeader>
          <CardContent>
            {memory.error ? (
              <div className="text-sm text-destructive">{memory.error}</div>
            ) : (
              <>
                <KV label="RSS (peak)" value={formatBytes(memory.rss_bytes ?? 0)} />
                {memory.vms_bytes != null && (
                  <KV label="VMS" value={formatBytes(memory.vms_bytes)} />
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Backups & Migrations side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Backups</CardTitle>
          </CardHeader>
          <CardContent>
            {backups.error ? (
              <div className="text-sm text-destructive">{backups.error}</div>
            ) : (
              <>
                <KV label="Count" value={backups.count ?? 0} />
                {backups.last_at && (
                  <KV
                    label="Latest"
                    value={new Date(backups.last_at).toLocaleString()}
                  />
                )}
                <KV label="Total size" value={formatBytes(backups.total_bytes ?? 0)} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              Migrations
              {migrations.in_sync != null && (
                <Badge variant={migrations.in_sync ? "default" : "destructive"}>
                  {migrations.in_sync ? "in sync" : "out of sync"}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {migrations.error ? (
              <div className="text-sm text-destructive">{migrations.error}</div>
            ) : (
              <>
                <KV
                  label="Current"
                  value={
                    <span className="font-mono text-xs">
                      {migrations.current_rev?.slice(0, 12) ?? "none"}
                    </span>
                  }
                />
                <KV
                  label="Head"
                  value={
                    <span className="font-mono text-xs">
                      {migrations.head_rev?.slice(0, 12) ?? "none"}
                    </span>
                  }
                />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* System */}
      <Card>
        <CardHeader>
          <CardTitle>System</CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Python" value={h.system.python} />
          <KV label="FastAPI" value={h.system.fastapi} />
          <KV label="Uvicorn" value={h.system.uvicorn} />
          <KV label="OS" value={h.system.os} />
          <KV label="Hostname" value={h.system.hostname} />
          <KV label="Uptime" value={`${h.system.uptime_seconds} s`} />
        </CardContent>
      </Card>

      {/* Recent Errors */}
      <Card>
        <CardHeader>
          <CardTitle>Recent errors ({h.recent_errors.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {h.recent_errors.length === 0 && (
            <div className="text-sm text-muted-foreground">None.</div>
          )}
          <ul className="space-y-3 text-sm">
            {h.recent_errors.map((e, i) => (
              <li key={i} className="border-l-2 border-destructive pl-3">
                <div className="font-mono text-xs text-muted-foreground">
                  {e.timestamp} · {e.level} · {e.logger}
                </div>
                <div>{e.message}</div>
                {e.exception && (
                  <pre className="mt-1 text-xs overflow-x-auto bg-muted p-2 rounded">
                    {e.exception}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between border-b py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
