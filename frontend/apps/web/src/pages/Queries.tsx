import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Save, Search, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { useConnections } from "@/api/hooks/useConnections";
import type { NamedQueryRead, QueryListParams } from "@/api/hooks/useQueries";
import { useQueries } from "@/api/hooks/useQueries";
import { Button, buttonVariants } from "@/components/ui/button";
import { DeleteQueryDialog } from "@/features/queries/DeleteQueryDialog";
import { PromoteQueryDialog } from "@/features/queries/PromoteQueryDialog";
import { cn } from "@/lib/utils";

export function Queries() {
  const [connectionFilter, setConnectionFilter] = useState("all");
  const [namedOnly, setNamedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<NamedQueryRead | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<NamedQueryRead | null>(null);

  const params = useMemo<QueryListParams>(
    () => ({
      connection_id: connectionFilter === "all" ? undefined : Number(connectionFilter),
      is_named: namedOnly ? true : undefined,
      search: search.trim() || undefined,
      page,
      page_size: 50,
    }),
    [connectionFilter, namedOnly, page, search],
  );

  useEffect(() => {
    setPage(1);
  }, [connectionFilter, namedOnly, search]);

  const queries = useQueries(params);
  const connections = useConnections();
  const connectionNames = useMemo(() => {
    return new Map(
      (connections.data?.items ?? []).map((connection) => [connection.id, connection.name]),
    );
  }, [connections.data?.items]);

  const items = queries.data?.items ?? [];
  const pagination = queries.data?.pagination;
  const pageIsOutOfRange =
    pagination !== undefined && pagination.total > 0 && page > pagination.total_pages;

  useEffect(() => {
    if (pageIsOutOfRange) {
      setPage(pagination.total_pages);
    }
  }, [pageIsOutOfRange, pagination?.total_pages]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Queries</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Saved and temporary SQL queries across your connected databases.
          </p>
        </div>
        <Link to="/query" className={cn(buttonVariants(), "shrink-0")}>
          新建查询
        </Link>
      </div>

      <div className="grid gap-3 rounded-lg border bg-card p-4 md:grid-cols-[220px_140px_minmax(240px,1fr)]">
        <label className="block text-sm font-medium">
          连接
          <select
            className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
            value={connectionFilter}
            onChange={(event) => setConnectionFilter(event.target.value)}
          >
            <option value="all">全部连接</option>
            {(connections.data?.items ?? []).map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex h-full items-end gap-2 pb-2 text-sm font-medium">
          <input
            className="h-4 w-4 rounded border-input"
            type="checkbox"
            checked={namedOnly}
            onChange={(event) => setNamedOnly(event.target.checked)}
          />
          仅命名
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
          <div className="p-6 text-sm text-muted-foreground">正在加载查询...</div>
        ) : queries.isError ? (
          <div className="flex items-center justify-between gap-3 p-6 text-sm text-destructive">
            <span>{queries.error instanceof Error ? queries.error.message : "查询加载失败"}</span>
            <Button variant="outline" size="sm" onClick={() => void queries.refetch()}>
              重试
            </Button>
          </div>
        ) : pageIsOutOfRange ? (
          <div className="p-6 text-sm text-muted-foreground">正在调整页码...</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 px-4 py-14 text-center">
            <div className="text-base font-medium">暂无查询</div>
            <div className="max-w-sm text-sm text-muted-foreground">
              执行 SQL 后会生成临时查询，也可以新建命名查询。
            </div>
            <Link to="/query" className={cn(buttonVariants({ variant: "outline" }))}>
              新建查询
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[260px]" />
                <col className="w-[170px]" />
                <col className="w-[300px]" />
                <col className="w-[100px]" />
                <col className="w-[150px]" />
                <col className="w-[150px]" />
                <col className="w-[170px]" />
              </colgroup>
              <thead className="bg-muted/60 text-left text-xs font-medium uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Connection</th>
                  <th className="px-4 py-3">SQL</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Last Executed</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((query) => (
                  <tr key={query.id} className="border-t">
                    <td className="px-4 py-3 align-top">
                      {query.name === null ? (
                        <span className="text-muted-foreground">（临时）</span>
                      ) : (
                        <span className="block break-all font-medium leading-5">
                          {query.name}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top text-muted-foreground">
                      <span className="block truncate" title={connectionNames.get(query.connection_id)}>
                        {connectionNames.get(query.connection_id) ?? `#${query.connection_id}`}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top font-mono text-xs">
                      <span className="block truncate" title={query.sql_text}>
                        {previewSql(query.sql_text)}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <span
                        className={cn(
                          "inline-flex rounded-md border px-2 py-1 text-xs font-medium",
                          query.is_named
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border-slate-200 bg-slate-50 text-slate-600",
                        )}
                      >
                        {query.is_named ? "Named" : "Temporary"}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top text-muted-foreground">
                      {formatDateTime(query.last_executed_at)}
                    </td>
                    <td className="px-4 py-3 align-top text-muted-foreground">
                      {query.expires_at === null ? "永不过期" : formatDateTime(query.expires_at)}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/query/${query.id}`}
                          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1")}
                        >
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                          打开
                        </Link>
                        {!query.is_named ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1"
                            onClick={() => setPromoteTarget(query)}
                          >
                            <Save className="h-3.5 w-3.5" aria-hidden="true" />
                            保存
                          </Button>
                        ) : null}
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1 text-destructive hover:text-destructive"
                          onClick={() => setDeleteTarget(query)}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          删除
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {pagination !== undefined ? (
              <div className="flex flex-col gap-3 border-t px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <div>
                  第 {pagination.page} / {pagination.total_pages} 页，共 {pagination.total} 条
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
                    disabled={
                      pagination.page >= pagination.total_pages || queries.isFetching
                    }
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
        open={promoteTarget !== null}
        query={promoteTarget}
        onOpenChange={(open) => {
          if (!open) {
            setPromoteTarget(null);
          }
        }}
      />
    </div>
  );
}

function previewSql(sql: string): string {
  const compact = sql.replace(/\s+/g, " ").trim();
  return compact.length > 60 ? `${compact.slice(0, 60)}...` : compact;
}

function formatDateTime(value: string | null): string {
  if (value === null) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
