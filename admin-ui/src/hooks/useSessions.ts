import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type SessionInfo = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
  is_current: boolean;
};

const KEY = ["admin", "auth", "sessions"] as const;

export function useSessions() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<SessionInfo[]>("/api/admin/auth/sessions"),
  });
}

export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/admin/auth/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
