/**
 * Exercises admin page — delta off MeasurementsPage.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { ExerciseForm } from "@/components/forms/ExerciseForm";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type Exercise = components["schemas"]["ExerciseAdminResponse"];
type ExerciseCreate = components["schemas"]["ExerciseAdminCreate"];
type ExerciseUpdate = components["schemas"]["ExerciseAdminUpdate"];

const RESOURCE = "exercises";

export function ExercisesPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<Exercise | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Exercise | null>(null);

  const list = useList<Exercise>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<Exercise, ExerciseCreate>(RESOURCE);
  const update = useUpdate<Exercise, ExerciseUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: Exercise | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<Exercise>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "name", header: "Name", sortable: true },
    { key: "muscle_group", header: "Muscle group", sortable: true },
    { key: "equipment", header: "Equipment", sortable: true },
    { key: "category", header: "Category", sortable: true },
    { key: "difficulty", header: "Difficulty", sortable: true },
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
      <h1 className="text-2xl font-semibold">Exercises</h1>
      <DataTable<Exercise>
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
        resourceLabel="exercises"
        toolbar={
          <Button onClick={() => setEditTarget("new")}>New exercise</Button>
        }
      />
      <EditSheet<Exercise>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New exercise" : "Edit exercise"}
        row={editRow}
        form={
          <ExerciseForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as ExerciseCreate);
                  toast.success("Exercise created");
                } else if (editTarget) {
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: v as ExerciseUpdate,
                  });
                  toast.success("Exercise updated");
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
            const { id: _id, ...rest } = parsed;
            void _id;
            await update.mutateAsync({
              id: editTarget.id,
              input: rest as ExerciseUpdate,
            });
            toast.success("Exercise updated via JSON");
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
        title={
          deleteTarget
            ? `Delete exercise "${deleteTarget.name}"?`
            : ""
        }
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Exercise deleted");
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
