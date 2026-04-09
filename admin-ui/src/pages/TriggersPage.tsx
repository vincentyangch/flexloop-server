import type { ComponentType } from "react";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Database,
  HardDriveDownload,
  Loader2,
  RefreshCw,
  RotateCcw,
  Scissors,
  Send,
  Sprout,
  Trash2,
  Trophy,
  Wrench,
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
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { parseSSE } from "@/lib/sseReader";
import { cn } from "@/lib/utils";

type TriggerName =
  | "reseed-exercises"
  | "run-migrations"
  | "backup"
  | "test-ai"
  | "reload-prompts"
  | "vacuum-db"
  | "clear-sessions"
  | "recompute-prs"
  | "clear-ai-usage";

type TriggerDef = {
  name: TriggerName;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  confirm: "none" | "simple" | "strong";
  confirmLabel?: string;
  accentClassName: string;
  sse?: boolean;
};

type TriggerResult = Record<string, unknown>;

type SseProgress = {
  percent: number;
  currentStep: string;
  message: string;
};

const TRIGGERS: TriggerDef[] = [
  {
    name: "reseed-exercises",
    title: "Re-seed exercises",
    description: "Reload exercise metadata from the bundled exercise details file.",
    icon: Sprout,
    confirm: "simple",
    accentClassName: "bg-emerald-500/10 text-emerald-700",
  },
  {
    name: "run-migrations",
    title: "Run pending migrations",
    description: "Apply any unapplied Alembic migrations to the current database.",
    icon: Database,
    confirm: "simple",
    accentClassName: "bg-sky-500/10 text-sky-700",
  },
  {
    name: "backup",
    title: "Backup now",
    description: "Create an immediate database backup in the server backup directory.",
    icon: HardDriveDownload,
    confirm: "none",
    accentClassName: "bg-indigo-500/10 text-indigo-700",
  },
  {
    name: "test-ai",
    title: "Test AI provider",
    description: "Send a small health-check request to the configured AI provider.",
    icon: Send,
    confirm: "none",
    accentClassName: "bg-amber-500/10 text-amber-700",
  },
  {
    name: "reload-prompts",
    title: "Reload prompts",
    description: "Clear prompt cache state so the next request reads fresh prompt files.",
    icon: RefreshCw,
    confirm: "none",
    accentClassName: "bg-cyan-500/10 text-cyan-700",
  },
  {
    name: "vacuum-db",
    title: "Vacuum database",
    description: "Reclaim unused disk space and compact the SQLite database file.",
    icon: Scissors,
    confirm: "simple",
    accentClassName: "bg-slate-500/10 text-slate-700",
  },
  {
    name: "clear-sessions",
    title: "Clear all sessions",
    description: "Log out all admins. You will be logged out and need to sign in again.",
    icon: Trash2,
    confirm: "strong",
    confirmLabel: "CLEAR SESSIONS",
    accentClassName: "bg-rose-500/10 text-rose-700",
  },
  {
    name: "recompute-prs",
    title: "Recompute PRs",
    description: "Re-detect personal records across all workout history with live progress.",
    icon: Trophy,
    confirm: "simple",
    accentClassName: "bg-violet-500/10 text-violet-700",
    sse: true,
  },
  {
    name: "clear-ai-usage",
    title: "Clear AI usage",
    description: "Delete all AI token and call count records from the admin analytics tables.",
    icon: RotateCcw,
    confirm: "strong",
    confirmLabel: "CLEAR USAGE",
    accentClassName: "bg-orange-500/10 text-orange-700",
  },
];

function successMessage(name: TriggerName, data: TriggerResult): string {
  switch (name) {
    case "backup":
      return `Backup created: ${String(data.filename ?? "unknown file")}`;
    case "test-ai":
      return `AI test completed in ${String(data.latency_ms ?? 0)} ms`;
    case "reload-prompts":
      return String(data.message ?? "Prompt cache cleared");
    case "reseed-exercises":
      return `Updated ${String(data.updated ?? 0)} exercises`;
    case "run-migrations":
    case "vacuum-db":
      return String(data.message ?? "Completed successfully");
    case "clear-sessions":
      return `Cleared ${String(data.deleted ?? 0)} sessions`;
    case "clear-ai-usage":
      return `Deleted ${String(data.deleted ?? 0)} usage rows`;
    default:
      return "Completed successfully";
  }
}

function failureMessage(name: TriggerName, error: unknown): string {
  if (error instanceof ApiError) {
    return `${name}: ${error.detail}`;
  }
  if (error instanceof Error) {
    return `${name}: ${error.message}`;
  }
  return `${name}: request failed`;
}

export function TriggersPage() {
  const [confirmTrigger, setConfirmTrigger] = useState<TriggerDef | null>(null);
  const [strongConfirmText, setStrongConfirmText] = useState("");
  const [runningTrigger, setRunningTrigger] = useState<TriggerName | null>(null);
  const [sseProgress, setSseProgress] = useState<SseProgress | null>(null);

  const triggerMutation = useMutation<TriggerResult, Error, TriggerName>({
    mutationFn: (name) => api.post<TriggerResult>(`/api/admin/triggers/${name}`),
    onSuccess: (data, name) => {
      setRunningTrigger(null);
      if (String(data.status ?? "ok") !== "ok") {
        toast.error(`${name}: ${String(data.error ?? "failed")}`);
        return;
      }

      toast.success(successMessage(name, data));
      if (name === "clear-sessions") {
        window.setTimeout(() => {
          window.location.assign("/admin/login");
        }, 300);
      }
    },
    onError: (error, name) => {
      setRunningTrigger(null);
      toast.error(failureMessage(name, error));
    },
  });

  async function runSseTrigger(name: TriggerName) {
    setRunningTrigger(name);
    setSseProgress({
      percent: 0,
      currentStep: "Starting",
      message: "Preparing recompute job…",
    });

    try {
      const response = await fetch(`/api/admin/triggers/${name}`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "text/event-stream" },
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      let sawDone = false;
      for await (const event of parseSSE(response)) {
        if (event.type === "progress") {
          setSseProgress({
            percent: Number(event.percent ?? 0),
            currentStep: String(event.current_step ?? "In progress"),
            message: String(event.message ?? ""),
          });
        } else if (event.type === "error") {
          throw new Error(String(event.error ?? "stream failed"));
        } else if (event.type === "done") {
          sawDone = true;
          const result = (event.result ?? {}) as TriggerResult;
          toast.success(
            `${name}: ${String(result.new_prs ?? 0)} new PRs found across ${String(result.sets_checked ?? 0)} checked sets`,
          );
        }
      }

      if (!sawDone) {
        throw new Error("stream ended before completion");
      }
    } catch (error) {
      toast.error(failureMessage(name, error));
    } finally {
      setRunningTrigger(null);
      setSseProgress(null);
    }
  }

  function fireTrigger(trigger: TriggerDef) {
    setConfirmTrigger(null);
    setStrongConfirmText("");

    if (trigger.sse) {
      void runSseTrigger(trigger.name);
      return;
    }

    setRunningTrigger(trigger.name);
    triggerMutation.mutate(trigger.name);
  }

  function handleRun(trigger: TriggerDef) {
    if (trigger.confirm === "none") {
      fireTrigger(trigger);
      return;
    }

    setConfirmTrigger(trigger);
    setStrongConfirmText("");
  }

  const isBusy = runningTrigger !== null;
  const strongConfirmMatches =
    confirmTrigger?.confirm !== "strong" ||
    strongConfirmText === confirmTrigger.confirmLabel;

  return (
    <div className="space-y-6 p-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Triggers</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Manual maintenance actions for operator workflows. Confirm dialogs are
          enforced here in the UI, and long-running work streams live progress
          before the final result toast.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {TRIGGERS.map((trigger) => {
          const Icon = trigger.icon;
          const isRunning = runningTrigger === trigger.name;

          return (
            <Card key={trigger.name} className="h-full">
              <CardHeader className="space-y-3">
                <div
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-xl",
                    trigger.accentClassName,
                  )}
                >
                  <Icon className="h-5 w-5" />
                </div>
                <div className="space-y-1">
                  <CardTitle>{trigger.title}</CardTitle>
                  <CardDescription>{trigger.description}</CardDescription>
                </div>
              </CardHeader>
              <CardFooter className="mt-auto flex items-center justify-between gap-3">
                <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  {trigger.confirm === "strong"
                    ? "Type to confirm"
                    : trigger.confirm === "simple"
                      ? "Confirm first"
                      : "Runs immediately"}
                </div>
                <Button
                  size="sm"
                  onClick={() => handleRun(trigger)}
                  disabled={isBusy}
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Running…
                    </>
                  ) : (
                    <>
                      <Wrench />
                      Run
                    </>
                  )}
                </Button>
              </CardFooter>
            </Card>
          );
        })}
      </div>

      <AlertDialog
        open={confirmTrigger !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmTrigger(null);
            setStrongConfirmText("");
          }
        }}
      >
        <AlertDialogContent size="default">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Run {confirmTrigger?.title ?? "trigger"}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmTrigger?.description}
              {confirmTrigger?.confirm === "strong" ? (
                <>
                  {" "}
                  Type{" "}
                  <code className="font-mono font-semibold">
                    {confirmTrigger.confirmLabel}
                  </code>{" "}
                  to confirm this destructive action.
                </>
              ) : (
                " This action starts immediately after confirmation."
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {confirmTrigger?.confirm === "strong" ? (
            <Input
              value={strongConfirmText}
              onChange={(event) => setStrongConfirmText(event.target.value)}
              placeholder={confirmTrigger.confirmLabel}
              className="font-mono"
            />
          ) : null}

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!strongConfirmMatches}
              onClick={() => {
                if (confirmTrigger) {
                  fireTrigger(confirmTrigger);
                }
              }}
            >
              Run trigger
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={sseProgress !== null}>
        <DialogContent className="sm:max-w-md" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Recomputing personal records</DialogTitle>
            <DialogDescription>
              Streaming progress from the backend while every workout set is
              re-evaluated.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="overflow-hidden rounded-full bg-muted">
              <div
                className="h-2 rounded-full bg-primary transition-[width] duration-300"
                style={{ width: `${sseProgress?.percent ?? 0}%` }}
              />
            </div>
            <div className="space-y-1">
              <div className="text-sm font-medium">
                {sseProgress?.currentStep ?? "Starting"}
              </div>
              <div className="text-sm text-muted-foreground">
                {sseProgress?.message ?? "Preparing…"}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
