/**
 * Generic data table for admin list pages.
 *
 * Intentionally NOT TanStack Table — that's ~20KB of extra bundle for
 * functionality we don't need (column reordering, row selection, etc.).
 * Each resource page supplies its own column definitions as a list of
 * {key, header, render?} triples.
 *
 * Pagination, sort, and search are HOISTED to the parent: this component
 * is purely presentational. The parent owns the state (usually via
 * useState + useList).
 */
import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type Column<T> = {
  /** Internal key for sort state. Matches the backend ALLOWED_SORT_COLUMNS. */
  key: string;
  /** Visible header text. */
  header: string;
  /** Optional custom cell renderer. Defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode;
  /** Is this column sortable? Must be in backend's ALLOWED_SORT_COLUMNS. */
  sortable?: boolean;
  /** Optional cell className (e.g. "text-right tabular-nums"). */
  className?: string;
};

export type SortState = {
  column: string;
  direction: "asc" | "desc";
} | null;

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  isLoading?: boolean;
  isError?: boolean;
  total: number;
  page: number;
  perPage: number;
  search: string;
  onSearchChange: (s: string) => void;
  onPageChange: (page: number) => void;
  sort: SortState;
  onSortChange: (sort: SortState) => void;
  onRowClick?: (row: T) => void;
  /** Resource name used in the empty state message. */
  resourceLabel?: string;
  /** Slot for action buttons (e.g. a "New user" button) above the table. */
  toolbar?: ReactNode;
  rowKey?: (row: T) => string | number;
};

export function DataTable<T>({
  columns,
  rows,
  isLoading = false,
  isError = false,
  total,
  page,
  perPage,
  search,
  onSearchChange,
  onPageChange,
  sort,
  onSortChange,
  onRowClick,
  resourceLabel = "items",
  toolbar,
  rowKey,
}: Props<T>) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const toggleSort = (col: Column<T>) => {
    if (!col.sortable) return;
    if (!sort || sort.column !== col.key) {
      onSortChange({ column: col.key, direction: "asc" });
    } else if (sort.direction === "asc") {
      onSortChange({ column: col.key, direction: "desc" });
    } else {
      onSortChange(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Input
          placeholder={`Search ${resourceLabel}...`}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="max-w-sm"
        />
        {toolbar}
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => {
                const isSorted = sort?.column === col.key;
                const Icon = !col.sortable
                  ? null
                  : !isSorted
                    ? ChevronsUpDown
                    : sort.direction === "asc"
                      ? ChevronUp
                      : ChevronDown;
                return (
                  <TableHead
                    key={col.key}
                    onClick={() => toggleSort(col)}
                    className={`${col.sortable ? "cursor-pointer select-none" : ""} ${col.className ?? ""}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.header}
                      {Icon && <Icon className="h-3 w-3 opacity-60" />}
                    </span>
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: Math.min(perPage, 8) }).map((_, i) => (
                <TableRow key={`sk-${i}`}>
                  {columns.map((col) => (
                    <TableCell key={col.key}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : isError ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-sm text-destructive">
                  Failed to load {resourceLabel}.
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-sm text-muted-foreground">
                  No {resourceLabel} found.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row, i) => (
                <TableRow
                  key={rowKey ? rowKey(row) : i}
                  onClick={() => onRowClick?.(row)}
                  className={onRowClick ? "cursor-pointer" : undefined}
                >
                  {columns.map((col) => (
                    <TableCell key={col.key} className={col.className}>
                      {col.render
                        ? col.render(row)
                        : String((row as unknown as Record<string, unknown>)[col.key] ?? "")}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <div>
          {total === 0
            ? "No results"
            : `Showing ${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)} of ${total}`}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1 || isLoading}
          >
            Previous
          </Button>
          <span>
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages || isLoading}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
