/**
 * Modal showing the unified diff between the current version and another
 * version selected from a dropdown.
 *
 * Uses the shadcn Dialog primitive (already installed). Diff text renders
 * as a <pre> with per-line CSS coloring: `+` green, `-` red, `@@` gray.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type DiffResponse = components["schemas"]["DiffResponse"];

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  currentVersion: string;
  availableVersions: string[];
};

function renderDiffLine(line: string, i: number) {
  let className = "text-muted-foreground";
  if (line.startsWith("+") && !line.startsWith("+++")) {
    className = "text-green-600 dark:text-green-400";
  } else if (line.startsWith("-") && !line.startsWith("---")) {
    className = "text-red-600 dark:text-red-400";
  } else if (line.startsWith("@@")) {
    className = "text-blue-600 dark:text-blue-400";
  }
  return (
    <div key={i} className={className}>
      {line || " "}
    </div>
  );
}

export function DiffDialog({
  open,
  onOpenChange,
  name,
  currentVersion,
  availableVersions,
}: Props) {
  // Default to comparing against the version just before the current one
  const otherVersions = availableVersions.filter((v) => v !== currentVersion);
  const [from, setFrom] = useState<string>(
    () => otherVersions[0] ?? currentVersion,
  );

  const diffQuery = useQuery({
    queryKey: ["admin", "prompts", "diff", name, from, currentVersion],
    queryFn: () =>
      api.get<DiffResponse>(
        `/api/admin/prompts/${name}/diff?from=${from}&to=${currentVersion}`,
      ),
    enabled: open && from !== currentVersion,
  });

  const lines = useMemo(
    () => (diffQuery.data?.diff ?? "").split("\n"),
    [diffQuery.data],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            Diff: {name} / {from} → {currentVersion}
          </DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <span className="text-sm">Compare against:</span>
          <Select value={from} onValueChange={setFrom}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {otherVersions.map((v) => (
                <SelectItem key={v} value={v}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <pre className="font-mono text-xs whitespace-pre-wrap max-h-[50vh] overflow-auto bg-muted/30 p-3 rounded">
          {diffQuery.isLoading && "Loading diff…"}
          {diffQuery.isError && "Failed to load diff."}
          {diffQuery.data && lines.map((l, i) => renderDiffLine(l, i))}
          {!diffQuery.isLoading && lines.length <= 1 && diffQuery.data?.diff === "" && (
            <span className="text-muted-foreground">No differences.</span>
          )}
        </pre>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
