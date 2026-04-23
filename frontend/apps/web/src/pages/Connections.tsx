import { Link } from "react-router-dom";

import { useConnections } from "@/api/hooks/useConnections";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Connections() {
  const connections = useConnections();

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">连接管理</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            管理 AgentLens 只读连接的数据源。完整创建/编辑表单会在后续任务实现。
          </p>
        </div>
        <Link to="/query" className={cn(buttonVariants({ variant: "outline" }))}>
          去新建查询
        </Link>
      </div>

      <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
        {connections.isLoading ? (
          <div className="p-6 text-sm text-muted-foreground">正在加载连接...</div>
        ) : connections.isError ? (
          <div className="flex items-center justify-between gap-3 p-6 text-sm text-destructive">
            <span>
              {connections.error instanceof Error ? connections.error.message : "连接加载失败"}
            </span>
            <Button variant="outline" size="sm" onClick={() => void connections.refetch()}>
              重试
            </Button>
          </div>
        ) : (connections.data?.items ?? []).length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">暂无连接。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <thead className="bg-muted/60 text-left text-xs font-medium uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Host</th>
                  <th className="px-4 py-3">Database</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {(connections.data?.items ?? []).map((connection) => (
                  <tr key={connection.id} className="border-t">
                    <td className="px-4 py-3 font-medium">{connection.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{connection.db_type}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {connection.host ?? "localhost"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{connection.database}</td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/query?connection_id=${connection.id}`}
                        className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                      >
                        用此连接查询
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
