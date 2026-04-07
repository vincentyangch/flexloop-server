import { useHealth } from "@/hooks/useHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatBytes(bytes: number | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n >= 10 ? 0 : 1)} ${units[i]}`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function DashboardPage() {
  const health = useHealth();

  if (health.isLoading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }
  if (health.isError || !health.data) {
    return <div className="text-destructive">Failed to load health data.</div>;
  }

  const h = health.data;
  const statusColor =
    h.status === "healthy"
      ? "text-green-500"
      : h.status === "degraded"
      ? "text-yellow-500"
      : "text-red-500";

  const rowCounts = h.components.database.table_row_counts ?? {};

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>
            <span className={`${statusColor} mr-2`}>●</span>
            System {h.status}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-muted-foreground text-xs uppercase">Uptime</div>
              <div className="font-medium">{formatUptime(h.system.uptime_seconds)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">DB size</div>
              <div className="font-medium">
                {formatBytes(h.components.database.db_size_bytes)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Recent errors</div>
              <div className="font-medium">{h.recent_errors.length}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Python</div>
              <div className="font-medium">{h.system.python}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Users" value={rowCounts.users ?? 0} />
        <StatCard label="Workouts" value={rowCounts.workout_sessions ?? 0} />
        <StatCard label="Plans" value={rowCounts.plans ?? 0} />
        <StatCard label="Exercises" value={rowCounts.exercises ?? 0} />
      </div>

      {h.recent_errors.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent errors</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {h.recent_errors.slice(0, 5).map((e, i) => (
                <li key={i} className="flex gap-3">
                  <span className="text-muted-foreground">{e.timestamp.slice(11, 19)}</span>
                  <span className="font-medium uppercase">{e.level}</span>
                  <span className="truncate">{e.message}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-muted-foreground text-xs uppercase">{label}</div>
        <div className="text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}
