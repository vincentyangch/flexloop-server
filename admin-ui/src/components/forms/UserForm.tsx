/**
 * Hand-written react-hook-form + zod form for Users.
 *
 * Why hand-written: auto-form generators make a mess of JSON array columns
 * like `available_equipment`. The per-resource form is ~80 lines and worth
 * the clarity.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import type { InputHTMLAttributes } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api.types";

type UserAdminResponse = components["schemas"]["UserAdminResponse"];

const schema = z.object({
  name: z.string().min(1).max(100),
  gender: z.string().min(1).max(20),
  age: z.coerce.number().int().min(0).max(150),
  height: z.coerce.number().positive(),
  weight: z.coerce.number().positive(),
  weight_unit: z.string().default("kg"),
  height_unit: z.string().default("cm"),
  experience_level: z.string().min(1).max(20),
  goals: z.string().max(500).default(""),
  available_equipment_csv: z.string().default(""),
});

export type UserFormInput = z.input<typeof schema>;
export type UserFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: UserAdminResponse | null;
  onSubmit: (
    values: UserFormValues & { available_equipment: string[] | null },
  ) => void | Promise<void>;
  isSaving?: boolean;
};

export function UserForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UserFormInput, unknown, UserFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          name: defaultValues.name,
          gender: defaultValues.gender,
          age: defaultValues.age,
          height: defaultValues.height,
          weight: defaultValues.weight,
          weight_unit: defaultValues.weight_unit,
          height_unit: defaultValues.height_unit,
          experience_level: defaultValues.experience_level,
          goals: defaultValues.goals,
          available_equipment_csv: (defaultValues.available_equipment ?? []).join(", "),
        }
      : {
          name: "",
          gender: "other",
          age: 30,
          height: 170,
          weight: 70,
          weight_unit: "kg",
          height_unit: "cm",
          experience_level: "intermediate",
          goals: "",
          available_equipment_csv: "",
        },
  });

  const submit = handleSubmit(async (values) => {
    const equipment = values.available_equipment_csv
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await onSubmit({
      ...values,
      available_equipment: equipment.length ? equipment : null,
    });
  });

  const field = (
    name: keyof UserFormInput,
    label: string,
    props: InputHTMLAttributes<HTMLInputElement> = {},
  ) => (
    <div className="space-y-1">
      <Label htmlFor={name}>{label}</Label>
      <Input id={name} {...props} {...register(name)} />
      {errors[name] && (
        <p className="text-xs text-destructive">{String(errors[name]?.message)}</p>
      )}
    </div>
  );

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      {field("name", "Name")}
      {field("gender", "Gender")}
      <div className="grid grid-cols-2 gap-3">
        {field("age", "Age", { type: "number", min: 0, max: 150 })}
        {field("experience_level", "Experience")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {field("height", "Height", { type: "number", step: "0.1" })}
        {field("height_unit", "Height unit")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {field("weight", "Weight", { type: "number", step: "0.1" })}
        {field("weight_unit", "Weight unit")}
      </div>

      <div className="space-y-1">
        <Label htmlFor="goals">Goals</Label>
        <Textarea id="goals" rows={3} {...register("goals")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="available_equipment_csv">
          Available equipment (comma-separated)
        </Label>
        <Input
          id="available_equipment_csv"
          placeholder="barbell, dumbbells, cables"
          {...register("available_equipment_csv")}
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving..." : defaultValues ? "Save changes" : "Create user"}
        </Button>
      </div>
    </form>
  );
}
