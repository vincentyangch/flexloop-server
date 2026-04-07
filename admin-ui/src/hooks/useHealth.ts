import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type HealthComponentDB = {
  status: "healthy" | "degraded" | "down";
  ms?: number;
  db_size_bytes?: number;
  table_row_counts?: Record<string, number>;
  error?: string;
};

export type HealthResponse = {
  status: "healthy" | "degraded" | "down";
  checked_at: string;
  components: {
    database: HealthComponentDB;
  };
  recent_errors: Array<{
    timestamp: string;
    level: string;
    logger: string;
    message: string;
    exception: string | null;
  }>;
  system: {
    python: string;
    fastapi: string;
    uvicorn: string;
    os: string;
    hostname: string;
    uptime_seconds: number;
  };
};

export function useHealth() {
  return useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => api.get<HealthResponse>("/api/admin/health"),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}
