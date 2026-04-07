import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry on 401 — the AuthGate will redirect
        if (error instanceof Error && error.message.startsWith("401:")) return false;
        return failureCount < 2;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  },
});
