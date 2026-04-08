/**
 * Hand-written react-hook-form + zod form for AI Usage records.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type AIUsage = components["schemas"]["AIUsageAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  month: z.string().regex(/^\d{4}-\d{2}$/, "Use YYYY-MM format"),
  total_input_tokens: z.coerce.number().int().min(0).default(0),
  total_output_tokens: z.coerce.number().int().min(0).default(0),
  total_cache_read_tokens: z.coerce.number().int().min(0).default(0),
  total_cache_creation_tokens: z.coerce.number().int().min(0).default(0),
  estimated_cost: z.coerce.number().min(0).default(0),
  call_count: z.coerce.number().int().min(0).default(0),
});

export type AIUsageFormInput = z.input<typeof schema>;
export type AIUsageFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: AIUsage | null;
  onSubmit: (values: AIUsageFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function AIUsageForm({
  defaultValues,
  onSubmit,
  isSaving = false,
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AIUsageFormInput, unknown, AIUsageFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          month: defaultValues.month,
          total_input_tokens: defaultValues.total_input_tokens,
          total_output_tokens: defaultValues.total_output_tokens,
          total_cache_read_tokens: defaultValues.total_cache_read_tokens,
          total_cache_creation_tokens:
            defaultValues.total_cache_creation_tokens,
          estimated_cost: defaultValues.estimated_cost,
          call_count: defaultValues.call_count,
        }
      : {
          user_id: 1,
          month: new Date().toISOString().slice(0, 7),
          total_input_tokens: 0,
          total_output_tokens: 0,
          total_cache_read_tokens: 0,
          total_cache_creation_tokens: 0,
          estimated_cost: 0,
          call_count: 0,
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
          <Label htmlFor="month">Month</Label>
          <Input id="month" placeholder="2026-04" {...register("month")} />
          {errors.month && (
            <p className="text-xs text-destructive">{errors.month.message}</p>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="total_input_tokens">Input tokens</Label>
          <Input
            id="total_input_tokens"
            type="number"
            min={0}
            {...register("total_input_tokens")}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="total_output_tokens">Output tokens</Label>
          <Input
            id="total_output_tokens"
            type="number"
            min={0}
            {...register("total_output_tokens")}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="total_cache_read_tokens">Cache read tokens</Label>
          <Input
            id="total_cache_read_tokens"
            type="number"
            min={0}
            {...register("total_cache_read_tokens")}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="total_cache_creation_tokens">
            Cache creation tokens
          </Label>
          <Input
            id="total_cache_creation_tokens"
            type="number"
            min={0}
            {...register("total_cache_creation_tokens")}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="estimated_cost">Estimated cost ($)</Label>
          <Input
            id="estimated_cost"
            type="number"
            step="0.0001"
            min={0}
            {...register("estimated_cost")}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="call_count">Call count</Label>
          <Input
            id="call_count"
            type="number"
            min={0}
            {...register("call_count")}
          />
        </div>
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving
            ? "Saving..."
            : defaultValues
              ? "Save changes"
              : "Create usage row"}
        </Button>
      </div>
    </form>
  );
}
