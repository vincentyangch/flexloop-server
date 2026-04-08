/**
 * One day's editor — keeps a local draft of the day's nested contents
 * and bubbles "Save day" / "Delete day" up to the parent PlanDetailPage.
 *
 * The draft resets whenever the underlying server-fetched day changes
 * (via the useEffect below), so after a successful save the query
 * invalidation flows the fresh data back in.
 */
import { useEffect, useRef, useState } from "react";

import { GroupEditor } from "./GroupEditor";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type PlanDay = components["schemas"]["PlanDayAdminResponse"];
type PlanDayUpdate = components["schemas"]["PlanDayAdminUpdate"];
type GroupDraft = components["schemas"]["ExerciseGroupAdminCreate"];
type SetTarget = components["schemas"]["SetTargetAdmin"];

function dayToDraft(day: PlanDay): PlanDayUpdate {
  return {
    label: day.label,
    focus: day.focus,
    exercise_groups: (day.exercise_groups ?? []).map((g) => ({
      group_type: g.group_type,
      order: g.order,
      rest_after_group_sec: g.rest_after_group_sec,
      exercises: (g.exercises ?? []).map((ex) => ({
        exercise_id: ex.exercise_id,
        order: ex.order,
        sets: ex.sets,
        reps: ex.reps,
        weight: ex.weight,
        rpe_target: ex.rpe_target,
        sets_json: ex.sets_json as SetTarget[] | null,
        notes: ex.notes,
      })),
    })),
  };
}

const EMPTY_GROUP: GroupDraft = {
  group_type: "straight",
  order: 1,
  rest_after_group_sec: 90,
  exercises: [],
};

type Props = {
  day: PlanDay;
  isSaving: boolean;
  onSave: (draft: PlanDayUpdate) => Promise<void>;
  onDelete: () => Promise<void>;
};

export function DayAccordion({ day, isSaving, onSave, onDelete }: Props) {
  const [draft, setDraft] = useState<PlanDayUpdate>(() => dayToDraft(day));
  const isDirtyRef = useRef(false);

  useEffect(() => {
    if (!isDirtyRef.current) {
      setDraft(dayToDraft(day));
    }
  }, [day]);

  const patch = (p: Partial<PlanDayUpdate>) => {
    isDirtyRef.current = true;
    setDraft((d) => ({ ...d, ...p }));
  };

  const updateGroup = (index: number, next: GroupDraft) => {
    patch({
      exercise_groups: (draft.exercise_groups ?? []).map((g, i) =>
        i === index ? next : g,
      ),
    });
  };

  const deleteGroup = (index: number) => {
    patch({
      exercise_groups: (draft.exercise_groups ?? []).filter(
        (_, i) => i !== index,
      ),
    });
  };

  const addGroup = () => {
    const groups = draft.exercise_groups ?? [];
    const nextOrder = (groups.at(-1)?.order ?? 0) + 1;
    patch({
      exercise_groups: [
        ...groups,
        { ...EMPTY_GROUP, order: nextOrder },
      ],
    });
  };

  return (
    <AccordionItem value={String(day.day_number)}>
      <AccordionTrigger className="px-3">
        <div className="flex-1 text-left">
          <span className="font-medium">Day {day.day_number}</span>
          <span className="text-muted-foreground"> — {day.label}</span>
          {day.focus && (
            <span className="text-muted-foreground"> — {day.focus}</span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-3 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Label</Label>
            <Input
              value={draft.label ?? ""}
              onChange={(e) => patch({ label: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Focus</Label>
            <Input
              value={draft.focus ?? ""}
              onChange={(e) => patch({ focus: e.target.value })}
            />
          </div>
        </div>
        <div className="space-y-3">
          {(draft.exercise_groups ?? []).map((group, i) => (
            <GroupEditor
              key={i}
              value={group}
              onChange={(next) => updateGroup(i, next)}
              onDelete={() => deleteGroup(i)}
            />
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={addGroup}
          >
            + Add exercise group
          </Button>
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={onDelete}
            disabled={isSaving}
          >
            Delete day
          </Button>
          <Button
            type="button"
            onClick={() => {
              void (async () => {
                try {
                  await onSave(draft);
                  isDirtyRef.current = false;
                  setDraft(dayToDraft(day));
                } catch {
                  // retain dirty state on failure; parent surfaces the toast
                }
              })();
            }}
            disabled={isSaving}
          >
            {isSaving ? "Saving…" : "Save day"}
          </Button>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
