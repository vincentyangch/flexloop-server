/**
 * Editor for a single PlanExercise inside a group.
 *
 * Mirrors the inline layout from spec §9.3: top row with exercise_id,
 * order, sets, reps, weight, rpe_target; optional SetTargetsGrid below.
 *
 * The parent GroupEditor controls draft state — this component never
 * talks to the API directly.
 */
import { SetTargetsGrid } from "./SetTargetsGrid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api.types";

type ExerciseDraft = components["schemas"]["PlanExerciseAdminCreate"];

type Props = {
  value: ExerciseDraft;
  onChange: (next: ExerciseDraft) => void;
  onDelete: () => void;
};

export function ExerciseEditor({ value, onChange, onDelete }: Props) {
  const patch = (p: Partial<ExerciseDraft>) => onChange({ ...value, ...p });

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="grid grid-cols-[5rem_4rem_4rem_4rem_5rem_4rem_auto] gap-2 items-end">
        <div className="space-y-1">
          <Label className="text-xs">Exercise ID</Label>
          <Input
            type="number"
            value={value.exercise_id}
            onChange={(e) => patch({ exercise_id: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Order</Label>
          <Input
            type="number"
            value={value.order}
            onChange={(e) => patch({ order: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Sets</Label>
          <Input
            type="number"
            value={value.sets}
            onChange={(e) => patch({ sets: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Reps</Label>
          <Input
            type="number"
            value={value.reps}
            onChange={(e) => patch({ reps: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Weight</Label>
          <Input
            type="number"
            step="0.5"
            value={value.weight ?? ""}
            onChange={(e) =>
              patch({
                weight: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">RPE</Label>
          <Input
            type="number"
            step="0.5"
            value={value.rpe_target ?? ""}
            onChange={(e) =>
              patch({
                rpe_target:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
          Delete
        </Button>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Notes</Label>
        <Textarea
          rows={2}
          value={value.notes ?? ""}
          onChange={(e) => patch({ notes: e.target.value || null })}
        />
      </div>
      <SetTargetsGrid
        setsJson={value.sets_json ?? null}
        fallbackSets={value.sets}
        fallbackReps={value.reps}
        fallbackWeight={value.weight ?? null}
        onChange={(next) => patch({ sets_json: next })}
      />
    </div>
  );
}
