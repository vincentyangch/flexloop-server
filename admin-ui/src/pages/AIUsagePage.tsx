/**
 * AI Usage admin page — delta off MeasurementsPage.
 *
 * Resource path is "ai/usage" (two URL segments), which flows through useCrud
 * to `/api/admin/ai/usage`.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { AIUsageForm } from "@/components/forms/AIUsageForm";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type AIUsage = components["schemas"]["AIUsageAdminResponse"];
type AIUsageCreate = components["schemas"]["AIUsageAdminCreate"];
type AIUsageUpdate = components["schemas"]["AIUsageAdminUpdate"];

const RESOURCE = "ai/usage";

export function AIUsagePage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<AIUsage | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AIUsage | null>(null);

  const list = useList<AIUsage>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<AIUsage, AIUsageCreate>(RESOURCE);
  const update = useUpdate<AIUsage, AIUsageUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: AIUsage | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<AIUsage>[] = [
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    { key: "month", header: "Month", sortable: true, className: "w-24" },
    {
      key: "call_count",
      header: "Calls",
      sortable: true,
      className: "text-right tabular-nums",
    },
    {
      key: "total_input_tokens",
      header: "Input tok",
      sortable: true,
      className: "text-right tabular-nums",
    },
    {
      key: "total_output_tokens",
      header: "Output tok",
      sortable: true,
      className: "text-right tabular-nums",
    },
    {
      key: "estimated_cost",
      header: "Cost",
      sortable: true,
      className: "text-right tabular-nums",
      render: (row) => `$${row.estimated_cost.toFixed(4)}`,
    },
    {
      key: "_actions",
      header: "",
      className: "w-32 text-right",
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(r);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(r);
            }}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">AI Usage</h1>
      <DataTable<AIUsage>
        columns={columns}
        rows={list.data?.items ?? []}
        isLoading={list.isLoading}
        isError={list.isError}
        total={list.data?.total ?? 0}
        page={page}
        perPage={perPage}
        search={search}
        onSearchChange={(s) => {
          setSearch(s);
          setPage(1);
        }}
        onPageChange={setPage}
        sort={sort}
        onSortChange={setSort}
        rowKey={(r) => r.id}
        resourceLabel="usage rows"
        toolbar={
          <Button onClick={() => setEditTarget("new")}>New usage row</Button>
        }
      />
      <EditSheet<AIUsage>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New usage row" : "Edit usage row"}
        row={editRow}
        form={
          <AIUsageForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as AIUsageCreate);
                  toast.success("Usage row created");
                } else if (editTarget) {
                  // user_id and month are form-only on edit — AIUsageAdminUpdate
                  // uses extra="forbid" and only accepts the 6 counter fields.
                  const { user_id: _uid, month: _month, ...rest } = v;
                  void _uid;
                  void _month;
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: rest as AIUsageUpdate,
                  });
                  toast.success("Usage row updated");
                }
                setEditTarget(null);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Save failed");
              }
            }}
          />
        }
        onJsonSave={async (parsed) => {
          if (editTarget === "new" || !editTarget) return;
          try {
            const {
              id: _id,
              user_id: _user_id,
              month: _month,
              ...rest
            } = parsed;
            void _id;
            void _user_id;
            void _month;
            await update.mutateAsync({
              id: editTarget.id,
              input: rest as AIUsageUpdate,
            });
            toast.success("Usage row updated via JSON");
            setEditTarget(null);
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "JSON save failed");
          }
        }}
        isSaving={update.isPending}
      />
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={deleteTarget ? `Delete usage row #${deleteTarget.id}?` : ""}
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Usage row deleted");
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Delete failed");
          } finally {
            setDeleteTarget(null);
          }
        }}
      />
    </div>
  );
}
