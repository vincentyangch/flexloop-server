/**
 * Generic CRUD hooks for admin resource pages.
 *
 * Every resource in phase 2 uses the same five operations with the same shape:
 *   - GET /api/admin/{resource}?<params>            → PaginatedResponse<T>
 *   - GET /api/admin/{resource}/{id}                → T
 *   - POST /api/admin/{resource}                    → T
 *   - PUT /api/admin/{resource}/{id}                → T
 *   - DELETE /api/admin/{resource}/{id}             → void
 *
 * The resource key (e.g. "users", "workouts") is used BOTH as the URL path
 * segment and as the root of the TanStack Query key, so invalidating writes
 * across list + detail is automatic.
 *
 * For non-standard paths like "ai/usage", pass the full path.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import { listParamsToQuery } from "@/lib/crud";
import type { ListParams, PaginatedResponse } from "@/lib/crud";

type ResourceKey = string;

function rootKey(resource: ResourceKey): string[] {
  return ["admin", "crud", resource];
}

function listKey(resource: ResourceKey, params: ListParams): (string | ListParams)[] {
  return [...rootKey(resource), "list", params];
}

function detailKey(resource: ResourceKey, id: string | number): (string | number)[] {
  return [...rootKey(resource), "detail", id];
}

export function useList<T>(resource: ResourceKey, params: ListParams = {}) {
  return useQuery({
    queryKey: listKey(resource, params),
    queryFn: () =>
      api.get<PaginatedResponse<T>>(
        `/api/admin/${resource}`,
        listParamsToQuery(params),
      ),
    placeholderData: (prev) => prev, // keep previous page while loading new one
  });
}

export function useDetail<T>(resource: ResourceKey, id: string | number | null) {
  return useQuery({
    queryKey: detailKey(resource, id ?? "none"),
    queryFn: () => api.get<T>(`/api/admin/${resource}/${id}`),
    enabled: id !== null && id !== undefined,
  });
}

export function useCreate<T, TInput>(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TInput) => api.post<T>(`/api/admin/${resource}`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
    },
  });
}

export function useUpdate<T, TInput>(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string | number; input: TInput }) =>
      api.put<T>(`/api/admin/${resource}/${id}`, input),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
      qc.invalidateQueries({ queryKey: detailKey(resource, variables.id) });
    },
  });
}

export function useDelete(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string | number) => api.delete(`/api/admin/${resource}/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
    },
  });
}
