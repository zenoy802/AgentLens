import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { CheckCircle2, Clock3, Database, ListChecks, Plus, Terminal } from "lucide-react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { useConnections } from "@/api/hooks/useConnections";
import type { QueryHistoryRead } from "@/api/hooks/useQueryHistory";
import { useQueryHistory } from "@/api/hooks/useQueryHistory";
import type { QueryDetailState, QueryListParams } from "@/api/hooks/useQueries";
import { useQueries, useQueryDetailsByIds } from "@/api/hooks/useQueries";
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
  const namedQueryParams = useMemo<QueryListParams>(
    () => ({
      is_named: true,
      include_expired: false,
      order_by: "last_executed_at",
      page_size: 10,
    }),
    [],
  );
  const namedQueries = useQueries(namedQueryParams);
  const connections = useConnections();
  const connectionNames = new Map(
    (connections.data?.items ?? []).map((connection) => [connection.id, connection.name]),
  );
  const recentHistory = useMemo(
    () => (history.data?.items ?? []).slice(0, 10),
    [history.data?.items],
  );
  const recentHistoryQueryIds = useMemo(
    () =>
      recentHistory
        .map((item) => item.query_id)
        .filter((queryId): queryId is number => queryId !== null),
    [recentHistory],
  );
  const historyQueryStates = useQueryDetailsByIds(recentHistoryQueryIds);
  const topNamedQueries = (namedQueries.data?.items ?? []).slice(0, 10);

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
            <h2 className="text-base font-semibold">最近执行</h2>
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
              <div
                key={item.id}
                className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center"
              >
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
                <HistoryOpenAction
                  item={item}
                  queryState={getHistoryQueryState(item, historyQueryStates)}
                />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">我的命名查询</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              按最近执行时间排序的前 10 条。
            </p>
          </div>
          <Link to="/queries" className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
            管理查询
          </Link>
        </div>

        {namedQueries.isLoading ? (
          <LoadingState label="正在加载命名查询..." rows={5} className="rounded-none border-0" />
        ) : namedQueries.isError ? (
          <ErrorState
            error={namedQueries.error}
            className="m-4"
            action={
              <Button variant="outline" size="sm" onClick={() => void namedQueries.refetch()}>
                重试
              </Button>
            }
          />
        ) : topNamedQueries.length === 0 ? (
          <EmptyState
            icon={<ListChecks className="h-6 w-6" aria-hidden="true" />}
            title="暂无命名查询"
            description="将临时查询 Promote 后，这里会显示最近使用的命名查询。"
            className="m-4"
            action={
              <Link to="/queries" className={cn(buttonVariants({ variant: "outline" }))}>
                查看查询列表
              </Link>
            }
          />
        ) : (
          <div className="divide-y">
            {topNamedQueries.map((query) => (
              <div
                key={query.id}
                className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{query.connection_name ?? `#${query.connection_id}`}</span>
                    <span>·</span>
                    <span>{formatNullableDateTime(query.last_executed_at)}</span>
                    <span>·</span>
                    <span>{formatExpiration(query.expires_at)}</span>
                  </div>
                  <div className="mt-2 truncate text-sm font-medium">{query.name}</div>
                  <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                    {previewSql(query.sql_text)}
                  </div>
                </div>
                <Link
                  to={`/query/${query.id}`}
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

function getHistoryOpenState(item: QueryHistoryRead): { initialSql: string } | undefined {
  return item.query_id === null ? { initialSql: item.sql_text } : undefined;
}

function getHistoryQueryState(
  item: QueryHistoryRead,
  queryStates: Map<number, QueryDetailState>,
): QueryDetailState | null | undefined {
  if (item.query_id === null) {
    return null;
  }

  return queryStates.get(item.query_id);
}

function HistoryOpenAction({
  item,
  queryState,
}: {
  item: QueryHistoryRead;
  queryState: QueryDetailState | null | undefined;
}) {
  if (item.query_id !== null) {
    const activeQueryState = queryState;
    if (activeQueryState === null || activeQueryState === undefined || activeQueryState.isLoading) {
      return (
        <Button variant="outline" size="sm" disabled className="shrink-0">
          加载中
        </Button>
      );
    }

    if (activeQueryState.isError || activeQueryState.data === undefined) {
      return (
        <Button variant="outline" size="sm" disabled className="shrink-0">
          不可用
        </Button>
      );
    }

    if (isExpired(activeQueryState.data.expires_at)) {
      return (
        <Button variant="outline" size="sm" disabled className="shrink-0">
          已过期
        </Button>
      );
    }
  }

  const to =
    item.query_id === null
      ? `/query?connection_id=${item.connection_id}`
      : `/query/${item.query_id}`;

  return (
    <Link
      to={to}
      state={getHistoryOpenState(item)}
      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "shrink-0")}
    >
      打开
    </Link>
  );
}

function formatNullableDateTime(value: string | null): string {
  if (value === null) {
    return "从未执行";
  }

  return formatDateTime(value);
}

function formatExpiration(value: string | null): string {
  if (value === null) {
    return "永不过期";
  }

  return isExpired(value) ? "已过期" : `${formatDateTime(value)} 过期`;
}

function isExpired(value: string | null): boolean {
  if (value === null) {
    return false;
  }

  const time = new Date(value).getTime();
  return !Number.isNaN(time) && Date.now() > time;
}
