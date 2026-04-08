/**
 * Hand-written react-hook-form + zod form for Admin Users.
 *
 * The password field is write-only — it never appears in the response
 * schema, so we swap between two zod schemas based on mode:
 *   - create: password required (min 8)
 *   - edit:   password optional; empty string is accepted and stripped
 *             in the submit handler so the backend update doesn't touch
 *             the hash.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type AdminAdminUserResponse = components["schemas"]["AdminAdminUserResponse"];

const createSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(8).max(256),
  is_active: z.boolean().default(true),
});

const updateSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(8).max(256).optional().or(z.literal("")),
  is_active: z.boolean().default(true),
});

export type AdminUserFormInput = z.input<typeof updateSchema>;
export type AdminUserFormValues = z.output<typeof updateSchema>;

type Props = {
  mode: "create" | "edit";
  defaultValues?: AdminAdminUserResponse | null;
  onSubmit: (values: AdminUserFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function AdminUserForm({
  mode,
  defaultValues,
  onSubmit,
  isSaving = false,
}: Props) {
  const schema = mode === "create" ? createSchema : updateSchema;
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AdminUserFormInput, unknown, AdminUserFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          username: defaultValues.username,
          password: "",
          is_active: defaultValues.is_active,
        }
      : {
          username: "",
          password: "",
          is_active: true,
        },
  });

  const submit = handleSubmit(async (values) => {
    // In edit mode, an empty password string means "leave existing hash
    // alone"; drop the key entirely so the backend update schema ignores
    // it (instead of trying to validate "" as a bcrypt candidate).
    if (mode === "edit" && !values.password) {
      const { password: _pw, ...rest } = values;
      void _pw;
      await onSubmit(rest as AdminUserFormValues);
      return;
    }
    await onSubmit(values);
  });

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="username">Username</Label>
        <Input id="username" {...register("username")} />
        {errors.username && (
          <p className="text-xs text-destructive">{errors.username.message}</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          placeholder={
            mode === "edit"
              ? "Leave blank to keep existing"
              : "At least 8 characters"
          }
          {...register("password")}
        />
        {errors.password && (
          <p className="text-xs text-destructive">{errors.password.message}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input
          id="is_active"
          type="checkbox"
          className="size-4 rounded border-input"
          {...register("is_active")}
        />
        <Label htmlFor="is_active" className="cursor-pointer">
          Active
        </Label>
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving
            ? "Saving..."
            : mode === "edit"
              ? "Save changes"
              : "Create admin user"}
        </Button>
      </div>
    </form>
  );
}
