/**
 * Admin Prompts editor page.
 *
 * Three-panel layout: PromptTree on the left, CodeMirror editor in the
 * center, VariableInspector on the right. Toolbar above the editor provides
 * Save / New version / Set active / Diff actions.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";

import { PromptTree } from "@/components/prompts/PromptTree";
import { PromptToolbar } from "@/components/prompts/PromptToolbar";
import { VariableInspector } from "@/components/prompts/VariableInspector";
import { DiffDialog } from "@/components/prompts/DiffDialog";
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
  const [diffOpen, setDiffOpen] = useState(false);

  const qc = useQueryClient();

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

  // Track which version's content is currently loaded into the buffer so
  // background refetches don't blow away unsaved edits. Keyed on the
  // identity of the selection, not the query's data reference.
  const loadedVersionRef = useRef<string | null>(null);

  useEffect(() => {
    if (!versionQuery.data) return;
    const key = `${versionQuery.data.name}@${versionQuery.data.version}`;
    // If we already loaded this exact version, leave the buffer alone —
    // this is a background refetch and the user may have unsaved edits.
    if (loadedVersionRef.current === key) return;
    loadedVersionRef.current = key;
    setBuffer(versionQuery.data.content);
  }, [versionQuery.data]);

  const isDirty = useMemo(
    () => versionQuery.data && buffer !== versionQuery.data.content,
    [versionQuery.data, buffer],
  );

  const save = useMutation({
    mutationFn: ({ name, version, content }: { name: string; version: string; content: string }) =>
      api.put<VersionResponse>(
        `/api/admin/prompts/${name}/versions/${version}`,
        { content },
      ),
    onSuccess: (data, variables) => {
      toast.success("Saved");
      // Reset the ref so the refetch can flow in; use the server's
      // round-trip value as the authoritative buffer.
      loadedVersionRef.current = null;
      setBuffer(data.content);
      qc.invalidateQueries({ queryKey: versionKey(variables.name, variables.version) });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Save failed"),
  });

  const createVersion = useMutation({
    mutationFn: ({ name }: { name: string }) =>
      api.post<VersionResponse>(`/api/admin/prompts/${name}/versions`, {}),
    onSuccess: (data, variables) => {
      toast.success(`Created ${data.version}`);
      setSelected({ name: variables.name, version: data.version });
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Create failed"),
  });

  const setActive = useMutation({
    mutationFn: ({ name, version }: { name: string; version: string }) =>
      api.put(`/api/admin/prompts/${name}/active`, { version, provider: "default" }),
    onSuccess: () => {
      toast.success("Active version updated");
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Set active failed"),
  });

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

      <div className="grid grid-cols-[240px_1fr_220px] gap-4 min-h-[60vh]">
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
              <PromptToolbar
                isDirty={!!isDirty}
                isSaving={save.isPending}
                isCreating={createVersion.isPending}
                isSettingActive={setActive.isPending}
                canSetActive={
                  listQuery.data.prompts.find((p) => p.name === selected.name)?.active_by_provider?.default
                    !== selected.version
                }
                onSave={() => save.mutate({
                  name: selected.name,
                  version: selected.version,
                  content: buffer,
                })}
                onNewVersion={() => createVersion.mutate({ name: selected.name })}
                onSetActive={() => setActive.mutate({
                  name: selected.name,
                  version: selected.version,
                })}
                onOpenDiff={() => setDiffOpen(true)}
              />
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

        {/* Right sidebar: variables */}
        <div>
          {selected && <VariableInspector content={buffer} />}
        </div>
      </div>

      {selected && versionQuery.data && (
        <DiffDialog
          open={diffOpen}
          onOpenChange={setDiffOpen}
          name={selected.name}
          currentVersion={selected.version}
          availableVersions={
            listQuery.data.prompts.find((p) => p.name === selected.name)?.versions ?? []
          }
        />
      )}
    </div>
  );
}
