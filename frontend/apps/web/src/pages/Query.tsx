import { useEffect, useRef, useState, type PointerEvent } from "react";
import { ArrowLeft, GripHorizontal, Loader2 } from "lucide-react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

import { useExecute } from "@/api/hooks/useExecute";
import { useQueryById } from "@/api/hooks/useQueries";
import type { Row } from "@/api/types";
import { buttonVariants } from "@/components/ui/button";
import { ErrorAlert } from "@/components/common/ErrorAlert";
import { QueryToolbar } from "@/features/query-editor/QueryToolbar";
import { clampEditorHeight, SqlEditor } from "@/features/query-editor/SqlEditor";
import {
  PromoteQueryDialog,
  type PromotableQuery,
} from "@/features/queries/PromoteQueryDialog";
import { RowDetailSheet } from "@/features/row-view/RowDetailSheet";
import { RowTable } from "@/features/row-view/RowTable";
import { cn } from "@/lib/utils";
import { initialTableConfig, useQueryStore } from "@/stores/queryStore";

type ActiveQuery = PromotableQuery & {
  is_named: boolean;
};

type DragState = {
  pointerId: number;
  startY: number;
  startHeight: number;
};

export function Query() {
  const { queryId: queryIdParam } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const routeQueryId = parsePositiveInt(queryIdParam);
  const connectionIdParam = searchParams.get("connection_id");
  const initialConnectionId = parsePositiveInt(connectionIdParam);
  const initialSql = getInitialSql(location.state);

  const connectionId = useQueryStore((state) => state.connectionId);
  const sql = useQueryStore((state) => state.sql);
  const queryId = useQueryStore((state) => state.queryId);
  const columns = useQueryStore((state) => state.columns);
  const rows = useQueryStore((state) => state.rows);
  const execution = useQueryStore((state) => state.execution);
  const isExecuting = useQueryStore((state) => state.isExecuting);
  const setConnectionId = useQueryStore((state) => state.setConnectionId);
  const setSql = useQueryStore((state) => state.setSql);
  const setResult = useQueryStore((state) => state.setResult);
  const reset = useQueryStore((state) => state.reset);

  const [activeQuery, setActiveQuery] = useState<ActiveQuery | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<PromotableQuery | null>(null);
  const [lastError, setLastError] = useState<unknown>(null);
  const [autoEditorHeight, setAutoEditorHeight] = useState(200);
  const [manualEditorHeight, setManualEditorHeight] = useState<number | null>(null);
  const [detailRow, setDetailRow] = useState<Row | null>(null);
  const [detailRowNumber, setDetailRowNumber] = useState<number | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const hydratedQueryIdRef = useRef<number | null>(null);

  const queryDetail = useQueryById(routeQueryId ?? 0);
  const execute = useExecute();

  useEffect(() => {
    if (routeQueryId !== null) {
      return;
    }

    reset();
    hydratedQueryIdRef.current = null;
    setActiveQuery(null);
    setLastError(null);
    setManualEditorHeight(null);
    setDetailRow(null);
    setDetailRowNumber(null);

    if (initialConnectionId !== null) {
      setConnectionId(initialConnectionId);
    }
    if (initialSql !== null) {
      setSql(initialSql);
    }
  }, [initialConnectionId, initialSql, reset, routeQueryId, setConnectionId, setSql]);

  useEffect(() => {
    if (
      routeQueryId === null ||
      queryDetail.data === undefined ||
      queryDetail.data.id !== routeQueryId ||
      hydratedQueryIdRef.current === queryDetail.data.id
    ) {
      return;
    }

    reset();
    hydratedQueryIdRef.current = queryDetail.data.id;
    setConnectionId(queryDetail.data.connection_id);
    setSql(queryDetail.data.sql_text);
    useQueryStore.setState({ queryId: queryDetail.data.id });
    setActiveQuery({
      id: queryDetail.data.id,
      name: queryDetail.data.name,
      description: queryDetail.data.description,
      expires_at: queryDetail.data.expires_at,
      is_named: queryDetail.data.is_named,
    });
    setLastError(null);
    setManualEditorHeight(null);
    setDetailRow(null);
    setDetailRowNumber(null);
  }, [queryDetail.data, reset, routeQueryId, setConnectionId, setSql]);

  async function handleRun() {
    if (connectionId === null || sql.trim().length === 0 || isExecuting) {
      return;
    }

    const executionConnectionId = connectionId;
    const executionSql = sql;
    clearCurrentQueryIdentity({ preserveViewConfig: true });
    useQueryStore.setState({ isExecuting: true });

    try {
      const result = await execute.mutateAsync({
        connection_id: executionConnectionId,
        sql: executionSql,
        save_as_temporary: true,
      });
      if (!executionStillMatches(executionConnectionId, executionSql)) {
        useQueryStore.setState({ isExecuting: false });
        return;
      }

      setResult(result);
      setDetailRow(null);
      setDetailRowNumber(null);
      setActiveQuery({
        id: result.query_id,
        name: null,
        description: null,
        expires_at: null,
        is_named: !result.is_temporary,
      });
    } catch (error) {
      if (!executionStillMatches(executionConnectionId, executionSql)) {
        useQueryStore.setState({ isExecuting: false });
        return;
      }

      useQueryStore.setState({ isExecuting: false });
      setLastError(error);
    }
  }

  function handleConnectionChange(id: number | null) {
    if (id === useQueryStore.getState().connectionId) {
      return;
    }

    setConnectionId(id);
    clearCurrentQueryIdentity();
  }

  function handleSqlChange(nextSql: string) {
    if (nextSql === useQueryStore.getState().sql) {
      return;
    }

    setSql(nextSql);
    clearCurrentQueryIdentity();
  }

  function clearCurrentQueryIdentity(options?: { preserveViewConfig?: boolean }) {
    setLastError(null);
    setDetailRow(null);
    setActiveQuery(null);
    setPromoteTarget(null);
    setDetailRowNumber(null);
    const nextState: Partial<ReturnType<typeof useQueryStore.getState>> = {
      queryId: null,
      columns: [],
      rows: [],
      execution: null,
      suggestedRenders: {},
      warnings: [],
    };

    if (options?.preserveViewConfig !== true) {
      nextState.fieldRenders = {};
      nextState.manualFieldRenderColumns = [];
      nextState.tableConfig = initialTableConfig;
    }

    useQueryStore.setState(nextState);
  }

  function executionStillMatches(executionConnectionId: number, executionSql: string): boolean {
    const currentState = useQueryStore.getState();
    return (
      currentState.connectionId === executionConnectionId && currentState.sql === executionSql
    );
  }

  function handleSaveAs() {
    if (activeQuery === null || activeQuery.is_named) {
      return;
    }

    setPromoteTarget(activeQuery);
  }

  function handleRowClick(row: Row, rowNumber: number) {
    setDetailRow(row);
    setDetailRowNumber(rowNumber);
  }

  function handleDividerPointerDown(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStateRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      startHeight: manualEditorHeight ?? autoEditorHeight,
    };
  }

  function handleDividerPointerMove(event: PointerEvent<HTMLDivElement>) {
    const dragState = dragStateRef.current;
    if (dragState === null || dragState.pointerId !== event.pointerId) {
      return;
    }

    setManualEditorHeight(clampEditorHeight(dragState.startHeight + event.clientY - dragState.startY));
  }

  function handleDividerPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragStateRef.current = null;
  }

  if (routeQueryId !== null && queryDetail.isLoading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        正在加载查询...
      </div>
    );
  }

  if (routeQueryId !== null && queryDetail.isError) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link to="/queries" className={cn(buttonVariants({ variant: "outline" }), "gap-2")}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          返回查询列表
        </Link>
        <ErrorAlert error={queryDetail.error} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {routeQueryId === null ? "新建查询" : `查询 #${routeQueryId}`}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            编写 SQL，选择连接后运行。打开已有查询时不会自动执行。
          </p>
        </div>
        <Link to="/queries" className={cn(buttonVariants({ variant: "outline" }), "gap-2")}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          查询列表
        </Link>
      </div>

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <QueryToolbar
          connectionId={connectionId}
          sql={sql}
          queryId={queryId}
          isNamed={activeQuery?.is_named ?? false}
          execution={execution}
          isExecuting={isExecuting}
          onConnectionChange={handleConnectionChange}
          onRun={() => void handleRun()}
          onSaveAs={handleSaveAs}
        />

        <div className="bg-background p-4">
          <SqlEditor
            value={sql}
            onChange={handleSqlChange}
            onRun={() => void handleRun()}
            height={manualEditorHeight ?? undefined}
            onHeightChange={setAutoEditorHeight}
          />
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="调整 SQL 编辑器高度"
            className="mt-2 flex h-4 cursor-row-resize items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
            onPointerDown={handleDividerPointerDown}
            onPointerMove={handleDividerPointerMove}
            onPointerUp={handleDividerPointerUp}
            onPointerCancel={handleDividerPointerUp}
            onDoubleClick={() => setManualEditorHeight(null)}
          >
            <GripHorizontal className="h-4 w-4" aria-hidden="true" />
          </div>
        </div>

        <div className="min-h-[260px] border-t bg-muted/20 p-4">
          <ResultPlaceholder
            error={lastError}
            isExecuting={isExecuting}
            execution={execution}
            columns={columns}
            rows={rows}
            returnedRows={rows.length}
            onRowClick={handleRowClick}
          />
        </div>
      </section>

      <RowDetailSheet
        open={detailRow !== null}
        row={detailRow}
        columns={columns}
        rowNumber={detailRowNumber}
        onOpenChange={(open) => {
          if (!open) {
            setDetailRow(null);
            setDetailRowNumber(null);
          }
        }}
      />

      <PromoteQueryDialog
        open={promoteTarget !== null}
        query={promoteTarget}
        onPromoted={(promotedQuery) => {
          useQueryStore.setState({ queryId: promotedQuery.id });
          setActiveQuery({
            id: promotedQuery.id,
            name: promotedQuery.name,
            description: promotedQuery.description,
            expires_at: promotedQuery.expires_at,
            is_named: promotedQuery.is_named,
          });
        }}
        onOpenChange={(open) => {
          if (!open) {
            setPromoteTarget(null);
          }
        }}
      />
    </div>
  );
}

type ResultPlaceholderProps = {
  error: unknown;
  isExecuting: boolean;
  execution: ReturnType<typeof useQueryStore.getState>["execution"];
  columns: ReturnType<typeof useQueryStore.getState>["columns"];
  rows: Row[];
  returnedRows: number;
  onRowClick: (row: Row, rowNumber: number) => void;
};

function ResultPlaceholder({
  error,
  isExecuting,
  execution,
  columns,
  rows,
  returnedRows,
  onRowClick,
}: ResultPlaceholderProps) {
  if (isExecuting) {
    return (
      <div className="flex h-full min-h-[220px] items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        正在执行 SQL...
      </div>
    );
  }

  if (error !== null) {
    return <ErrorAlert error={error} />;
  }

  if (execution !== null) {
    if (rows.length > 0) {
      return <RowTable columns={columns} rows={rows} onRowClick={onRowClick} />;
    }

    return (
      <div className="flex h-full min-h-[220px] items-center justify-center rounded-lg border border-dashed bg-background text-sm text-muted-foreground">
        已返回 {returnedRows} 行
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[220px] items-center justify-center rounded-lg border border-dashed bg-background text-sm text-muted-foreground">
      运行 SQL 看结果
    </div>
  );
}

function parsePositiveInt(value: string | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function getInitialSql(locationState: unknown): string | null {
  if (
    typeof locationState === "object" &&
    locationState !== null &&
    "initialSql" in locationState
  ) {
    const initialSql = locationState.initialSql;
    return typeof initialSql === "string" ? initialSql : null;
  }

  return null;
}
