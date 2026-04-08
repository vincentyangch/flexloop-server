/**
 * Editor for a single ExerciseGroup inside a day.
 *
 * Shows group_type/order/rest controls on top, then one ExerciseEditor
 * per exercise plus an "Add exercise" button at the bottom.
 */
import { ExerciseEditor } from "./ExerciseEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type GroupDraft = components["schemas"]["ExerciseGroupAdminCreate"];
type ExerciseDraft = components["schemas"]["PlanExerciseAdminCreate"];

type Props = {
  value: GroupDraft;
  onChange: (next: GroupDraft) => void;
  onDelete: () => void;
};

const EMPTY_EXERCISE: ExerciseDraft = {
  exercise_id: 1,
  order: 1,
  sets: 3,
  reps: 10,
  weight: null,
  rpe_target: null,
  sets_json: null,
  notes: null,
};

export function GroupEditor({ value, onChange, onDelete }: Props) {
  const patch = (p: Partial<GroupDraft>) => onChange({ ...value, ...p });
  const exercises = value.exercises ?? [];

  const updateExercise = (index: number, next: ExerciseDraft) => {
    patch({
      exercises: exercises.map((ex, i) => (i === index ? next : ex)),
    });
  };

  const deleteExercise = (index: number) => {
    patch({ exercises: exercises.filter((_, i) => i !== index) });
  };

  const addExercise = () => {
    const nextOrder = (exercises.at(-1)?.order ?? 0) + 1;
    patch({
      exercises: [
        ...exercises,
        { ...EMPTY_EXERCISE, order: nextOrder },
      ],
    });
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-3">
      <div className="grid grid-cols-[1fr_6rem_6rem_auto] gap-2 items-end">
        <div className="space-y-1">
          <Label className="text-xs">Group type</Label>
          <Input
            value={value.group_type}
            onChange={(e) => patch({ group_type: e.target.value })}
            placeholder="straight / superset / circuit"
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
          <Label className="text-xs">Rest (sec)</Label>
          <Input
            type="number"
            value={value.rest_after_group_sec}
            onChange={(e) =>
              patch({ rest_after_group_sec: Number(e.target.value) })
            }
          />
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
          Delete group
        </Button>
      </div>
      <div className="space-y-2">
        {exercises.map((ex, i) => (
          <ExerciseEditor
            key={i}
            value={ex}
            onChange={(next) => updateExercise(i, next)}
            onDelete={() => deleteExercise(i)}
          />
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={addExercise}
        >
          + Add exercise to group
        </Button>
      </div>
    </div>
  );
}
