import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

export type MeResponse = {
  username: string;
  expires_at: string;
};

export type LoginResponse = {
  ok: boolean;
  username: string;
  expires_at: string;
};

const ME_KEY = ["admin", "auth", "me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: () => api.get<MeResponse>("/api/admin/auth/me"),
    retry: false,
    refetchOnMount: "always",
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      api.post<LoginResponse>("/api/admin/auth/login", creds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/admin/auth/logout"),
    onSuccess: () => {
      qc.setQueryData(ME_KEY, null);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
