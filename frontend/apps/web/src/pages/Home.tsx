import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { CheckCircle2, Clock3, Database, ListChecks, Plus, Terminal } from "lucide-react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { useConnections } from "@/api/hooks/useConnections";
import type { QueryHistoryRead } from "@/api/hooks/useQueryHistory";
import { useQueryHistory } from "@/api/hooks/useQueryHistory";
import type { HealthResponse } from "@/api/types";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

async function fetchHealth(): Promise<HealthResponse> {
  const { data, error, response } = await apiClient.GET("/health");

  if (error !== undefined) {
    throw { data, error, response };
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
  const history = useQueryHistory({ limit: 10 });
  const connections = useConnections();
  const connectionNames = new Map(
    (connections.data?.items ?? []).map((connection) => [connection.id, connection.name]),
  );
  const recentHistory = (history.data?.items ?? []).slice(0, 10);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">欢迎使用 AgentLens</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          用 SQL 连接已有 MySQL trajectory 数据，快速进入查询、可视化和打标分析流程。
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <QuickEntryCard
          icon={<Database className="h-5 w-5" aria-hidden="true" />}
          title="新建连接"
          description="配置只读 MySQL 数据源。"
          to="/connections"
        />
        <QuickEntryCard
          icon={<Terminal className="h-5 w-5" aria-hidden="true" />}
          title="新建查询"
          description="打开 SQL 编辑器并运行查询。"
          to="/query"
        />
        <QuickEntryCard
          icon={<ListChecks className="h-5 w-5" aria-hidden="true" />}
          title="查看查询列表"
          description="管理命名查询和临时查询。"
          to="/queries"
        />
      </div>

      <div className="rounded-lg border bg-card p-5 text-card-foreground shadow-sm">
        {healthQuery.isLoading ? (
          <LoadingState label="Checking backend status..." rows={2} className="border-0 p-0" />
        ) : healthQuery.isError || health === undefined ? (
          <ErrorState
            title="Backend status unavailable"
            error={healthQuery.error}
            action={
              <Button variant="outline" size="sm" onClick={() => void healthQuery.refetch()}>
                Retry
              </Button>
            }
          />
        ) : (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
            <span>
              Backend status: {health.status} · version {health.version}
            </span>
          </div>
        )}
      </div>

      <section className="rounded-lg border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">最近查询</h2>
            <p className="mt-1 text-sm text-muted-foreground">最近 10 条 query_history。</p>
          </div>
          <Link to="/query" className={cn(buttonVariants({ size: "sm" }), "gap-2")}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新建查询
          </Link>
        </div>

        {history.isLoading ? (
          <LoadingState label="正在加载最近查询..." rows={5} className="rounded-none border-0" />
        ) : history.isError ? (
          <ErrorState
            error={history.error}
            className="m-4"
            action={
              <Button variant="outline" size="sm" onClick={() => void history.refetch()}>
                重试
              </Button>
            }
          />
        ) : recentHistory.length === 0 ? (
          <EmptyState
            icon={<Clock3 className="h-6 w-6" aria-hidden="true" />}
            title="暂无查询历史"
            description="运行第一条 SQL 后，这里会显示最近执行记录。"
            className="m-4"
            action={
              <Link to="/query" className={cn(buttonVariants({ variant: "outline" }))}>
                新建查询
              </Link>
            }
          />
        ) : (
          <div className="divide-y">
            {recentHistory.map((item) => (
              <div key={item.id} className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatDateTime(item.executed_at)}</span>
                    <span>·</span>
                    <span>{connectionNames.get(item.connection_id) ?? `#${item.connection_id}`}</span>
                    <span>·</span>
                    <span className={item.status === "success" ? "text-emerald-700" : "text-destructive"}>
                      {item.status}
                    </span>
                    {item.row_count !== null ? <span>· {item.row_count} 行</span> : null}
                    {item.duration_ms !== null ? <span>· {Math.round(item.duration_ms)}ms</span> : null}
                  </div>
                  <div className="mt-2 truncate font-mono text-xs">{previewSql(item.sql_text)}</div>
                  {item.error_message !== null ? (
                    <div className="mt-1 truncate text-xs text-destructive">{item.error_message}</div>
                  ) : null}
                </div>
                <Link
                  to={getHistoryOpenPath(item)}
                  state={getHistoryOpenState(item)}
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }), "shrink-0")}
                >
                  打开
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

type QuickEntryCardProps = {
  icon: ReactNode;
  title: string;
  description: string;
  to: string;
};

function QuickEntryCard({ icon, title, description, to }: QuickEntryCardProps) {
  return (
    <Link
      to={to}
      className="rounded-lg border bg-card p-5 text-card-foreground shadow-sm transition-colors hover:bg-accent/50"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-md border bg-background p-2 text-foreground">{icon}</div>
        <div>
          <div className="font-medium">{title}</div>
          <div className="mt-1 text-sm text-muted-foreground">{description}</div>
        </div>
      </div>
    </Link>
  );
}

function previewSql(sql: string): string {
  const compact = sql.replace(/\s+/g, " ").trim();
  return compact.length > 100 ? `${compact.slice(0, 100)}...` : compact;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getHistoryOpenPath(item: QueryHistoryRead): string {
  if (item.query_id !== null) {
    return `/query/${item.query_id}`;
  }

  return `/query?connection_id=${item.connection_id}`;
}

function getHistoryOpenState(item: QueryHistoryRead): { initialSql: string } | undefined {
  return item.query_id === null ? { initialSql: item.sql_text } : undefined;
}
