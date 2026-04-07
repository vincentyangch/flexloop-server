import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ChangePasswordPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: (vars: { current_password: string; new_password: string }) =>
      api.post("/api/admin/auth/change-password", vars),
    onSuccess: () => {
      setMsg("Password changed successfully.");
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (next !== confirm) {
      setMsg("New password and confirmation do not match.");
      return;
    }
    if (next.length < 8) {
      setMsg("New password must be at least 8 characters.");
      return;
    }
    change.mutate({ current_password: current, new_password: next });
  };

  return (
    <div className="max-w-md space-y-6">
      <h1 className="text-2xl font-semibold">Change password</h1>
      <Card>
        <CardHeader>
          <CardTitle>Update your password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current">Current password</Label>
              <Input
                id="current"
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new">New password</Label>
              <Input
                id="new"
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">Confirm new password</Label>
              <Input
                id="confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>
            {msg && <p className="text-sm">{msg}</p>}
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? "Updating..." : "Update password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
