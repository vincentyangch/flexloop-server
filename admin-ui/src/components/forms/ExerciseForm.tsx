/**
 * Hand-written react-hook-form + zod form for Exercises.
 *
 * metadata_json is intentionally omitted from the form — it's editable
 * only via the JSON tab escape hatch in EditSheet.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type Exercise = components["schemas"]["ExerciseAdminResponse"];

const schema = z.object({
  name: z.string().min(1).max(200),
  muscle_group: z.string().min(1).max(50),
  equipment: z.string().min(1).max(50),
  category: z.string().min(1).max(50),
  difficulty: z.string().min(1).max(20),
  source_plugin: z.string().nullable().optional(),
});

export type ExerciseFormInput = z.input<typeof schema>;
export type ExerciseFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: Exercise | null;
  onSubmit: (values: ExerciseFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function ExerciseForm({
  defaultValues,
  onSubmit,
  isSaving = false,
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ExerciseFormInput, unknown, ExerciseFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          name: defaultValues.name,
          muscle_group: defaultValues.muscle_group,
          equipment: defaultValues.equipment,
          category: defaultValues.category,
          difficulty: defaultValues.difficulty,
          source_plugin: defaultValues.source_plugin ?? "",
        }
      : {
          name: "",
          muscle_group: "chest",
          equipment: "barbell",
          category: "compound",
          difficulty: "intermediate",
          source_plugin: "",
        },
  });

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-4"
    >
      <div className="space-y-1">
        <Label htmlFor="name">Name</Label>
        <Input id="name" {...register("name")} />
        {errors.name && (
          <p className="text-xs text-destructive">{errors.name.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="muscle_group">Muscle group</Label>
        <Input
          id="muscle_group"
          placeholder="chest, back, legs, ..."
          {...register("muscle_group")}
        />
        {errors.muscle_group && (
          <p className="text-xs text-destructive">
            {errors.muscle_group.message}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="equipment">Equipment</Label>
        <Input
          id="equipment"
          placeholder="barbell, dumbbells, cables, ..."
          {...register("equipment")}
        />
        {errors.equipment && (
          <p className="text-xs text-destructive">{errors.equipment.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="category">Category</Label>
        <Input
          id="category"
          placeholder="compound, isolation"
          {...register("category")}
        />
        {errors.category && (
          <p className="text-xs text-destructive">{errors.category.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="difficulty">Difficulty</Label>
        <Input
          id="difficulty"
          placeholder="beginner, intermediate, advanced"
          {...register("difficulty")}
        />
        {errors.difficulty && (
          <p className="text-xs text-destructive">
            {errors.difficulty.message}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="source_plugin">Source plugin (optional)</Label>
        <Input
          id="source_plugin"
          placeholder="Leave blank for manual entries"
          {...register("source_plugin")}
        />
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving
            ? "Saving..."
            : defaultValues
              ? "Save changes"
              : "Create exercise"}
        </Button>
      </div>
    </form>
  );
}
