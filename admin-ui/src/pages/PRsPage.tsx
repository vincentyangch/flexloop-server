/**
 * Personal Records admin page — delta off MeasurementsPage.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { PRForm } from "@/components/forms/PRForm";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type PersonalRecord = components["schemas"]["PersonalRecordAdminResponse"];
type PersonalRecordCreate = components["schemas"]["PersonalRecordAdminCreate"];
type PersonalRecordUpdate = components["schemas"]["PersonalRecordAdminUpdate"];

const RESOURCE = "prs";

export function PRsPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<PersonalRecord | "new" | null>(
    null,
  );
  const [deleteTarget, setDeleteTarget] = useState<PersonalRecord | null>(null);

  const list = useList<PersonalRecord>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<PersonalRecord, PersonalRecordCreate>(RESOURCE);
  const update = useUpdate<PersonalRecord, PersonalRecordUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: PersonalRecord | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<PersonalRecord>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    {
      key: "exercise_id",
      header: "Exercise",
      sortable: true,
      className: "w-24 tabular-nums",
    },
    { key: "pr_type", header: "Type", sortable: true },
    {
      key: "value",
      header: "Value",
      sortable: true,
      className: "text-right tabular-nums",
    },
    {
      key: "achieved_at",
      header: "Achieved",
      sortable: true,
      render: (r) => r.achieved_at.slice(0, 16),
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
      <h1 className="text-2xl font-semibold">Personal Records</h1>
      <DataTable<PersonalRecord>
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
        resourceLabel="PRs"
        toolbar={<Button onClick={() => setEditTarget("new")}>New PR</Button>}
      />
      <EditSheet<PersonalRecord>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New PR" : "Edit PR"}
        row={editRow}
        form={
          <PRForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as PersonalRecordCreate);
                  toast.success("PR created");
                } else if (editTarget) {
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: v as PersonalRecordUpdate,
                  });
                  toast.success("PR updated");
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
              input: rest as PersonalRecordUpdate,
            });
            toast.success("PR updated via JSON");
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
        title={deleteTarget ? `Delete PR #${deleteTarget.id}?` : ""}
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("PR deleted");
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
