import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardDriveDownload, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
