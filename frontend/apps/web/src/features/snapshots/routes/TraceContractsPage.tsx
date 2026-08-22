import { Braces, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useTraceContracts } from "@/features/snapshots/api";
import { cn } from "@/lib/utils";

export function TraceContractsPage() {
  const contracts = useTraceContracts({ limit: 50 });
  const items = contracts.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Trace Contracts</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            版本化保存 SQL schema 到 canonical trajectory 的显式映射。
          </p>
        </div>
        <Link to="/trace-contracts/new" className={cn(buttonVariants(), "gap-2")}>
          <Plus className="h-4 w-4" aria-hidden="true" />新建 Contract
        </Link>
      </div>

      {contracts.isLoading ? (
        <LoadingState label="正在加载 TraceContract…" rows={5} />
      ) : contracts.isError ? (
        <ErrorState
          error={contracts.error}
          action={
            <Button variant="outline" size="sm" onClick={() => void contracts.refetch()}>
              重试
            </Button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Braces className="h-6 w-6" aria-hidden="true" />}
          title="还没有 TraceContract"
          description="先选择一条命名查询，通过三步向导完成字段映射与动态验证。"
          action={
            <Link to="/trace-contracts/new" className={buttonVariants({ variant: "outline" })}>
              创建第一个 Contract
            </Link>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-background">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Name / Version</th>
                <th className="px-4 py-3">Query</th>
                <th className="px-4 py-3">Layout</th>
                <th className="px-4 py-3">Definition hash</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Definition</th>
              </tr>
            </thead>
            <tbody>
              {items.map((contract) => (
                <tr key={contract.id} className="border-t align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium">{contract.name}</div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      v{contract.version} · {contract.id.slice(0, 8)}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {contract.named_query_name ?? `Query #${contract.named_query_id}`}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="secondary">{contract.definition.source_layout}</Badge>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {contract.definition_sha256.slice(0, 12)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(contract.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <details>
                      <summary className="cursor-pointer text-sm font-medium">查看</summary>
                      <pre className="mt-2 max-h-72 max-w-xl overflow-auto rounded-md bg-muted/50 p-3 text-xs">
                        {JSON.stringify(contract.definition, null, 2)}
                      </pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
