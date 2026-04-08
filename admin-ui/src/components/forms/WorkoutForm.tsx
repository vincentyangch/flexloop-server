/**
 * Hand-written react-hook-form + zod form for Workout sessions.
 *
 * datetime-local inputs drive started_at/completed_at. completed_at is
 * left blank for in-progress workouts; the page layer normalizes that
 * to null before submit.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api.types";

type Workout = components["schemas"]["WorkoutSessionAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  source: z.string().default("plan"),
  plan_day_id: z.coerce.number().int().positive().nullable().optional(),
  template_id: z.coerce.number().int().positive().nullable().optional(),
  started_at: z.string().min(1),
  completed_at: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export type WorkoutFormInput = z.input<typeof schema>;
export type WorkoutFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: Workout | null;
  onSubmit: (values: WorkoutFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function WorkoutForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit } = useForm<
    WorkoutFormInput,
    unknown,
    WorkoutFormValues
  >({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          source: defaultValues.source,
          plan_day_id: defaultValues.plan_day_id ?? undefined,
          template_id: defaultValues.template_id ?? undefined,
          started_at: defaultValues.started_at,
          completed_at: defaultValues.completed_at ?? "",
          notes: defaultValues.notes ?? "",
        }
      : {
          user_id: 1,
          source: "plan",
          started_at: new Date().toISOString().slice(0, 16),
          completed_at: "",
          notes: "",
        },
  });

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-4"
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="user_id">User ID</Label>
          <Input id="user_id" type="number" {...register("user_id")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="source">Source</Label>
          <Input
            id="source"
            placeholder="plan, custom..."
            {...register("source")}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="started_at">Started at</Label>
        <Input
          id="started_at"
          type="datetime-local"
          {...register("started_at")}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="completed_at">
          Completed at (leave blank if in progress)
        </Label>
        <Input
          id="completed_at"
          type="datetime-local"
          {...register("completed_at")}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" rows={3} {...register("notes")} />
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving
            ? "Saving..."
            : defaultValues
              ? "Save changes"
              : "Create workout"}
        </Button>
      </div>
    </form>
  );
}
