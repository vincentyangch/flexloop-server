/**
 * Left-panel input for the playground.
 *
 * Phase 4c Chunk 3: free-form mode ONLY (system + user textareas).
 * Chunk 4 will add template mode with a dropdown + variable form +
 * rendered preview.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

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
};

export function PlaygroundInput({ onSend, isStreaming }: Props) {
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [userPrompt, setUserPrompt] = useState("");
  const [temperature, setTemperature] = useState<string>("");
  const [maxTokens, setMaxTokens] = useState<string>("");
  const [providerOverride, setProviderOverride] = useState("");
  const [modelOverride, setModelOverride] = useState("");

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
