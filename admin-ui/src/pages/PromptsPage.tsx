/**
 * Admin Prompts editor page.
 *
 * Two-panel layout: PromptTree on the left, CodeMirror editor on the right.
 * This first iteration is READ-ONLY — the editor shows the selected
 * version's content but the Save / New version / Set active / Diff
 * toolbar actions are added in a later task.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";

import { PromptTree } from "@/components/prompts/PromptTree";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type ListResponse = components["schemas"]["ListPromptsResponse"];
type VersionResponse = components["schemas"]["PromptVersionResponse"];

const LIST_KEY = ["admin", "prompts", "list"];

function versionKey(name: string, version: string) {
  return ["admin", "prompts", "version", name, version];
}

export function PromptsPage() {
  const [selected, setSelected] = useState<{ name: string; version: string } | null>(
    null,
  );
  const [buffer, setBuffer] = useState<string>("");

  const listQuery = useQuery({
    queryKey: LIST_KEY,
    queryFn: () => api.get<ListResponse>("/api/admin/prompts"),
  });

  // Auto-select the first prompt's active version on first load
  useEffect(() => {
    if (selected !== null || !listQuery.data) return;
    const first = listQuery.data.prompts[0];
    if (first && first.versions.length > 0) {
      setSelected({
        name: first.name,
        version: first.active_by_provider?.default ?? first.versions[0],
      });
    }
  }, [listQuery.data, selected]);

  const versionQuery = useQuery({
    queryKey: selected
      ? versionKey(selected.name, selected.version)
      : ["admin", "prompts", "version", "none"],
    queryFn: () =>
      api.get<VersionResponse>(
        `/api/admin/prompts/${selected!.name}/versions/${selected!.version}`,
      ),
    enabled: selected !== null,
  });

  // Sync the buffer with the loaded version content
  useEffect(() => {
    if (versionQuery.data) {
      setBuffer(versionQuery.data.content);
    }
  }, [versionQuery.data]);

  const isDirty = useMemo(
    () => versionQuery.data && buffer !== versionQuery.data.content,
    [versionQuery.data, buffer],
  );

  if (listQuery.isLoading) {
    return <div className="p-6">Loading prompts…</div>;
  }
  if (listQuery.isError || !listQuery.data) {
    return <div className="p-6">Failed to load prompts.</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Prompts</h1>
        <p className="text-sm text-muted-foreground">
          Edit AI prompt templates. Changes take effect on the next generation
          — no server restart required.
        </p>
      </div>

      <div className="grid grid-cols-[240px_1fr] gap-4 min-h-[60vh]">
        {/* Left panel: tree */}
        <div className="border rounded-md p-2 overflow-auto">
          <PromptTree
            prompts={listQuery.data.prompts}
            selected={selected}
            onSelect={setSelected}
          />
        </div>

        {/* Right panel: editor */}
        <div className="border rounded-md p-2 flex flex-col">
          {selected === null ? (
            <div className="text-sm text-muted-foreground p-4">
              Select a prompt version from the tree.
            </div>
          ) : versionQuery.isLoading ? (
            <div className="text-sm text-muted-foreground p-4">
              Loading version…
            </div>
          ) : versionQuery.isError || !versionQuery.data ? (
            <div className="text-sm text-red-500 p-4">
              Failed to load version.
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">
                  {selected.name} / {selected.version}
                  {isDirty && (
                    <span className="ml-2 text-xs text-amber-600 dark:text-amber-400">
                      • unsaved
                    </span>
                  )}
                </div>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden border rounded">
                <CodeMirror
                  value={buffer}
                  extensions={[markdown()]}
                  theme={oneDark}
                  onChange={(v) => setBuffer(v)}
                  height="60vh"
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
