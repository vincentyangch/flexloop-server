/**
 * Admin Config page.
 *
 * Top: "Test connection" card — fires POST /api/admin/config/test-connection
 * with an empty body so it uses the currently saved config.
 *
 * Middle: ConfigForm — sectioned form for editing AppSettings.
 *
 * Save sends PUT /api/admin/config. Empty ai_api_key field is interpreted
 * as "explicitly clear the key" — the user had to click Rotate and confirm.
 * Unchanged (masked) field is round-tripped as-is and the server leaves
 * the plaintext alone.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ConfigForm } from "@/components/forms/ConfigForm";
import type { ConfigFormValues } from "@/components/forms/ConfigForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type Config = components["schemas"]["AppSettingsResponse"];
type ConfigUpdate = components["schemas"]["AppSettingsUpdate"];
type TestResult = components["schemas"]["TestConnectionResponse"];
type TestRequest = components["schemas"]["TestConnectionRequest"];

const CONFIG_KEY = ["admin", "config"];

function formValuesToUpdate(v: ConfigFormValues): ConfigUpdate {
  const origins = v.admin_allowed_origins_csv
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return {
    ai_provider: v.ai_provider,
    ai_model: v.ai_model,
    ai_api_key: v.ai_api_key,
    ai_base_url: v.ai_base_url,
    codex_auth_file: v.codex_auth_file,
    ai_reasoning_effort: v.ai_reasoning_effort,
    ai_temperature: v.ai_temperature,
    ai_max_tokens: v.ai_max_tokens,
    ai_review_frequency: v.ai_review_frequency,
    ai_review_block_weeks: v.ai_review_block_weeks,
    admin_allowed_origins: origins,
  };
}

export function ConfigPage() {
  const qc = useQueryClient();
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const configQuery = useQuery({
    queryKey: CONFIG_KEY,
    queryFn: () => api.get<Config>("/api/admin/config"),
  });

  const save = useMutation({
    mutationFn: (input: ConfigUpdate) =>
      api.put<Config>("/api/admin/config", input),
    onSuccess: () => {
      toast.success("Config saved");
      setTestResult(null);
      qc.invalidateQueries({ queryKey: CONFIG_KEY });
    },
    onError: (e) => {
      toast.error(e instanceof Error ? e.message : "Save failed");
    },
  });

  const testConnection = useMutation({
    mutationFn: (input: TestRequest) =>
      api.post<TestResult>("/api/admin/config/test-connection", input),
    onSuccess: (data) => {
      setTestResult(data);
    },
    onError: (e) => {
      setTestResult({
        status: "error",
        latency_ms: 0,
        response_text: null,
        error: e instanceof Error ? e.message : "Test failed",
      });
    },
  });

  if (configQuery.isLoading) {
    return <div className="p-6">Loading config…</div>;
  }
  if (configQuery.isError || !configQuery.data) {
    return (
      <div className="p-6 space-y-2">
        <p>Failed to load config.</p>
        <p className="text-sm text-muted-foreground">
          If this is a fresh deployment, make sure the seed migration has run.
        </p>
      </div>
    );
  }

  const config = configQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Config</h1>
        <p className="text-sm text-muted-foreground">
          Runtime-mutable settings. Changes take effect immediately —
          no restart required.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Test connection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Button
              onClick={() =>
                testConnection.mutate({
                  // No overrides — use saved config
                })
              }
              disabled={testConnection.isPending}
            >
              {testConnection.isPending ? "Testing…" : "Test connection"}
            </Button>
            {testResult && (
              <Badge variant={testResult.status === "ok" ? "default" : "destructive"}>
                {testResult.status === "ok" ? "OK" : "Error"}
              </Badge>
            )}
            {testResult && (
              <span className="text-sm text-muted-foreground tabular-nums">
                {testResult.latency_ms} ms
              </span>
            )}
          </div>
          {testResult?.status === "ok" && testResult.response_text && (
            <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
              {testResult.response_text}
            </pre>
          )}
          {testResult?.status === "error" && testResult.error && (
            <pre className="text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-2 rounded overflow-x-auto">
              {testResult.error}
            </pre>
          )}
        </CardContent>
      </Card>

      <ConfigForm
        key={`${config.ai_provider}:${config.ai_model}:${config.ai_api_key}:${config.ai_base_url}:${config.codex_auth_file}:${config.ai_reasoning_effort}:${config.ai_temperature}:${config.ai_max_tokens}:${config.ai_review_frequency}:${config.ai_review_block_weeks}:${(config.admin_allowed_origins ?? []).join(",")}`}
        defaultValues={config}
        isSaving={save.isPending}
        onSubmit={async (v) => {
          await save.mutateAsync(formValuesToUpdate(v));
        }}
      />
    </div>
  );
}
