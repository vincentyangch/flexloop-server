import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type HealthComponentDB = {
  status: "healthy" | "degraded" | "down";
  ms?: number;
  db_size_bytes?: number;
  table_row_counts?: Record<string, number>;
  error?: string;
};

export type HealthComponentAI = {
  status: "healthy" | "degraded" | "unconfigured";
  provider: string;
  model: string;
  has_key: boolean;
  reachable: boolean;
  cached?: boolean;
  error?: string;
};

export type HealthComponentDisk = {
  total_bytes?: number;
  free_bytes?: number;
  used_pct?: number;
  error?: string;
};

export type HealthComponentMemory = {
  rss_bytes?: number;
  vms_bytes?: number;
  error?: string;
};

export type HealthComponentBackups = {
  count?: number;
  last_at?: string;
  total_bytes?: number;
  error?: string;
};

export type HealthComponentMigrations = {
  current_rev?: string;
  head_rev?: string;
  in_sync?: boolean;
  error?: string;
};

export type HealthResponse = {
  status: "healthy" | "degraded" | "down";
  checked_at: string;
  components: {
    database: HealthComponentDB;
    ai_provider: HealthComponentAI;
    disk: HealthComponentDisk;
    memory: HealthComponentMemory;
    backups: HealthComponentBackups;
    migrations: HealthComponentMigrations;
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
