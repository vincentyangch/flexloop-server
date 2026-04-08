/**
 * Shared CRUD types used by the generic useList/useDetail/useCreate/... hooks.
 *
 * `PaginatedResponse<T>` mirrors the backend's ``flexloop.admin.schemas.common.PaginatedResponse``.
 * Resource-specific item types come from `lib/api.types.ts` (generated from the FastAPI OpenAPI).
 */

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
};

export type ListParams = {
  page?: number;
  per_page?: number;
  search?: string;
  sort?: string;
  /** Resource-specific filters. Stored as a flat dict; the hook serializes them to `filter[key]=value`. */
  filters?: Record<string, string | number | boolean | undefined>;
};

/** Turn a ListParams into a flat query-string params object for `api.get(..., params)`. */
export function listParamsToQuery(params: ListParams): Record<string, string | number | undefined> {
  const q: Record<string, string | number | undefined> = {};
  if (params.page !== undefined) q.page = params.page;
  if (params.per_page !== undefined) q.per_page = params.per_page;
  if (params.search) q.search = params.search;
  if (params.sort) q.sort = params.sort;
  if (params.filters) {
    for (const [k, v] of Object.entries(params.filters)) {
      if (v === undefined || v === "" || v === null) continue;
      q[`filter[${k}]`] = String(v);
    }
  }
  return q;
}
