/**
 * Admin Users admin page — delta off MeasurementsPage.
 *
 * Notes:
 *   - RESOURCE uses the hyphenated path "admin-users" to match the backend.
 *   - password is write-only: it never appears on the response type, and
 *     we defensively strip any `password` key from the JSON tab payload so
 *     a hand-edited JSON blob can't silently replace the hash.
 *   - Self-delete returns a 400 from the backend; the toast surfaces the
 *     error message directly.
 */
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { AdminUserForm } from "@/components/forms/AdminUserForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type AdminUser = components["schemas"]["AdminAdminUserResponse"];
type AdminUserCreate = components["schemas"]["AdminAdminUserCreate"];
type AdminUserUpdate = components["schemas"]["AdminAdminUserUpdate"];

const RESOURCE = "admin-users";

export function AdminUsersPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<AdminUser | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const list = useList<AdminUser>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<AdminUser, AdminUserCreate>(RESOURCE);
  const update = useUpdate<AdminUser, AdminUserUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: AdminUser | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<AdminUser>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "username", header: "Username", sortable: true },
    {
      key: "is_active",
      header: "Active",
      render: (u) => (
        <Badge variant={u.is_active ? "default" : "secondary"}>
          {u.is_active ? "Active" : "Disabled"}
        </Badge>
      ),
    },
    {
      key: "created_at",
      header: "Created",
      sortable: true,
      render: (u) => u.created_at.replace("T", " ").slice(0, 16),
    },
    {
      key: "last_login_at",
      header: "Last login",
      render: (u) =>
        u.last_login_at ? u.last_login_at.replace("T", " ").slice(0, 16) : "—",
    },
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
      <h1 className="text-2xl font-semibold">Admin Users</h1>
      <DataTable<AdminUser>
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
        resourceLabel="admin users"
        toolbar={
          <Button onClick={() => setEditTarget("new")}>New admin user</Button>
        }
      />
      <EditSheet<AdminUser>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={
          editTarget === "new"
            ? "New admin user"
            : `Edit admin user${editRow ? ` "${editRow.username}"` : ""}`
        }
        row={editRow}
        form={
          <AdminUserForm
            mode={editTarget === "new" ? "create" : "edit"}
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as AdminUserCreate);
                  toast.success("Admin user created");
                } else if (editTarget) {
                  await update.mutateAsync({
                    id: editTarget.id,
                    input: v as AdminUserUpdate,
                  });
                  toast.success("Admin user updated");
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
            // Defensively strip password from JSON tab payloads: the
            // response model excludes it, but we never want a hand-edited
            // JSON blob to silently replace the bcrypt hash.
            const {
              id: _id,
              created_at: _created_at,
              last_login_at: _last_login_at,
              password: _password,
              ...rest
            } = parsed as AdminUser & { password?: string };
            void _id;
            void _created_at;
            void _last_login_at;
            void _password;
            await update.mutateAsync({
              id: editTarget.id,
              input: rest as AdminUserUpdate,
            });
            toast.success("Admin user updated via JSON");
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
          deleteTarget ? `Delete admin user "${deleteTarget.username}"?` : ""
        }
        description="This cannot be undone. You cannot delete yourself."
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Admin user deleted");
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
