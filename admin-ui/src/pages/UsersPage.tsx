/**
 * Users admin page — canonical template for all phase 2 CRUD pages.
 *
 * State layout:
 *   - page/per_page/search/sort  → local state, passed to useList
 *   - editTarget                 → null | "new" | User (drives EditSheet)
 *   - deleteTarget               → null | User (drives DeleteDialog)
 *
 * This page is deliberately written without any helper/abstraction for the
 * table-edit-delete trio. Six more resource pages follow the exact same
 * pattern; consolidating them behind a generic <ResourcePage> would save
 * lines but hurt readability for a 7-page surface.
 */
import { useState } from "react";
import type { ComponentProps } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { UserForm } from "@/components/forms/UserForm";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type User = components["schemas"]["UserAdminResponse"];
type UserCreate = components["schemas"]["UserAdminCreate"];
type UserUpdate = components["schemas"]["UserAdminUpdate"];

const RESOURCE = "users";

const COLUMNS: Column<User>[] = [
  { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
  { key: "name", header: "Name", sortable: true },
  { key: "gender", header: "Gender" },
  { key: "age", header: "Age", sortable: true, className: "w-16 tabular-nums" },
  { key: "experience_level", header: "Experience", sortable: true },
  {
    key: "available_equipment",
    header: "Equipment",
    render: (u) => (u.available_equipment ?? []).join(", ") || "—",
  },
];

export function UsersPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<User | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const list = useList<User>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });

  const create = useCreate<User, UserCreate>(RESOURCE);
  const update = useUpdate<User, UserUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const handleFormSubmit = async (
    values: Parameters<ComponentProps<typeof UserForm>["onSubmit"]>[0],
  ) => {
    try {
      if (editTarget === "new") {
        await create.mutateAsync(values as UserCreate);
        toast.success("User created");
      } else if (editTarget) {
        await update.mutateAsync({
          id: editTarget.id,
          input: values as UserUpdate,
        });
        toast.success("User updated");
      }
      setEditTarget(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  };

  const handleJsonSave = async (parsed: User) => {
    if (editTarget === "new" || !editTarget) return;
    try {
      const { id: _id, created_at: _created_at, ...rest } = parsed;
      void _id;
      void _created_at;
      await update.mutateAsync({
        id: editTarget.id,
        input: rest as UserUpdate,
      });
      toast.success("User updated via JSON");
      setEditTarget(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "JSON save failed");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await del.mutateAsync(deleteTarget.id);
      toast.success("User deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteTarget(null);
    }
  };

  const editRow: User | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<User>[] = [
    ...COLUMNS,
    {
      key: "_actions",
      header: "",
      className: "w-32 text-right",
      render: (u) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(u);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(u);
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Users</h1>
      </div>

      <DataTable<User>
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
        rowKey={(u) => u.id}
        resourceLabel="users"
        toolbar={<Button onClick={() => setEditTarget("new")}>New user</Button>}
      />

      <EditSheet<User>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={
          editTarget === "new"
            ? "New user"
            : `Edit user #${editRow ? editRow.id : ""}`
        }
        row={editRow}
        form={
          <UserForm
            defaultValues={editRow}
            onSubmit={handleFormSubmit}
            isSaving={create.isPending || update.isPending}
          />
        }
        onJsonSave={handleJsonSave}
        isSaving={update.isPending}
      />

      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={deleteTarget ? `Delete user "${deleteTarget.name}"?` : ""}
        description="This cannot be undone."
        isPending={del.isPending}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
