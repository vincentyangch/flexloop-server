/**
 * Left-panel tree view for the prompts editor.
 *
 * Lists every prompt name from ListPromptsResponse. Clicking a name
 * expands to show its versions. The active version (by "default" provider)
 * is marked with a small green dot. Selecting a version calls the
 * ``onSelect`` callback with ``{name, version}``.
 */
import { useEffect, useState } from "react";

import type { components } from "@/lib/api.types";

type PromptInfo = components["schemas"]["PromptInfoResponse"];

type Props = {
  prompts: PromptInfo[];
  selected: { name: string; version: string } | null;
  onSelect: (sel: { name: string; version: string }) => void;
};

export function PromptTree({ prompts, selected, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(selected ? [selected.name] : []),
  );

  // Keep the tree in sync with the parent's selection — when the
  // selected prompt changes (e.g. auto-select after initial load),
  // make sure that prompt's versions are visible.
  useEffect(() => {
    if (!selected) return;
    setExpanded((prev) => {
      if (prev.has(selected.name)) return prev;
      const next = new Set(prev);
      next.add(selected.name);
      return next;
    });
  }, [selected?.name]);

  const toggle = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  return (
    <div className="text-sm">
      {prompts.map((p) => {
        const isOpen = expanded.has(p.name);
        const activeDefault = p.active_by_provider?.default;
        return (
          <div key={p.name} className="mb-1">
            <button
              type="button"
              className="w-full text-left px-2 py-1 rounded hover:bg-muted font-medium flex items-center gap-2"
              onClick={() => toggle(p.name)}
            >
              <span className="text-xs text-muted-foreground w-3">
                {isOpen ? "▾" : "▸"}
              </span>
              <span className="flex-1">{p.name}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {p.versions.length}
              </span>
            </button>
            {isOpen && (
              <div className="ml-5 mt-1 space-y-0.5">
                {p.versions.map((v) => {
                  const isSelected =
                    selected?.name === p.name && selected?.version === v;
                  const isActive = activeDefault === v;
                  return (
                    <button
                      type="button"
                      key={v}
                      onClick={() => onSelect({ name: p.name, version: v })}
                      className={
                        "w-full text-left px-2 py-1 rounded flex items-center gap-2 " +
                        (isSelected ? "bg-muted font-medium" : "hover:bg-muted/50")
                      }
                    >
                      {isActive ? (
                        <span
                          className="inline-block h-2 w-2 rounded-full bg-green-500"
                          aria-label="active version"
                        />
                      ) : (
                        <span className="inline-block h-2 w-2" />
                      )}
                      <span className="tabular-nums">{v}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
