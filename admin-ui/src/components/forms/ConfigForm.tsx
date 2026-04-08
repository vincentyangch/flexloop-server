/**
 * Config form — sectioned layout for AppSettings fields.
 *
 * Sections:
 * - AI Provider: provider, model, api_key (masked), base_url
 * - Generation Defaults: temperature, max_tokens
 * - Review Schedule: review_frequency, review_block_weeks
 * - Allowed Origins: admin_allowed_origins (CSV input)
 *
 * The API key field uses type="password" with a reveal toggle (client-side
 * only). The "Rotate" button clears the field so the user can paste a new
 * value. After save, the server returns the masked form which the parent
 * page writes back into the form's defaults.
 */
import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
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

type Config = components["schemas"]["AppSettingsResponse"];

const schema = z.object({
  ai_provider: z.string().min(1),
  ai_model: z.string().min(1),
  ai_api_key: z.string(),
  ai_base_url: z.string(),
  ai_temperature: z.coerce.number().min(0).max(2),
  ai_max_tokens: z.coerce.number().int().positive(),
  ai_review_frequency: z.string().min(1),
  ai_review_block_weeks: z.coerce.number().int().positive(),
  admin_allowed_origins_csv: z.string(),
});

export type ConfigFormInput = z.input<typeof schema>;
export type ConfigFormValues = z.output<typeof schema>;

type Props = {
  defaultValues: Config;
  onSubmit: (values: ConfigFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function ConfigForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const [revealKey, setRevealKey] = useState(false);

  const { register, handleSubmit, setValue, watch } = useForm<
    ConfigFormInput,
    unknown,
    ConfigFormValues
  >({
    resolver: zodResolver(schema),
    defaultValues: {
      ai_provider: defaultValues.ai_provider,
      ai_model: defaultValues.ai_model,
      ai_api_key: defaultValues.ai_api_key,
      ai_base_url: defaultValues.ai_base_url,
      ai_temperature: defaultValues.ai_temperature,
      ai_max_tokens: defaultValues.ai_max_tokens,
      ai_review_frequency: defaultValues.ai_review_frequency,
      ai_review_block_weeks: defaultValues.ai_review_block_weeks,
      admin_allowed_origins_csv: (defaultValues.admin_allowed_origins ?? []).join(
        ", ",
      ),
    },
  });

  const provider = watch("ai_provider");
  const frequency = watch("ai_review_frequency");

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-8 max-w-2xl"
    >
      {/* AI Provider */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">AI Provider</h2>
        <div className="space-y-1.5">
          <Label htmlFor="ai_provider">Provider</Label>
          <Select
            value={provider}
            onValueChange={(v) => setValue("ai_provider", v)}
          >
            <SelectTrigger id="ai_provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="openai-compatible">OpenAI-compatible</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
              <SelectItem value="ollama">Ollama</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_model">Model</Label>
          <Input id="ai_model" {...register("ai_model")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_api_key">API Key</Label>
          <div className="flex gap-2">
            <Input
              id="ai_api_key"
              type={revealKey ? "text" : "password"}
              className="font-mono"
              {...register("ai_api_key")}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => setRevealKey((r) => !r)}
            >
              {revealKey ? "Hide" : "Reveal"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setValue("ai_api_key", "")}
            >
              Rotate
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            The key is masked for display. Leave as-is to keep the current key,
            or type a new value to rotate.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_base_url">Base URL</Label>
          <Input
            id="ai_base_url"
            placeholder="(optional — leave blank for provider default)"
            {...register("ai_base_url")}
          />
        </div>
      </section>

      {/* Generation Defaults */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Generation Defaults</h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="ai_temperature">Temperature</Label>
            <Input
              id="ai_temperature"
              type="number"
              step="0.05"
              {...register("ai_temperature")}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ai_max_tokens">Max tokens</Label>
            <Input
              id="ai_max_tokens"
              type="number"
              {...register("ai_max_tokens")}
            />
          </div>
        </div>
      </section>

      {/* Review Schedule */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Review Schedule</h2>
        <div className="space-y-1.5">
          <Label htmlFor="ai_review_frequency">Frequency</Label>
          <Select
            value={frequency}
            onValueChange={(v) => setValue("ai_review_frequency", v)}
          >
            <SelectTrigger id="ai_review_frequency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="block">Per block</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="never">Never</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_review_block_weeks">Block length (weeks)</Label>
          <Input
            id="ai_review_block_weeks"
            type="number"
            {...register("ai_review_block_weeks")}
          />
        </div>
      </section>

      {/* Allowed Origins */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Allowed Origins</h2>
        <div className="space-y-1.5">
          <Label htmlFor="admin_allowed_origins_csv">
            Admin allowed origins (comma-separated)
          </Label>
          <Input
            id="admin_allowed_origins_csv"
            placeholder="http://localhost:5173, https://admin.example.com"
            {...register("admin_allowed_origins_csv")}
          />
          <p className="text-xs text-muted-foreground">
            Used by the CSRF middleware. Changes take effect immediately
            after save — no restart required.
          </p>
        </div>
      </section>

      <div className="flex justify-end pt-4 border-t">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving…" : "Save"}
        </Button>
      </div>
    </form>
  );
}
