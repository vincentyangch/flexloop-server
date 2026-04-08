/**
 * Measurements admin page — simple flat table following the UsersPage template.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { MeasurementForm } from "@/components/forms/MeasurementForm";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type Measurement = components["schemas"]["MeasurementAdminResponse"];
type MeasurementCreate = components["schemas"]["MeasurementAdminCreate"];
type MeasurementUpdate = components["schemas"]["MeasurementAdminUpdate"];

const RESOURCE = "measurements";

export function MeasurementsPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<Measurement | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Measurement | null>(null);

  const list = useList<Measurement>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<Measurement, MeasurementCreate>(RESOURCE);
  const update = useUpdate<Measurement, MeasurementUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: Measurement | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<Measurement>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    { key: "date", header: "Date", sortable: true, className: "w-28" },
    { key: "type", header: "Type" },
    {
      key: "value",
      header: "Value",
      sortable: true,
      className: "text-right tabular-nums",
    },
    { key: "notes", header: "Notes", render: (m) => m.notes ?? "—" },
    {
      key: "_actions",
      header: "",
      className: "w-32 text-right",
      render: (m) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(m);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(m);
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
      <h1 className="text-2xl font-semibold">Measurements</h1>
      <DataTable<Measurement>
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
        rowKey={(m) => m.id}
        resourceLabel="measurements"
        toolbar={
          <Button onClick={() => setEditTarget("new")}>New measurement</Button>
        }
      />
      <EditSheet<Measurement>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New measurement" : "Edit measurement"}
        row={editRow}
        form={
          <MeasurementForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as MeasurementCreate);
                  toast.success("Measurement created");
                } else if (editTarget) {
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: v as MeasurementUpdate,
                  });
                  toast.success("Measurement updated");
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
            const { id: _id, user_id: _user_id, ...rest } = parsed;
            void _id;
            void _user_id;
            await update.mutateAsync({
              id: editTarget.id,
              input: rest as MeasurementUpdate,
            });
            toast.success("Measurement updated via JSON");
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
        title={deleteTarget ? `Delete measurement #${deleteTarget.id}?` : ""}
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Measurement deleted");
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
