import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types.gen";
import { Button } from "@/components/ui/button";

type HealthResponse = components["schemas"]["HealthResponse"];

async function fetchHealth(): Promise<HealthResponse> {
  const { data, error, response } = await apiClient.GET("/health");

  if (error !== undefined) {
    throw new Error(`Health check failed: ${JSON.stringify(error)}`);
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return data;
}

export function Home() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });
  const health = healthQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">AgentLens</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          SQL-first trajectory visualization and labeling workspace for agent developers.
        </p>
      </div>

      <div className="rounded-lg border bg-card p-5 text-card-foreground shadow-sm">
        {healthQuery.isLoading ? (
          <div className="text-sm text-muted-foreground">Checking backend status...</div>
        ) : healthQuery.isError || health === undefined ? (
          <div className="flex items-center gap-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <span>Backend status unavailable</span>
            <Button variant="outline" size="sm" onClick={() => void healthQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
            <span>
              Backend status: {health.status} · version {health.version}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
