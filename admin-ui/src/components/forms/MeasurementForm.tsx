/**
 * Hand-written react-hook-form + zod form for Measurements.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api.types";

type Measurement = components["schemas"]["MeasurementAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  date: z.string().min(1), // "YYYY-MM-DD"
  type: z.string().min(1).max(20),
  value: z.coerce.number(),
  notes: z.string().nullable().optional(),
});

export type MeasurementFormInput = z.input<typeof schema>;
export type MeasurementFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: Measurement | null;
  onSubmit: (values: MeasurementFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function MeasurementForm({
  defaultValues,
  onSubmit,
  isSaving = false,
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<MeasurementFormInput, unknown, MeasurementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          date: defaultValues.date,
          type: defaultValues.type,
          value: defaultValues.value,
          notes: defaultValues.notes ?? "",
        }
      : {
          user_id: 1,
          date: new Date().toISOString().slice(0, 10),
          type: "weight",
          value: 0,
          notes: "",
        },
  });

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-4"
    >
      <div className="space-y-1">
        <Label htmlFor="user_id">User ID</Label>
        <Input id="user_id" type="number" {...register("user_id")} />
        {errors.user_id && (
          <p className="text-xs text-destructive">{errors.user_id.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="date">Date</Label>
        <Input id="date" type="date" {...register("date")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="type">Type</Label>
        <Input
          id="type"
          placeholder="weight, body_fat, chest..."
          {...register("type")}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="value">Value</Label>
        <Input id="value" type="number" step="0.1" {...register("value")} />
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
              : "Create measurement"}
        </Button>
      </div>
    </form>
  );
}
