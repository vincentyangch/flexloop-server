/**
 * Toolbar above the prompt editor.
 *
 * Save: PUT current buffer to the selected version
 * New version: POST to /versions — clones active
 * Set as active: PUT /active with the selected version
 * Diff: opens the DiffDialog
 */
import { Button } from "@/components/ui/button";

type Props = {
  isDirty: boolean;
  isSaving: boolean;
  isCreating: boolean;
  isSettingActive: boolean;
  canSetActive: boolean;
  onSave: () => void;
  onNewVersion: () => void;
  onSetActive: () => void;
  onOpenDiff: () => void;
};

export function PromptToolbar({
  isDirty,
  isSaving,
  isCreating,
  isSettingActive,
  canSetActive,
  onSave,
  onNewVersion,
  onSetActive,
  onOpenDiff,
}: Props) {
  return (
    <div className="flex items-center gap-2 pb-2 border-b">
      <Button
        size="sm"
        onClick={onSave}
        disabled={!isDirty || isSaving}
      >
        {isSaving ? "Saving…" : "Save"}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={onNewVersion}
        disabled={isCreating}
      >
        {isCreating ? "Cloning…" : "New version"}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={onSetActive}
        disabled={!canSetActive || isSettingActive}
      >
        {isSettingActive ? "Setting…" : "Set as active"}
      </Button>
      <Button size="sm" variant="ghost" onClick={onOpenDiff}>
        Diff…
      </Button>
    </div>
  );
}
