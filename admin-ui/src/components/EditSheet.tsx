/**
 * Slide-out drawer for creating/editing admin resources.
 *
 * Exposes two tabs:
 *  - "Form": whatever node the parent passes via the `form` prop (typically
 *    a resource-specific react-hook-form component).
 *  - "JSON": the raw JSON editor, only shown when editing an existing row.
 *
 * The parent owns the mutation state. This component is just layout.
 */
import type { ReactNode } from "react";

import { JsonEditor } from "@/components/JsonEditor";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

type Props<T> = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** The current row being edited. If null, the JSON tab is hidden. */
  row: T | null;
  form: ReactNode;
  onJsonSave: (parsed: T) => void | Promise<void>;
  isSaving?: boolean;
};

export function EditSheet<T>({
  open,
  onOpenChange,
  title,
  description,
  row,
  form,
  onJsonSave,
  isSaving = false,
}: Props<T>) {
  const showJson = row !== null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>

        <div className="mt-6">
          {showJson ? (
            <Tabs defaultValue="form">
              <TabsList>
                <TabsTrigger value="form">Form</TabsTrigger>
                <TabsTrigger value="json">JSON</TabsTrigger>
              </TabsList>
              <TabsContent value="form" className="mt-4">
                {form}
              </TabsContent>
              <TabsContent value="json" className="mt-4">
                <JsonEditor value={row} onSave={onJsonSave} isSaving={isSaving} />
              </TabsContent>
            </Tabs>
          ) : (
            form
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
