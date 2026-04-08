/**
 * Plan detail page — the plans editor from spec §9.3.
 *
 * Top section: plan metadata (read-only summary with a link back to the
 * list for edits via EditSheet).
 * Middle section: per-day accordions with inline group/exercise/set
 * editing. Each day has its own Save button calling PUT /days/{n}.
 * Bottom: "Add day" button that opens a minimal prompt for the new
 * day_number/label and calls POST /days.
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DayAccordion } from "@/components/plan-editor/DayAccordion";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];
type PlanDayCreate = components["schemas"]["PlanDayAdminCreate"];
type PlanDayUpdate = components["schemas"]["PlanDayAdminUpdate"];
type PlanDayResponse = components["schemas"]["PlanDayAdminResponse"];

function planKey(id: number): (string | number)[] {
  return ["admin", "crud", "plans", "detail", id];
}

export function PlanDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const planId = Number(params.id);
  const qc = useQueryClient();
  const [addDayOpen, setAddDayOpen] = useState(false);
  const [newDayNumber, setNewDayNumber] = useState("");
  const [newDayLabel, setNewDayLabel] = useState("");
  const [savingDayNumber, setSavingDayNumber] = useState<number | null>(null);

  const planQuery = useQuery({
    queryKey: planKey(planId),
    queryFn: () => api.get<Plan>(`/api/admin/plans/${planId}`),
    enabled: !Number.isNaN(planId),
  });

  const invalidatePlan = () => {
    void qc.invalidateQueries({ queryKey: ["admin", "crud", "plans"] });
  };

  const saveDay = useMutation({
    mutationFn: async ({
      day_number,
      input,
    }: {
      day_number: number;
      input: PlanDayUpdate;
    }) =>
      api.put<PlanDayResponse>(
        `/api/admin/plans/${planId}/days/${day_number}`,
        input,
      ),
    onSuccess: () => {
      toast.success("Day saved");
      invalidatePlan();
      setSavingDayNumber(null);
    },
    onError: (e) => {
      toast.error(e instanceof Error ? e.message : "Save failed");
      setSavingDayNumber(null);
    },
  });

  const deleteDay = useMutation({
    mutationFn: async (day_number: number) =>
      api.delete(`/api/admin/plans/${planId}/days/${day_number}`),
    onSuccess: () => {
      toast.success("Day deleted");
      invalidatePlan();
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Delete failed"),
  });

  const addDay = useMutation({
    mutationFn: async (input: PlanDayCreate) =>
      api.post<PlanDayResponse>(`/api/admin/plans/${planId}/days`, input),
    onSuccess: () => {
      toast.success("Day added");
      invalidatePlan();
      setAddDayOpen(false);
      setNewDayNumber("");
      setNewDayLabel("");
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Add failed"),
  });

  if (Number.isNaN(planId)) {
    return <div className="p-6">Invalid plan id.</div>;
  }

  if (planQuery.isLoading) {
    return <div className="p-6">Loading…</div>;
  }

  if (planQuery.isError || !planQuery.data) {
    return (
      <div className="p-6 space-y-2">
        <p>Failed to load plan.</p>
        <Button onClick={() => navigate("/plans")}>Back to list</Button>
      </div>
    );
  }

  const plan = planQuery.data;
  const days = plan.days ?? [];

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate("/plans")}
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Back to plans
          </button>
          <h1 className="text-2xl font-semibold mt-1">
            {plan.name}{" "}
            <Badge variant={plan.status === "active" ? "default" : "secondary"}>
              {plan.status}
            </Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            User {plan.user_id} · {plan.split_type} · cycle length{" "}
            {plan.cycle_length}
            {plan.ai_generated ? " · AI-generated" : ""}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Days</h2>
          <Button size="sm" onClick={() => setAddDayOpen(true)}>
            + Add day
          </Button>
        </div>
        {days.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No days yet. Add one to start building the plan.
          </p>
        ) : (
          <Accordion type="multiple" className="space-y-1">
            {[...days]
              .sort((a, b) => a.day_number - b.day_number)
              .map((day) => (
                <DayAccordion
                  key={day.id}
                  day={day}
                  isSaving={
                    saveDay.isPending && savingDayNumber === day.day_number
                  }
                  onSave={async (draft) => {
                    setSavingDayNumber(day.day_number);
                    await saveDay.mutateAsync({
                      day_number: day.day_number,
                      input: draft,
                    });
                  }}
                  onDelete={async () => {
                    if (!confirm(`Delete Day ${day.day_number}?`)) return;
                    await deleteDay.mutateAsync(day.day_number);
                  }}
                />
              ))}
          </Accordion>
        )}
      </div>

      <Dialog
        open={addDayOpen}
        onOpenChange={(o) => {
          setAddDayOpen(o);
          if (!o) {
            setNewDayNumber("");
            setNewDayLabel("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add day</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Day number</Label>
              <Input
                type="number"
                value={newDayNumber}
                onChange={(e) => setNewDayNumber(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>Label</Label>
              <Input
                value={newDayLabel}
                onChange={(e) => setNewDayLabel(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setAddDayOpen(false)}
              disabled={addDay.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() =>
                addDay.mutate({
                  day_number: Number(newDayNumber),
                  label: newDayLabel,
                  focus: "",
                  exercise_groups: [],
                })
              }
              disabled={addDay.isPending || !newDayNumber || !newDayLabel}
            >
              {addDay.isPending ? "Adding…" : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
