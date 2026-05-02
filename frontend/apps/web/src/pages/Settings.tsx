import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { AdminInfoResponse } from "@/api/types";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Button } from "@/components/ui/button";

async function fetchAdminInfo(): Promise<AdminInfoResponse> {
  const { data, error, response } = await apiClient.GET("/admin/info");

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load admin info with status ${response.status}`);
  }

  return data;
}

export function Settings() {
  const adminInfo = useQuery({
    queryKey: ["admin-info"],
    queryFn: fetchAdminInfo,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          查看当前 AgentLens 运行信息。
        </p>
      </div>

      <div className="rounded-lg border bg-card p-5 shadow-sm">
        {adminInfo.isLoading ? (
          <LoadingState label="正在加载运行信息..." rows={5} className="border-0 p-0" />
        ) : adminInfo.isError || adminInfo.data === undefined ? (
          <ErrorState
            error={adminInfo.error}
            action={
              <Button variant="outline" size="sm" onClick={() => void adminInfo.refetch()}>
                重试
              </Button>
            }
          />
        ) : (
          <AdminInfoPanel info={adminInfo.data} />
        )}
      </div>
    </div>
  );
}

function AdminInfoPanel({ info }: { info: AdminInfoResponse }) {
  return (
    <div className="space-y-5 text-sm">
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Version" value={info.version} />
        <Metric label="Connections" value={String(info.connections_count)} />
        <Metric label="Named Queries" value={String(info.named_queries_count)} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <InfoRow label="Data Dir" value={info.data_dir} />
        <InfoRow label="Metadata DB" value={info.db_path} />
        <InfoRow label="Uptime" value={`${info.uptime_seconds}s`} />
        <InfoRow
          label="Scheduler"
          value={
            info.scheduler_jobs.length > 0
              ? info.scheduler_jobs.map((job) => `${job.id}: ${job.next_run ?? "pending"}`).join(", ")
              : "no jobs"
          }
        />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="text-xs font-medium uppercase text-muted-foreground">{label}</div>
      <div className="mt-2 break-words text-lg font-semibold">{value}</div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="text-xs font-medium uppercase text-muted-foreground">{label}</div>
      <div className="mt-2 break-all font-mono text-xs text-muted-foreground">{value}</div>
    </div>
  );
}
