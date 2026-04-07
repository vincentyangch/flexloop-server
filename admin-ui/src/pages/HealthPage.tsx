import type { ReactNode } from "react";
import { useHealth } from "@/hooks/useHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";

export function HealthPage() {
  const health = useHealth();
  const qc = useQueryClient();

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "health"] });

  if (health.isLoading) return <div>Loading...</div>;
  if (health.isError || !health.data)
    return <div className="text-destructive">Failed to load health data.</div>;

  const h = health.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Health</h1>
        <Button onClick={refresh} variant="outline" size="sm">
          Re-check now
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Database</CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Status" value={h.components.database.status} />
          <KV label="Query latency" value={`${h.components.database.ms ?? 0} ms`} />
          <KV
            label="Size"
            value={`${((h.components.database.db_size_bytes ?? 0) / 1024).toFixed(1)} KB`}
          />
          <div className="mt-3">
            <div className="text-xs uppercase text-muted-foreground mb-1">
              Table row counts
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              {Object.entries(h.components.database.table_row_counts ?? {}).map(
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
