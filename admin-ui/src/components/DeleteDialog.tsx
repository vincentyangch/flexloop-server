/**
 * Reusable confirm-delete dialog.
 *
 * Usage:
 *   const [target, setTarget] = useState<User | null>(null);
 *   const del = useDelete("users");
 *   ...
 *   <DeleteDialog
 *     open={target !== null}
 *     onOpenChange={(o) => !o && setTarget(null)}
 *     title={`Delete user "${target?.name}"?`}
 *     description="This cannot be undone."
 *     isPending={del.isPending}
 *     onConfirm={async () => {
 *       if (target) await del.mutateAsync(target.id);
 *       setTarget(null);
 *     }}
 *   />
 */
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  isPending?: boolean;
  onConfirm: () => void | Promise<void>;
};

export function DeleteDialog({
  open,
  onOpenChange,
  title,
  description = "This cannot be undone.",
  confirmLabel = "Delete",
  isPending = false,
  onConfirm,
}: Props) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              void onConfirm();
            }}
            disabled={isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isPending ? "Deleting..." : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
