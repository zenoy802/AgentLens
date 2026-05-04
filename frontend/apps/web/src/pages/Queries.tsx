import { useEffect, useMemo, useState } from "react";
import {
  differenceInCalendarDays,
  formatDistanceToNow,
  isValid,
  parseISO,
} from "date-fns";
import { zhCN } from "date-fns/locale";
import { FileSearch, Plus, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { useConnections } from "@/api/hooks/useConnections";
import type { NamedQueryRead, QueryListParams } from "@/api/hooks/useQueries";
import { useQueries } from "@/api/hooks/useQueries";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DeleteQueryDialog } from "@/features/queries/DeleteQueryDialog";
import { ExportDialog } from "@/features/export/ExportDialog";
import { PromoteQueryDialog } from "@/features/queries/PromoteQueryDialog";
import { QueryActionsMenu } from "@/features/queries/QueryActionsMenu";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

export function Queries() {
  const [connectionFilter, setConnectionFilter] = useState("all");
  const [namedOnly, setNamedOnly] = useState(false);
  const [includeExpired, setIncludeExpired] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<NamedQueryRead | null>(null);
  const [editTarget, setEditTarget] = useState<NamedQueryRead | null>(null);
  const [exportTarget, setExportTarget] = useState<NamedQueryRead | null>(null);

  const params = useMemo<QueryListParams>(
    () => ({
      connection_id: connectionFilter === "all" ? undefined : Number(connectionFilter),
      is_named: namedOnly ? true : undefined,
      include_expired: includeExpired,
      search: search.trim() || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    [connectionFilter, includeExpired, namedOnly, page, search],
  );

  useEffect(() => {
    setPage(1);
  }, [connectionFilter, includeExpired, namedOnly, search]);

  const queries = useQueries(params);
  const connections = useConnections();

  const items = queries.data?.items ?? [];
  const pagination = queries.data?.pagination;
  const pageIsOutOfRange =
    pagination !== undefined && pagination.total > 0 && page > pagination.total_pages;

  useEffect(() => {
    if (pageIsOutOfRange && pagination !== undefined) {
      setPage(pagination.total_pages);
    }
  }, [pageIsOutOfRange, pagination]);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">查询管理</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              管理命名查询和临时查询，查看打标与分析统计。
            </p>
          </div>
          <Link to="/query" className={cn(buttonVariants(), "shrink-0 gap-2")}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新建查询
          </Link>
        </div>

        <div className="grid gap-3 rounded-lg border bg-card p-4 md:grid-cols-[220px_110px_150px_minmax(240px,1fr)] md:items-end">
          <label className="block text-sm font-medium">
            连接
            <Select value={connectionFilter} onValueChange={setConnectionFilter}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="全部连接" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部连接</SelectItem>
                {(connections.data?.items ?? []).map((connection) => (
                  <SelectItem key={connection.id} value={String(connection.id)}>
                    {connection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="flex h-9 items-center gap-2 text-sm font-medium">
            <input
              className="h-4 w-4 rounded border-input"
              type="checkbox"
              checked={namedOnly}
              onChange={(event) => setNamedOnly(event.target.checked)}
            />
            仅命名
          </label>

          <label className="flex h-9 items-center gap-2 text-sm font-medium">
            <input
              className="h-4 w-4 rounded border-input"
              type="checkbox"
              checked={includeExpired}
              onChange={(event) => setIncludeExpired(event.target.checked)}
            />
            包含已过期
          </label>

          <label className="block text-sm font-medium">
            搜索
            <div className="relative mt-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                className="h-9 w-full rounded-md border bg-background pl-9 pr-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="名称、描述或 SQL"
              />
            </div>
          </label>
        </div>

        <div className="overflow-hidden rounded-lg border">
          {queries.isLoading ? (
            <LoadingState label="正在加载查询..." rows={6} className="rounded-none border-0" />
          ) : queries.isError ? (
            <ErrorState
              error={queries.error}
              className="m-4"
              action={
                <Button variant="outline" size="sm" onClick={() => void queries.refetch()}>
                  重试
                </Button>
              }
            />
          ) : pageIsOutOfRange ? (
            <LoadingState label="正在调整页码..." rows={3} className="rounded-none border-0" />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<FileSearch className="h-6 w-6" aria-hidden="true" />}
              title="暂无查询"
              description="执行 SQL 后会生成临时查询，也可以保存为命名查询。"
              className="m-4"
              action={
                <Link to="/query" className={cn(buttonVariants({ variant: "outline" }))}>
                  去写第一条 SQL
                </Link>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1320px] table-fixed border-collapse text-sm">
                <colgroup>
                  <col className="w-[220px]" />
                  <col className="w-[170px]" />
                  <col className="w-[310px]" />
                  <col className="w-[100px]" />
                  <col className="w-[150px]" />
                  <col className="w-[150px]" />
                  <col className="w-[130px]" />
                  <col className="w-[90px]" />
                </colgroup>
                <thead className="bg-muted/60 text-left text-xs font-medium uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Connection</th>
                    <th className="px-4 py-3">SQL</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Last Executed</th>
                    <th className="px-4 py-3">Expires</th>
                    <th className="px-4 py-3">Stats</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((query) => {
                    const expiration = getExpirationMeta(query.expires_at);
                    const connectionName =
                      query.connection_name ?? `#${query.connection_id}`;
                    return (
                      <tr key={query.id} className="border-t">
                        <td className="px-4 py-3 align-top">
                          {query.name === null ? (
                            <span
                              className="text-muted-foreground italic"
                              title="临时查询"
                            >
                              （临时）
                            </span>
                          ) : (
                            <span className="block break-all font-medium leading-5">
                              {query.name}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top text-muted-foreground">
                          <span className="block truncate" title={connectionName}>
                            {connectionName}
                          </span>
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs">
                          <SqlPreview sql={query.sql_text} />
                        </td>
                        <td className="px-4 py-3 align-top">
                          <Badge variant={query.is_named ? "secondary" : "muted"}>
                            {query.is_named ? "命名" : "临时"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 align-top text-muted-foreground">
                          {formatRelativeDate(query.last_executed_at)}
                        </td>
                        <td className={cn("px-4 py-3 align-top", expiration.className)}>
                          {expiration.label}
                        </td>
                        <td className="px-4 py-3 align-top text-muted-foreground">
                          <span className="whitespace-nowrap">
                            {query.label_record_count ?? 0} 打标
                          </span>
                          <span className="mx-1">/</span>
                          <span className="whitespace-nowrap">
                            {query.llm_analysis_count ?? 0} 分析
                          </span>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex justify-end">
                            <QueryActionsMenu
                              query={query}
                              onEdit={setEditTarget}
                              onPromote={setEditTarget}
                              onExport={setExportTarget}
                              onDelete={setDeleteTarget}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {pagination !== undefined ? (
                <div className="flex flex-col gap-3 border-t px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    第 {pagination.page} / {pagination.total_pages} 页，共 {pagination.total} 条
                    {queries.isFetching ? "，刷新中..." : ""}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pagination.page <= 1 || queries.isFetching}
                      onClick={() => setPage((current) => Math.max(current - 1, 1))}
                    >
                      上一页
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pagination.page >= pagination.total_pages || queries.isFetching}
                      onClick={() =>
                        setPage((current) => Math.min(current + 1, pagination.total_pages))
                      }
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>

        <DeleteQueryDialog
          open={deleteTarget !== null}
          query={deleteTarget}
          onOpenChange={(open) => {
            if (!open) {
              setDeleteTarget(null);
            }
          }}
        />
        <PromoteQueryDialog
          open={editTarget !== null}
          query={editTarget}
          onOpenChange={(open) => {
            if (!open) {
              setEditTarget(null);
            }
          }}
        />
        <ExportDialog
          open={exportTarget !== null}
          queryId={exportTarget?.id ?? null}
          onOpenChange={(open) => {
            if (!open) {
              setExportTarget(null);
            }
          }}
        />
      </div>
    </TooltipProvider>
  );
}

function SqlPreview({ sql }: { sql: string }) {
  const preview = previewSql(sql);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block truncate">{preview}</span>
      </TooltipTrigger>
      <TooltipContent className="font-mono leading-5">
        <span className="whitespace-pre-wrap break-words">{sql}</span>
      </TooltipContent>
    </Tooltip>
  );
}

function previewSql(sql: string): string {
  const compact = sql.replace(/\s+/g, " ").trim();
  return compact.length > 60 ? `${compact.slice(0, 60)}...` : compact;
}

function formatRelativeDate(value: string | null): string {
  const date = parseDate(value);
  if (date === null) {
    return "-";
  }

  return formatDistanceToNow(date, { addSuffix: true, locale: zhCN });
}

function getExpirationMeta(value: string | null): { label: string; className: string } {
  const date = parseDate(value);
  if (date === null) {
    return { label: "∞ 永不过期", className: "text-muted-foreground" };
  }

  const now = new Date();
  if (now.getTime() > date.getTime()) {
    return { label: "已过期", className: "font-medium text-destructive" };
  }

  const days = differenceInCalendarDays(date, now);
  if (days < 7) {
    return {
      label: days <= 0 ? "今天过期" : `${days} 天后过期`,
      className: "font-medium text-amber-700",
    };
  }

  return {
    label: formatDistanceToNow(date, { addSuffix: true, locale: zhCN }),
    className: "text-muted-foreground",
  };
}

function parseDate(value: string | null): Date | null {
  if (value === null) {
    return null;
  }

  const date = parseISO(value);
  if (!isValid(date)) {
    return null;
  }

  return date;
}
