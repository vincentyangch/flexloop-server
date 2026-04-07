import { useSessions, useRevokeSession } from "@/hooks/useSessions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SessionsPage() {
  const sessions = useSessions();
  const revoke = useRevokeSession();

  if (sessions.isLoading) return <div>Loading...</div>;
  if (sessions.isError || !sessions.data) return <div>Failed to load sessions.</div>;

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Active sessions</h1>
      <Card>
        <CardHeader>
          <CardTitle>Your sessions ({sessions.data.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {sessions.data.map((s) => (
              <li key={s.id} className="py-3 flex items-center justify-between">
                <div className="text-sm">
                  <div className="font-medium">
                    {s.user_agent ?? "Unknown client"}
                    {s.is_current && (
                      <span className="ml-2 text-xs text-green-500">(current)</span>
                    )}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {s.ip_address ?? "unknown IP"} · created{" "}
                    {new Date(s.created_at).toLocaleString()} · expires{" "}
                    {new Date(s.expires_at).toLocaleString()}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(s.id)}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
