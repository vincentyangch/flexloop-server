/**
 * Simple JSON escape hatch — a textarea that validates on save.
 *
 * This is NOT a syntax-highlighted JSON editor; for ~7 admin resources
 * that's overkill. If we ever add CodeMirror for the prompt editor in
 * phase 4, revisit whether to reuse it here.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Props<T> = {
  value: T;
  onSave: (parsed: T) => void | Promise<void>;
  isSaving?: boolean;
};

export function JsonEditor<T>({ value, onSave, isSaving = false }: Props<T>) {
  const initial = JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    let parsed: T;
    try {
      parsed = JSON.parse(text) as T;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setError(null);
    await onSave(parsed);
  };

  const isDirty = text !== initial;

  return (
    <div className="space-y-2">
      <Textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        rows={18}
        className="font-mono text-xs"
        spellCheck={false}
      />
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setText(initial);
            setError(null);
          }}
          disabled={!isDirty || isSaving}
        >
          Reset
        </Button>
        <Button size="sm" onClick={() => void handleSave()} disabled={!isDirty || isSaving}>
          {isSaving ? "Saving..." : "Save JSON"}
        </Button>
      </div>
    </div>
  );
}
