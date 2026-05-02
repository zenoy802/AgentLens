import { Database } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useConnections, useTestConnection } from "@/api/hooks/useConnections";
import type { ConnectionRead } from "@/api/hooks/useConnections";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConnectionFormDialog } from "@/features/connections/ConnectionFormDialog";
import { DeleteConnectionDialog } from "@/features/connections/DeleteConnectionDialog";
import { formatApiError } from "@/lib/formatApiError";

export function Connections() {
  const connections = useConnections();
  const testConnection = useTestConnection();

  const [formTarget, setFormTarget] = useState<ConnectionRead | null | undefined>(
    undefined,
  );
  const [deleteTarget, setDeleteTarget] = useState<ConnectionRead | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);

  async function handleTest(connection: ConnectionRead) {
    setTestingId(connection.id);
    try {
      const result = await testConnection.mutateAsync(connection.id);
      if (result.ok) {
        toast.success(
          `连接成功 — ${result.server_version ?? "unknown"} (${result.latency_ms}ms)`,
        );
      } else {
        toast.error(`CONN_TEST_FAILED: ${result.error ?? "连接失败"}`);
      }
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setTestingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">连接管理</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            管理 AgentLens 只读连接的数据源。
          </p>
        </div>
        <Button
          className="shrink-0"
          onClick={() => setFormTarget(null)}
        >
          新建连接
        </Button>
      </div>

      <ConnectionFormDialog
        open={formTarget !== undefined}
        connection={formTarget ?? null}
        onOpenChange={(open) => {
          if (!open) setFormTarget(undefined);
        }}
      />
      <DeleteConnectionDialog
        open={deleteTarget !== null}
        connection={deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      />

      <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
        {connections.isLoading ? (
          <LoadingState label="正在加载连接..." rows={5} className="rounded-none border-0" />
        ) : connections.isError ? (
          <ErrorState
            error={connections.error}
            className="m-4"
            action={
              <Button variant="outline" size="sm" onClick={() => void connections.refetch()}>
                重试
              </Button>
            }
          />
        ) : (connections.data?.items ?? []).length === 0 ? (
          <EmptyState
            icon={<Database className="h-6 w-6" aria-hidden="true" />}
            title="暂无连接"
            description="创建只读 MySQL 数据源连接后，就可以开始分析 Agent trajectory 数据。"
            className="m-4"
            action={
              <Button variant="outline" onClick={() => setFormTarget(null)}>
                新建你的第一个连接
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table className="min-w-[960px]">
              <TableHeader>
                <TableRow className="border-none">
                  <TableHead>ID</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>主机</TableHead>
                  <TableHead>数据库</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(connections.data?.items ?? []).map((connection) => (
                  <TableRow key={connection.id}>
                    <TableCell className="text-muted-foreground">
                      {connection.id}
                    </TableCell>
                    <TableCell className="font-medium">{connection.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {connection.db_type}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {connection.host ?? "localhost"}:{connection.port ?? 3306}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {connection.database}
                    </TableCell>
                    <TableCell>
                      {connection.last_test_ok === true ? (
                        <span
                          role="img"
                          aria-label="连接成功"
                          title={connection.last_tested_at ?? undefined}
                        >
                          ✅
                        </span>
                      ) : connection.last_test_ok === false ? (
                        <span
                          role="img"
                          aria-label="连接失败"
                          title={connection.last_tested_at ?? undefined}
                        >
                          ❌
                        </span>
                      ) : (
                        <span className="text-muted-foreground" aria-label="未测试">
                          —
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleTest(connection)}
                          disabled={testingId !== null}
                        >
                          {testingId === connection.id ? "测试中..." : "测试"}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setFormTarget(connection)}
                        >
                          编辑
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setDeleteTarget(connection)}
                        >
                          删除
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
