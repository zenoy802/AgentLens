import type { ReactNode } from "react";
import { Download, Loader2, Play, Save } from "lucide-react";

import type { ExecutionInfo } from "@/stores/queryStore";
import { Button } from "@/components/ui/button";
import { ConnectionSelect } from "@/features/query-editor/ConnectionSelect";

type QueryToolbarProps = {
  connectionId: number | null;
  sql: string;
  queryId: number | null;
  isNamed: boolean;
  execution: ExecutionInfo | null;
  isExecuting: boolean;
  runDisabled?: boolean;
  resultTabs?: ReactNode;
  onConnectionChange: (id: number | null) => void;
  onRun: () => void;
  onSaveAs: () => void;
  onExport: () => void;
};

export function QueryToolbar({
  connectionId,
  sql,
  queryId,
  isNamed,
  execution,
  isExecuting,
  runDisabled: runBlocked = false,
  resultTabs,
  onConnectionChange,
  onRun,
  onSaveAs,
  onExport,
}: QueryToolbarProps) {
  const runDisabled =
    connectionId === null || sql.trim().length === 0 || isExecuting || runBlocked;
  const saveDisabled = queryId === null || isNamed || isExecuting;
  const exportDisabled = queryId === null || isExecuting;

  return (
    <div className="flex flex-col gap-3 border-b bg-card px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <ConnectionSelect value={connectionId} onChange={onConnectionChange} disabled={isExecuting} />
        <Button className="gap-2" onClick={onRun} disabled={runDisabled}>
          {isExecuting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
          运行
        </Button>
        <Button variant="outline" className="gap-2" onClick={onSaveAs} disabled={saveDisabled}>
          <Save className="h-4 w-4" aria-hidden="true" />
          另存为
        </Button>
        <Button variant="outline" className="gap-2" onClick={onExport} disabled={exportDisabled}>
          <Download className="h-4 w-4" aria-hidden="true" />
          导出
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
        {execution !== null ? (
          <div className="text-sm text-muted-foreground">
            {execution.row_count} 行 · {Math.round(execution.duration_ms)}ms
          </div>
        ) : null}
        {resultTabs}
      </div>
    </div>
  );
}
