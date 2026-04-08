/**
 * Editable grid of set targets for a single PlanExercise.
 *
 * Receives a sets_json array (may be null — meaning "use the top-level
 * sets/reps/weight defaults") and calls onChange with the new array on
 * every edit. Parent components decide when to persist.
 *
 * If sets_json is null, the grid shows a button to "initialize per-set
 * targets" which populates the array from the top-level sets count.
 */
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { components } from "@/lib/api.types";

type SetTarget = components["schemas"]["SetTargetAdmin"];

type Props = {
  setsJson: SetTarget[] | null;
  fallbackSets: number;
  fallbackReps: number;
  fallbackWeight: number | null;
  onChange: (next: SetTarget[] | null) => void;
};

export function SetTargetsGrid({
  setsJson,
  fallbackSets,
  fallbackReps,
  fallbackWeight,
  onChange,
}: Props) {
  if (setsJson === null || setsJson === undefined) {
    return (
      <div className="text-sm text-muted-foreground py-2">
        <span className="mr-2">
          Using top-level defaults ({fallbackSets}×{fallbackReps}
          {fallbackWeight !== null ? ` @ ${fallbackWeight}` : ""}).
        </span>
        <Button
          size="sm"
          variant="outline"
          type="button"
          onClick={() => {
            const rows: SetTarget[] = Array.from(
              { length: fallbackSets },
              (_, i) => ({
                set_number: i + 1,
                target_weight: fallbackWeight,
                target_reps: fallbackReps,
                target_rpe: null,
              }),
            );
            onChange(rows);
          }}
        >
          Use per-set targets
        </Button>
      </div>
    );
  }

  const updateRow = (index: number, patch: Partial<SetTarget>) => {
    const next = setsJson.map((row, i) =>
      i === index ? { ...row, ...patch } : row,
    );
    onChange(next);
  };

  return (
    <div className="space-y-1 pt-2">
      <div className="grid grid-cols-[3rem_1fr_1fr_1fr_2rem] gap-2 text-xs text-muted-foreground">
        <span>#</span>
        <span>Weight</span>
        <span>Reps</span>
        <span>RPE</span>
        <span />
      </div>
      {setsJson.map((row, i) => (
        <div
          key={i}
          className="grid grid-cols-[3rem_1fr_1fr_1fr_2rem] gap-2 items-center"
        >
          <span className="tabular-nums text-sm">{row.set_number}</span>
          <Input
            type="number"
            step="0.5"
            value={row.target_weight ?? ""}
            onChange={(e) =>
              updateRow(i, {
                target_weight:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
          <Input
            type="number"
            value={row.target_reps}
            onChange={(e) =>
              updateRow(i, { target_reps: Number(e.target.value) })
            }
          />
          <Input
            type="number"
            step="0.5"
            value={row.target_rpe ?? ""}
            onChange={(e) =>
              updateRow(i, {
                target_rpe:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => {
              const next = setsJson
                .filter((_, j) => j !== i)
                .map((r, j) => ({ ...r, set_number: j + 1 }));
              onChange(next.length === 0 ? null : next);
            }}
          >
            ×
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => {
          const lastNumber = setsJson.length;
          const last = setsJson[setsJson.length - 1];
          onChange([
            ...setsJson,
            {
              set_number: lastNumber + 1,
              target_weight: last?.target_weight ?? null,
              target_reps: last?.target_reps ?? fallbackReps,
              target_rpe: last?.target_rpe ?? null,
            },
          ]);
        }}
      >
        + Add set
      </Button>
    </div>
  );
}
