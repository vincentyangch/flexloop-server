import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  HardDriveDownload,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";

type Backup = {
  filename: string;
  size_bytes: number;
  created_at: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function BackupPage() {
  const qc = useQueryClient();
  const [dragOver, setDragOver] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<Backup | null>(null);
  const [restoreConfirmText, setRestoreConfirmText] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["admin", "backups"],
    queryFn: () => api.get<Backup[]>("/api/admin/backups"),
  });

  const createMut = useMutation({
    mutationFn: () => api.post<Backup>("/api/admin/backups"),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["admin", "backups"] });
      toast.success(`Backup created: ${data.filename}`);
    },
    onError: () => toast.error("Failed to create backup"),
  });

  const uploadMut = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/admin/backups/upload", {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail);
      }
      return res.json() as Promise<Backup>;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["admin", "backups"] });
      toast.success(`Uploaded: ${data.filename}`);
    },
    onError: (err: Error) => toast.error(`Upload failed: ${err.message}`),
  });

  const restoreMut = useMutation({
    mutationFn: (filename: string) =>
      api.post<{
        status: string;
        restored_from: string;
        safety_backup: string;
      }>(`/api/admin/backups/${filename}/restore`),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["admin", "backups"] });
      toast.success(
        `Restored from ${data.restored_from}. Safety backup: ${data.safety_backup}`,
      );
      setRestoreTarget(null);
      setRestoreConfirmText("");
    },
    onError: () => {
      toast.error("Restore failed");
      setRestoreTarget(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (filename: string) => api.delete(`/api/admin/backups/${filename}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "backups"] });
      toast.success("Backup deleted");
      setDeleteTarget(null);
    },
    onError: () => toast.error("Delete failed"),
  });

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadMut.mutate(file);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadMut.mutate(file);
    e.target.value = "";
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backup & Restore</h1>
        <div className="flex gap-2">
          <Button
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending}
          >
            <Plus className="mr-2 h-4 w-4" />
            {createMut.isPending ? "Creating…" : "Create backup"}
          </Button>
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25"
        }`}
      >
        <p className="text-sm text-muted-foreground">
          Drag &amp; drop a <code>.db</code> backup file here, or{" "}
          <label className="cursor-pointer text-primary underline">
            browse
            <input
              type="file"
              accept=".db"
              className="hidden"
              onChange={handleFileInput}
            />
          </label>
        </p>
        {uploadMut.isPending && (
          <p className="mt-2 text-sm text-muted-foreground">Uploading…</p>
        )}
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : backups.length === 0 ? (
        <p className="text-muted-foreground">No backups yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Filename</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Age</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {backups.map((b) => (
              <TableRow key={b.filename}>
                <TableCell className="font-mono text-sm">{b.filename}</TableCell>
                <TableCell>{formatBytes(b.size_bytes)}</TableCell>
                <TableCell>{new Date(b.created_at).toLocaleString()}</TableCell>
                <TableCell>{formatAge(b.created_at)}</TableCell>
                <TableCell className="space-x-1 text-right">
                  <Button variant="ghost" size="icon" asChild>
                    <a
                      href={`/api/admin/backups/${b.filename}/download`}
                      download
                    >
                      <HardDriveDownload className="h-4 w-4" />
                    </a>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setRestoreTarget(b)}
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDeleteTarget(b.filename)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <AlertDialog
        open={restoreTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRestoreTarget(null);
            setRestoreConfirmText("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore backup?</AlertDialogTitle>
            <AlertDialogDescription>
              This will replace the current database with{" "}
              <code className="font-mono">{restoreTarget?.filename}</code> (
              {restoreTarget ? formatBytes(restoreTarget.size_bytes) : ""}, created{" "}
              {restoreTarget ? formatAge(restoreTarget.created_at) : ""}). A
              safety backup of the current state will be created first. Type the
              backup filename to confirm.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={restoreConfirmText}
            onChange={(e) => setRestoreConfirmText(e.target.value)}
            placeholder={restoreTarget?.filename ?? ""}
            className="font-mono text-sm"
          />
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={
                restoreConfirmText !== restoreTarget?.filename ||
                restoreMut.isPending
              }
              onClick={() =>
                restoreTarget && restoreMut.mutate(restoreTarget.filename)
              }
            >
              {restoreMut.isPending ? "Restoring…" : "Restore"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete backup?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete{" "}
              <code className="font-mono">{deleteTarget}</code>. This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleteMut.isPending}
              onClick={() => deleteTarget && deleteMut.mutate(deleteTarget)}
            >
              {deleteMut.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
