/**
 * Hand-written react-hook-form + zod form for Personal Records.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type PersonalRecord = components["schemas"]["PersonalRecordAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  exercise_id: z.coerce.number().int().positive(),
  pr_type: z.string().min(1).max(20),
  value: z.coerce.number(),
  session_id: z.coerce.number().int().positive().nullable().optional(),
  achieved_at: z.string().min(1), // datetime-local
});

export type PRFormInput = z.input<typeof schema>;
export type PRFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: PersonalRecord | null;
  onSubmit: (values: PRFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function PRForm({
  defaultValues,
  onSubmit,
  isSaving = false,
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PRFormInput, unknown, PRFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          exercise_id: defaultValues.exercise_id,
          pr_type: defaultValues.pr_type,
          value: defaultValues.value,
          session_id: defaultValues.session_id ?? undefined,
          achieved_at: defaultValues.achieved_at.slice(0, 16),
        }
      : {
          user_id: 1,
          exercise_id: 1,
          pr_type: "max_weight",
          value: 0,
          session_id: undefined,
          achieved_at: new Date().toISOString().slice(0, 16),
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
          {errors.user_id && (
            <p className="text-xs text-destructive">{errors.user_id.message}</p>
          )}
        </div>
        <div className="space-y-1">
          <Label htmlFor="exercise_id">Exercise ID</Label>
          <Input id="exercise_id" type="number" {...register("exercise_id")} />
          {errors.exercise_id && (
            <p className="text-xs text-destructive">
              {errors.exercise_id.message}
            </p>
          )}
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="pr_type">PR type</Label>
        <Input
          id="pr_type"
          placeholder="max_weight, max_reps, max_distance"
          {...register("pr_type")}
        />
        {errors.pr_type && (
          <p className="text-xs text-destructive">{errors.pr_type.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="value">Value</Label>
        <Input id="value" type="number" step="0.01" {...register("value")} />
        {errors.value && (
          <p className="text-xs text-destructive">{errors.value.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="session_id">Session ID (optional)</Label>
        <Input
          id="session_id"
          type="number"
          placeholder="Leave blank if not tied to a session"
          {...register("session_id")}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="achieved_at">Achieved at</Label>
        <Input
          id="achieved_at"
          type="datetime-local"
          {...register("achieved_at")}
        />
        {errors.achieved_at && (
          <p className="text-xs text-destructive">
            {errors.achieved_at.message}
          </p>
        )}
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving
            ? "Saving..."
            : defaultValues
              ? "Save changes"
              : "Create PR"}
        </Button>
      </div>
    </form>
  );
}
