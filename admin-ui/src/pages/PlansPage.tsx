/**
 * Plans admin list page.
 *
 * Supports list, filter by status + user_id, search, pagination, create
 * (empty plan via POST with metadata only), inline metadata edit via
 * EditSheet, hard-delete with cascade confirmation.
 *
 * Row click / "Open" button navigates to /plans/:id (the detail page
 * delivered in Chunk 4) where day-level edits happen.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { PlanForm } from "@/components/forms/PlanForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];
type PlanCreate = components["schemas"]["PlanAdminCreate"];
type PlanUpdate = components["schemas"]["PlanAdminUpdate"];

const RESOURCE = "plans";

type StatusFilter = "any" | "active" | "inactive" | "archived";

export function PlansPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [status, setStatus] = useState<StatusFilter>("any");
  const [userFilter, setUserFilter] = useState<string>("");
  const [editTarget, setEditTarget] = useState<Plan | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Plan | null>(null);

  const list = useList<Plan>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
    filters: {
      status: status === "any" ? undefined : status,
      user_id: userFilter || undefined,
    },
  });
  const create = useCreate<Plan, PlanCreate>(RESOURCE);
  const update = useUpdate<Plan, PlanUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: Plan | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<Plan>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "name", header: "Name", sortable: true },
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    { key: "split_type", header: "Split" },
    {
      key: "cycle_length",
      header: "Cycle",
      className: "w-20 tabular-nums text-right",
    },
    {
      key: "days",
      header: "Days",
      render: (p) => (
        <span className="tabular-nums">{p.days?.length ?? 0}</span>
      ),
      className: "text-right w-16",
    },
    {
      key: "status",
      header: "Status",
      render: (p) => (
        <Badge variant={p.status === "active" ? "default" : "secondary"}>
          {p.status}
        </Badge>
      ),
    },
    {
      key: "_actions",
      header: "",
      className: "w-48 text-right",
      render: (p) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/plans/${p.id}`);
            }}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(p);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(p);
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
      <Input
        className="w-28"
        placeholder="user id"
        value={userFilter}
        onChange={(e) => {
          setUserFilter(e.target.value);
          setPage(1);
        }}
      />
      <Select
        value={status}
        onValueChange={(v) => {
          setStatus(v as StatusFilter);
          setPage(1);
        }}
      >
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="any">All statuses</SelectItem>
          <SelectItem value="active">Active</SelectItem>
          <SelectItem value="inactive">Inactive</SelectItem>
          <SelectItem value="archived">Archived</SelectItem>
        </SelectContent>
      </Select>
      <Button onClick={() => setEditTarget("new")}>New plan</Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Plans</h1>
      <DataTable<Plan>
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
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/plans/${p.id}`)}
        resourceLabel="plans"
        toolbar={toolbar}
      />
      <EditSheet<Plan>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={
          editTarget === "new"
            ? "New plan"
            : `Edit plan #${editRow ? editRow.id : ""}`
        }
        row={editRow}
        form={
          <PlanForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                // Normalize empty date strings to null for the API.
                const payload = {
                  ...v,
                  block_start: v.block_start || null,
                  block_end: v.block_end || null,
                };
                if (editTarget === "new") {
                  await create.mutateAsync(payload as PlanCreate);
                  toast.success("Plan created");
                } else if (editRow) {
                  // Update payload shouldn't include user_id (not in update schema).
                  const { user_id: _user_id, ...updatePayload } = payload;
                  void _user_id;
                  await update.mutateAsync({
                    id: editRow.id,
                    input: updatePayload as PlanUpdate,
                  });
                  toast.success("Plan updated");
                }
                setEditTarget(null);
              } catch (e) {
                toast.error((e as Error).message);
              }
            }}
          />
        }
        onJsonSave={async (parsed) => {
          if (editTarget === "new" || !editRow) return;
          try {
            const {
              id: _id,
              user_id: _user_id,
              days: _days,
              ...rest
            } = parsed;
            void _id;
            void _user_id;
            void _days;
            await update.mutateAsync({
              id: editRow.id,
              input: rest as PlanUpdate,
            });
            toast.success("Plan updated via JSON");
            setEditTarget(null);
          } catch (e) {
            toast.error((e as Error).message);
          }
        }}
        isSaving={update.isPending}
      />
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete plan?"
        description={
          deleteTarget
            ? `Delete "${deleteTarget.name}"? This will also delete all days, groups, exercises, and set targets. This cannot be undone.`
            : ""
        }
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Plan deleted");
            setDeleteTarget(null);
          } catch (e) {
            toast.error((e as Error).message);
          }
        }}
      />
    </div>
  );
}
