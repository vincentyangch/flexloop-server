/**
 * Hand-written react-hook-form + zod form for Plan metadata.
 *
 * This form ONLY edits plan metadata (name, split type, cycle length,
 * status, block dates). Day contents are edited on the Plan detail page
 * via the day endpoints — the admin update schema enforces this at the
 * API layer too.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  name: z.string().min(1, "name is required"),
  split_type: z.string().default("custom"),
  cycle_length: z.coerce.number().int().min(1).max(14),
  block_start: z.string().nullable().optional(),
  block_end: z.string().nullable().optional(),
  status: z.enum(["active", "inactive", "archived"]),
  ai_generated: z.boolean().default(false),
});

export type PlanFormInput = z.input<typeof schema>;
export type PlanFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: Plan | null;
  onSubmit: (values: PlanFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function PlanForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit, setValue, watch, formState: { errors } } =
    useForm<PlanFormInput, unknown, PlanFormValues>({
      resolver: zodResolver(schema),
      defaultValues: defaultValues
        ? {
            user_id: defaultValues.user_id,
            name: defaultValues.name,
            split_type: defaultValues.split_type,
            cycle_length: defaultValues.cycle_length,
            block_start: defaultValues.block_start ?? "",
            block_end: defaultValues.block_end ?? "",
            status: defaultValues.status as "active" | "inactive" | "archived",
            ai_generated: defaultValues.ai_generated,
          }
        : {
            user_id: 1,
            name: "",
            split_type: "custom",
            cycle_length: 3,
            block_start: "",
            block_end: "",
            status: "active",
            ai_generated: false,
          },
    });

  const status = watch("status");

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="user_id">User ID</Label>
        <Input id="user_id" type="number" {...register("user_id")} />
        {errors.user_id && (
          <p className="text-sm text-red-600">{errors.user_id.message}</p>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="name">Name</Label>
        <Input id="name" {...register("name")} />
        {errors.name && (
          <p className="text-sm text-red-600">{errors.name.message}</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="split_type">Split type</Label>
          <Input id="split_type" {...register("split_type")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cycle_length">Cycle length (days)</Label>
          <Input id="cycle_length" type="number" {...register("cycle_length")} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="block_start">Block start</Label>
          <Input id="block_start" type="date" {...register("block_start")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="block_end">Block end</Label>
          <Input id="block_end" type="date" {...register("block_end")} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Status</Label>
        <Select
          value={status}
          onValueChange={(v) =>
            setValue("status", v as "active" | "inactive" | "archived")
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox
          id="ai_generated"
          checked={watch("ai_generated")}
          onCheckedChange={(checked) => setValue("ai_generated", checked === true)}
        />
        <Label htmlFor="ai_generated" className="cursor-pointer">
          AI-generated
        </Label>
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving…" : "Save"}
        </Button>
      </div>
    </form>
  );
}
