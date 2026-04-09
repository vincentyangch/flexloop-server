/**
 * Left-panel input for the playground.
 *
 * Phase 4c Chunk 3: free-form mode ONLY (system + user textareas).
 * Chunk 4: adds template mode with a dropdown + variable form + rendered preview.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TemplateForm } from "@/components/playground/TemplateForm";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type TemplatesResponse = components["schemas"]["PlaygroundTemplatesResponse"];
type RenderResponse = components["schemas"]["PlaygroundRenderResponse"];

export type PlaygroundRunPayload = {
  system_prompt: string;
  user_prompt: string;
  temperature: number | null;
  max_tokens: number | null;
  provider_override: string | null;
  model_override: string | null;
  api_key_override: string | null;
  base_url_override: string | null;
};

type Props = {
  onSend: (payload: PlaygroundRunPayload) => void;
  isStreaming: boolean;
  initialTemplate?: string | null;
};

type Mode = "free" | "template";

export function PlaygroundInput({ onSend, isStreaming, initialTemplate }: Props) {
  const [mode, setMode] = useState<Mode>(initialTemplate ? "template" : "free");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(
    initialTemplate ?? null,
  );
  const [templateVars, setTemplateVars] = useState<Record<string, string>>({});

  const templatesQuery = useQuery({
    queryKey: ["admin", "playground", "templates"],
    queryFn: () => api.get<TemplatesResponse>("/api/admin/playground/templates"),
  });

  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [userPrompt, setUserPrompt] = useState("");
  const [temperature, setTemperature] = useState<string>("");
  const [maxTokens, setMaxTokens] = useState<string>("");
  const [providerOverride, setProviderOverride] = useState("");
  const [modelOverride, setModelOverride] = useState("");

  // When template selection or vars change, re-render the user_prompt
  useEffect(() => {
    if (mode !== "template" || !selectedTemplate) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.post<RenderResponse>(
          "/api/admin/playground/render",
          { template_name: selectedTemplate, variables: templateVars },
        );
        if (!cancelled) setUserPrompt(res.rendered);
      } catch (e) {
        if (!cancelled) setUserPrompt("(failed to render template)");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, selectedTemplate, templateVars]);

  const selectedTemplateInfo = templatesQuery.data?.templates.find(
    (t) => t.name === selectedTemplate,
  );

  const canSend = userPrompt.trim().length > 0 && !isStreaming;

  const handleSend = () => {
    onSend({
      system_prompt: systemPrompt,
      user_prompt: userPrompt,
      temperature: temperature === "" ? null : Number(temperature),
      max_tokens: maxTokens === "" ? null : Number(maxTokens),
      provider_override: providerOverride || null,
      model_override: modelOverride || null,
      api_key_override: null,
      base_url_override: null,
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Button
          size="sm"
          variant={mode === "free" ? "default" : "outline"}
          onClick={() => setMode("free")}
        >
          Free-form
        </Button>
        <Button
          size="sm"
          variant={mode === "template" ? "default" : "outline"}
          onClick={() => setMode("template")}
        >
          From template
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Prompt</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="system_prompt">System prompt</Label>
            <Textarea
              id="system_prompt"
              rows={3}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user_prompt">User prompt</Label>
            <Textarea
              id="user_prompt"
              rows={8}
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Type your test prompt here…"
            />
          </div>
        </CardContent>
      </Card>

      {mode === "template" && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Template</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="template_select">Template</Label>
              <Select
                value={selectedTemplate ?? ""}
                onValueChange={(v) => {
                  setSelectedTemplate(v);
                  setTemplateVars({});
                }}
              >
                <SelectTrigger id="template_select">
                  <SelectValue placeholder="(select a template)" />
                </SelectTrigger>
                <SelectContent>
                  {(templatesQuery.data?.templates ?? []).map((t) => (
                    <SelectItem key={t.name} value={t.name}>
                      {t.name} ({t.active_version})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedTemplateInfo && (
              <TemplateForm
                variables={selectedTemplateInfo.variables}
                values={templateVars}
                onChange={setTemplateVars}
              />
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Advanced</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="temperature">Temperature (blank = saved default)</Label>
            <Input
              id="temperature"
              type="number"
              step="0.05"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              placeholder="0.7"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="max_tokens">Max tokens</Label>
            <Input
              id="max_tokens"
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="2000"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="provider_override">Provider override</Label>
            <Input
              id="provider_override"
              value={providerOverride}
              onChange={(e) => setProviderOverride(e.target.value)}
              placeholder="(use saved)"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="model_override">Model override</Label>
            <Input
              id="model_override"
              value={modelOverride}
              onChange={(e) => setModelOverride(e.target.value)}
              placeholder="(use saved)"
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSend} disabled={!canSend}>
          {isStreaming ? "Streaming…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
