/**
 * Workouts admin page.
 *
 * Adds a completed filter (all/completed/in-progress), a status badge
 * column, and a sets count column. The delete confirmation message
 * surfaces the child set count so an admin knows how many rows will
 * cascade.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { WorkoutForm } from "@/components/forms/WorkoutForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type Workout = components["schemas"]["WorkoutSessionAdminResponse"];
type WorkoutCreate = components["schemas"]["WorkoutSessionAdminCreate"];
type WorkoutUpdate = components["schemas"]["WorkoutSessionAdminUpdate"];

const RESOURCE = "workouts";

type CompletedFilter = "any" | "true" | "false";

export function WorkoutsPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [completed, setCompleted] = useState<CompletedFilter>("any");
  const [editTarget, setEditTarget] = useState<Workout | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workout | null>(null);

  const list = useList<Workout>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
    filters: {
      completed: completed === "any" ? undefined : completed,
    },
  });
  const create = useCreate<Workout, WorkoutCreate>(RESOURCE);
  const update = useUpdate<Workout, WorkoutUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: Workout | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<Workout>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    {
      key: "started_at",
      header: "Started",
      sortable: true,
      render: (w) => w.started_at.replace("T", " ").slice(0, 16),
    },
    {
      key: "status",
      header: "Status",
      render: (w) =>
        w.completed_at ? (
          <Badge variant="secondary">Completed</Badge>
        ) : (
          <Badge>In progress</Badge>
        ),
    },
    { key: "source", header: "Source" },
    {
      key: "sets_count",
      header: "Sets",
      render: (w) => (
        <span className="tabular-nums">{w.sets?.length ?? 0}</span>
      ),
      className: "text-right",
    },
    {
      key: "_actions",
      header: "",
      className: "w-32 text-right",
      render: (w) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(w);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(w);
            }}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  const toolbar = (
    <div className="flex items-center gap-2">
      <Select
        value={completed}
        onValueChange={(v) => {
          setCompleted(v as CompletedFilter);
          setPage(1);
        }}
      >
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="any">All</SelectItem>
          <SelectItem value="true">Completed</SelectItem>
          <SelectItem value="false">In progress</SelectItem>
        </SelectContent>
      </Select>
      <Button onClick={() => setEditTarget("new")}>New workout</Button>
    </div>
  );

  const deleteSetCount = deleteTarget?.sets?.length ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Workouts</h1>
      <DataTable<Workout>
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
        rowKey={(w) => w.id}
        resourceLabel="workouts"
        toolbar={toolbar}
      />
      <EditSheet<Workout>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={
          editTarget === "new"
            ? "New workout"
            : `Edit workout #${editRow ? editRow.id : ""}`
        }
        row={editRow}
        form={
          <WorkoutForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                const payload = {
                  ...v,
                  completed_at: v.completed_at || null,
                  notes: v.notes || null,
                };
                if (editTarget === "new") {
                  await create.mutateAsync(payload as WorkoutCreate);
                  toast.success("Workout created");
                } else if (editTarget) {
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: payload as WorkoutUpdate,
                  });
                  toast.success("Workout updated");
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
              sets: _sets,
              ...rest
            } = parsed;
            void _id;
            void _user_id;
            void _sets;
            await update.mutateAsync({
              id: editTarget.id,
              input: rest as WorkoutUpdate,
            });
            toast.success("Workout updated via JSON");
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
        title={deleteTarget ? `Delete workout #${deleteTarget.id}?` : ""}
        description={
          deleteTarget && deleteSetCount > 0
            ? `This will also delete ${deleteSetCount} set${deleteSetCount === 1 ? "" : "s"}. This cannot be undone.`
            : "This cannot be undone."
        }
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Workout deleted");
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
