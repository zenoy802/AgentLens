import { useEffect, useRef, useState, type PointerEvent } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, DatabaseZap, GripHorizontal } from "lucide-react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useExecute, useExecuteQuery } from "@/api/hooks/useExecute";
import { useQueryById } from "@/api/hooks/useQueries";
import { useTrajectories } from "@/api/hooks/useTrajectories";
import { useSaveViewConfig, useViewConfig } from "@/api/hooks/useViewConfig";
import type { Row, Trajectory, Warning } from "@/api/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { QueryToolbar } from "@/features/query-editor/QueryToolbar";
import {
  clampEditorHeight,
  MIN_EDITOR_HEIGHT,
  SqlEditor,
} from "@/features/query-editor/SqlEditor";
import { ViewConfigBar } from "@/features/query-editor/ViewConfigBar";
import {
  PromoteQueryDialog,
  type PromotableQuery,
} from "@/features/queries/PromoteQueryDialog";
import { RowDetailSheet } from "@/features/row-view/RowDetailSheet";
import { RowTable } from "@/features/row-view/RowTable";
import { SingleTrajectoryView } from "@/features/trajectory-view/SingleTrajectoryView";
import { useBeforeUnloadGuard } from "@/hooks/useBeforeUnloadGuard";
import { cn } from "@/lib/utils";
import {
  getViewConfigPayloadFromState,
  initialTableConfig,
  useQueryStore,
  viewConfigIsEmpty,
  viewConfigPayloadMatchesState,
} from "@/stores/queryStore";

type ActiveQuery = PromotableQuery & {
  is_named: boolean;
};

type ResultView = "row" | "trajectory";

type DragState = {
  pointerId: number;
  startY: number;
  startHeight: number;
};

type ExecutionGuard = {
  connectionId: number;
  sql: string;
  routeQueryId: number | null;
  queryIdAfterClear: number | null;
};

const SQL_EDITOR_COLLAPSED_KEY = "agentlens.query.sqlEditorCollapsed";
const QUERY_TEMPLATE_SQL = `-- 从这里开始：按 session_id 和时间顺序查询一条或多条 trajectory
-- SELECT session_id, role, content, created_at
-- FROM agent_messages
-- ORDER BY session_id, created_at;
`;

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
  const trajectoryConfig = useQueryStore((state) => state.trajectoryConfig);
  const isExecuting = useQueryStore((state) => state.isExecuting);
  const isDirty = useQueryStore((state) => state.isDirty);
  const setConnectionId = useQueryStore((state) => state.setConnectionId);
  const setSql = useQueryStore((state) => state.setSql);
  const setResult = useQueryStore((state) => state.setResult);
  const applyViewConfig = useQueryStore((state) => state.applyViewConfig);
  const mergeSuggestedRenders = useQueryStore((state) => state.mergeSuggestedRenders);
  const reset = useQueryStore((state) => state.reset);

  const [activeQuery, setActiveQuery] = useState<ActiveQuery | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<PromotableQuery | null>(null);
  const [lastError, setLastError] = useState<unknown>(null);
  const [activeResultView, setActiveResultView] = useState<ResultView>("row");
  const [editorCollapsed, setEditorCollapsed] = useState(readEditorCollapsedPreference);
  const [autoEditorHeight, setAutoEditorHeight] = useState(MIN_EDITOR_HEIGHT);
  const [manualEditorHeight, setManualEditorHeight] = useState<number | null>(null);
  const [detailRow, setDetailRow] = useState<Row | null>(null);
  const [detailRowNumber, setDetailRowNumber] = useState<number | null>(null);
  const [trajectoryLoadedKey, setTrajectoryLoadedKey] = useState<string | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const hydratedQueryIdRef = useRef<number | null>(null);
  const appliedForQueryIdRef = useRef<number | null>(null);
  const trajectoryRequestedKeyRef = useRef<string | null>(null);
  const previousRouteQueryIdRef = useRef<number | null | undefined>(undefined);
  const routeQueryIdRef = useRef<number | null>(routeQueryId);
  routeQueryIdRef.current = routeQueryId;

  const queryDetail = useQueryById(routeQueryId ?? 0);
  const {
    data: viewConfig,
    isLoading: viewConfigLoading,
    isSuccess: viewConfigLoaded,
  } = useViewConfig(routeQueryId);
  const execute = useExecute();
  const executeQuery = useExecuteQuery();
  const saveViewConfig = useSaveViewConfig();
  const aggregateTrajectories = useTrajectories(queryId ?? 0);
  const runBlockedByViewConfigLoad = routeQueryId !== null && viewConfigLoading;
  const trajectoryConfigComplete = isTrajectoryConfigComplete(trajectoryConfig);
  const trajectoryTabDisabled = !trajectoryConfigComplete || rows.length === 0 || queryId === null;
  const trajectoryRequestKey =
    queryId !== null && trajectoryConfig !== null
      ? getTrajectoryRequestKey(
          queryId,
          execution?.executed_at ?? "no-execution",
          trajectoryConfig,
        )
      : null;
  const trajectoryDataIsCurrent =
    trajectoryRequestKey !== null && trajectoryLoadedKey === trajectoryRequestKey;
  const trajectoryRequestIsCurrent =
    trajectoryRequestKey !== null &&
    trajectoryRequestedKeyRef.current === trajectoryRequestKey;

  useBeforeUnloadGuard(isDirty);

  useEffect(() => {
    window.localStorage.setItem(SQL_EDITOR_COLLAPSED_KEY, String(editorCollapsed));
  }, [editorCollapsed]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented) {
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void handleRun();
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void handleSaveViewConfig();
        return;
      }

      if (event.key === "Escape") {
        setPromoteTarget(null);
        setDetailRow(null);
        setDetailRowNumber(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  useEffect(() => {
    if (activeResultView !== "trajectory") {
      trajectoryRequestedKeyRef.current = null;
    }
  }, [activeResultView]);

  useEffect(() => {
    if (activeResultView === "trajectory" && trajectoryTabDisabled) {
      setActiveResultView("row");
    }
  }, [activeResultView, trajectoryTabDisabled]);

  useEffect(() => {
    if (
      activeResultView !== "trajectory" ||
      queryId === null ||
      trajectoryConfig === null ||
      !trajectoryConfigComplete ||
      rows.length === 0
    ) {
      return;
    }

    const requestKey = getTrajectoryRequestKey(
      queryId,
      execution?.executed_at ?? "no-execution",
      trajectoryConfig,
    );
    if (trajectoryLoadedKey === requestKey || trajectoryRequestedKeyRef.current === requestKey) {
      return;
    }

    trajectoryRequestedKeyRef.current = requestKey;
    aggregateTrajectories.mutate(
      {
        useSavedConfig: false,
        config: trajectoryConfig,
      },
      {
        onSuccess: () => setTrajectoryLoadedKey(requestKey),
      },
    );
  }, [
    activeResultView,
    aggregateTrajectories,
    execution?.executed_at,
    queryId,
    rows.length,
    trajectoryConfig,
    trajectoryConfigComplete,
    trajectoryLoadedKey,
  ]);

  useEffect(() => {
    const previousRouteQueryId = previousRouteQueryIdRef.current;
    previousRouteQueryIdRef.current = routeQueryId;

    if (previousRouteQueryId !== undefined && previousRouteQueryId !== routeQueryId) {
      useQueryStore.getState().reset();
    }
  }, [routeQueryId]);

  useEffect(() => {
    appliedForQueryIdRef.current = null;
  }, [routeQueryId]);

  useEffect(() => {
    if (
      routeQueryId === null ||
      !viewConfigLoaded ||
      viewConfig === undefined ||
      queryId !== routeQueryId ||
      appliedForQueryIdRef.current === routeQueryId
    ) {
      return;
    }

    applyViewConfig(viewConfig);
    appliedForQueryIdRef.current = routeQueryId;
  }, [applyViewConfig, queryId, routeQueryId, viewConfig, viewConfigLoaded]);

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
    if (
      connectionId === null ||
      sql.trim().length === 0 ||
      isExecuting ||
      runBlockedByViewConfigLoad
    ) {
      return;
    }

    const executionConnectionId = connectionId;
    const executionSql = sql;
    const executeSavedQuery = shouldExecuteSavedQuery();
    const wasDirtyBeforeRun = useQueryStore.getState().isDirty;
    const persistedViewConfigUnknown = executeSavedQuery && !viewConfigLoaded;
    const persistedViewConfigWasEmpty = executeSavedQuery
      ? viewConfigLoaded && viewConfig !== undefined && viewConfigIsEmpty(viewConfig)
      : true;
    const executionGuard: ExecutionGuard = {
      connectionId: executionConnectionId,
      sql: executionSql,
      routeQueryId,
      queryIdAfterClear: executeSavedQuery ? routeQueryId : null,
    };

    clearCurrentQueryIdentity({
      preserveQueryIdentity: executeSavedQuery,
      preserveViewConfig: true,
    });
    useQueryStore.setState({ isExecuting: true });

    try {
      const result = executeSavedQuery
        ? await executeQuery.mutateAsync({ queryId: routeQueryId! })
        : await execute.mutateAsync({
            connection_id: executionConnectionId,
            sql: executionSql,
            save_as_temporary: true,
          });
      if (!executionStillMatches(executionGuard)) {
        useQueryStore.setState({ isExecuting: false });
        return;
      }

      setResult(result);
      mergeSuggestedRenders(result.suggested_field_renders);
      if (
        !wasDirtyBeforeRun &&
        persistedViewConfigUnknown &&
        Object.keys(result.suggested_field_renders).length > 0
      ) {
        useQueryStore.getState().markDirty();
      }
      setDetailRow(null);
      setDetailRowNumber(null);
      if (executeSavedQuery && activeQuery !== null) {
        setActiveQuery({
          ...activeQuery,
          is_named: !result.is_temporary,
        });
      } else {
        setActiveQuery({
          id: result.query_id,
          name: null,
          description: null,
          expires_at: null,
          is_named: !result.is_temporary,
        });
      }

      if (
        !wasDirtyBeforeRun &&
        persistedViewConfigWasEmpty &&
        Object.keys(result.suggested_field_renders).length > 0 &&
        result.query_id > 0
      ) {
        const payload = getViewConfigPayloadFromState(useQueryStore.getState());
        try {
          const saved = await saveViewConfig.mutateAsync({
            queryId: result.query_id,
            payload,
          });
          if (
            executionStillMatchesAfterResult(executionGuard, result.query_id) &&
            viewConfigPayloadMatchesState(payload, useQueryStore.getState())
          ) {
            useQueryStore.getState().applyViewConfig(saved);
          }
        } catch {
          if (
            executionStillMatchesAfterResult(executionGuard, result.query_id) &&
            viewConfigPayloadMatchesState(payload, useQueryStore.getState())
          ) {
            useQueryStore.getState().markDirty();
          }
        }
      }
    } catch (error) {
      if (!executionStillMatches(executionGuard)) {
        useQueryStore.setState({ isExecuting: false });
        return;
      }

      useQueryStore.setState({ isExecuting: false });
      setLastError(error);
    }
  }

  async function handleSaveViewConfig() {
    if (queryId === null || !isDirty || saveViewConfig.isPending) {
      return;
    }

    const payload = getViewConfigPayloadFromState(useQueryStore.getState());
    try {
      const saved = await saveViewConfig.mutateAsync({
        queryId,
        payload,
      });
      const currentState = useQueryStore.getState();
      if (currentState.queryId === queryId && viewConfigPayloadMatchesState(payload, currentState)) {
        applyViewConfig(saved);
      }
      toast.success("视图已保存");
    } catch {
      // useSaveViewConfig reports API errors with the shared toast formatter.
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

  function shouldExecuteSavedQuery(): boolean {
    return (
      routeQueryId !== null &&
      queryId === routeQueryId &&
      queryDetail.data?.id === routeQueryId &&
      sql === queryDetail.data.sql_text
    );
  }

  function clearCurrentQueryIdentity(options?: {
    preserveQueryIdentity?: boolean;
    preserveViewConfig?: boolean;
  }) {
    setLastError(null);
    setActiveResultView("row");
    trajectoryRequestedKeyRef.current = null;
    setTrajectoryLoadedKey(null);
    setDetailRow(null);
    setDetailRowNumber(null);
    const nextState: Partial<ReturnType<typeof useQueryStore.getState>> = {
      columns: [],
      rows: [],
      execution: null,
      suggestedRenders: {},
      warnings: [],
    };

    if (options?.preserveQueryIdentity !== true) {
      nextState.queryId = null;
      setActiveQuery(null);
      setPromoteTarget(null);
    }

    if (options?.preserveViewConfig !== true) {
      nextState.fieldRenders = {};
      nextState.manualFieldRenderColumns = [];
      nextState.tableConfig = initialTableConfig;
      nextState.trajectoryConfig = null;
      nextState.rowIdentityColumn = null;
      nextState.isDirty = false;
    }

    useQueryStore.setState(nextState);
  }

  function executionStillMatches(guard: ExecutionGuard): boolean {
    const currentState = useQueryStore.getState();
    return (
      routeQueryIdRef.current === guard.routeQueryId &&
      currentState.connectionId === guard.connectionId &&
      currentState.sql === guard.sql &&
      currentState.queryId === guard.queryIdAfterClear
    );
  }

  function executionStillMatchesAfterResult(
    guard: ExecutionGuard,
    resultQueryId: number,
  ): boolean {
    const currentState = useQueryStore.getState();
    return (
      routeQueryIdRef.current === guard.routeQueryId &&
      currentState.connectionId === guard.connectionId &&
      currentState.sql === guard.sql &&
      currentState.queryId === resultQueryId
    );
  }

  function handleSaveAs() {
    if (activeQuery === null || activeQuery.is_named) {
      return;
    }

    setPromoteTarget(activeQuery);
  }

  function handleUseSqlTemplate() {
    const currentSql = useQueryStore.getState().sql;
    const nextSql =
      currentSql.trim().length === 0 ? QUERY_TEMPLATE_SQL : `${currentSql}\n${QUERY_TEMPLATE_SQL}`;
    setSql(nextSql);
    clearCurrentQueryIdentity();
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
    return <LoadingState label="正在加载查询..." rows={5} />;
  }

  if (routeQueryId !== null && queryDetail.isError) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link to="/queries" className={cn(buttonVariants({ variant: "outline" }), "gap-2")}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          返回查询列表
        </Link>
        <ErrorState error={queryDetail.error} />
      </div>
    );
  }

  const displayedQueryId = routeQueryId ?? activeQuery?.id ?? null;
  const pageTitle = getQueryPageTitle(displayedQueryId, queryDetail.data?.name ?? activeQuery?.name);

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div className="min-w-0">
          <h1 className="max-w-4xl break-words text-2xl font-semibold tracking-tight">
            {pageTitle}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {displayedQueryId === null
              ? "编写 SQL，选择连接后运行。打开已有查询时不会自动执行。"
              : `查询 #${displayedQueryId}。打开已有查询时不会自动执行。`}
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
          runDisabled={runBlockedByViewConfigLoad}
          onConnectionChange={handleConnectionChange}
          onRun={() => void handleRun()}
          onSaveAs={handleSaveAs}
          resultTabs={
            <ResultViewTabs
              activeView={activeResultView}
              trajectoryDisabled={trajectoryTabDisabled}
              trajectoryDisabledReason={getTrajectoryDisabledReason({
                configComplete: trajectoryConfigComplete,
                hasRows: rows.length > 0,
                hasQueryId: queryId !== null,
              })}
              onChange={setActiveResultView}
            />
          }
        />

        <div className="bg-background p-4">
          <div className="overflow-hidden rounded-lg border bg-card">
            <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
              <div className="text-sm font-medium">SQL Editor</div>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={() => setEditorCollapsed((current) => !current)}
              >
                {editorCollapsed ? (
                  <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {editorCollapsed ? "Expand" : "Collapse"}
              </Button>
            </div>
            {!editorCollapsed ? (
              <>
                <SqlEditor
                  value={sql}
                  onChange={handleSqlChange}
                  onRun={() => void handleRun()}
                  height={manualEditorHeight ?? undefined}
                  onHeightChange={setAutoEditorHeight}
                  framed={false}
                />
                <div
                  role="separator"
                  aria-orientation="horizontal"
                  aria-label="调整 SQL 编辑器高度"
                  className="flex h-4 cursor-row-resize items-center justify-center text-muted-foreground hover:bg-accent"
                  onPointerDown={handleDividerPointerDown}
                  onPointerMove={handleDividerPointerMove}
                  onPointerUp={handleDividerPointerUp}
                  onPointerCancel={handleDividerPointerUp}
                  onDoubleClick={() => setManualEditorHeight(null)}
                >
                  <GripHorizontal className="h-4 w-4" aria-hidden="true" />
                </div>
              </>
            ) : null}
          </div>
        </div>

        <ViewConfigBar queryId={queryId} />

        <div className="min-h-[260px] border-t bg-muted/20 p-4">
          <ResultPlaceholder
            error={lastError}
            isExecuting={isExecuting}
            execution={execution}
            columns={columns}
            rows={rows}
            returnedRows={rows.length}
            activeView={activeResultView}
            trajectoryError={trajectoryRequestIsCurrent ? aggregateTrajectories.error : null}
            trajectoryLoading={trajectoryRequestIsCurrent && aggregateTrajectories.isPending}
            trajectories={
              trajectoryDataIsCurrent ? aggregateTrajectories.data?.trajectories : undefined
            }
            trajectoryWarnings={
              trajectoryDataIsCurrent ? aggregateTrajectories.data?.warnings : undefined
            }
            onRowClick={handleRowClick}
            onUseSqlTemplate={handleUseSqlTemplate}
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
  activeView: ResultView;
  trajectoryError: unknown;
  trajectoryLoading: boolean;
  trajectories: Trajectory[] | undefined;
  trajectoryWarnings: Warning[] | undefined;
  onRowClick: (row: Row, rowNumber: number) => void;
  onUseSqlTemplate: () => void;
};

type ResultViewTabsProps = {
  activeView: ResultView;
  trajectoryDisabled: boolean;
  trajectoryDisabledReason: string;
  onChange: (view: ResultView) => void;
};

function ResultViewTabs({
  activeView,
  trajectoryDisabled,
  trajectoryDisabledReason,
  onChange,
}: ResultViewTabsProps) {
  return (
    <div className="flex items-center gap-2" role="tablist" aria-label="结果视图">
      <button
        type="button"
        role="tab"
        aria-selected={activeView === "row"}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm font-medium",
          activeView === "row"
            ? "border-primary bg-primary text-primary-foreground"
            : "bg-background text-muted-foreground hover:text-foreground",
        )}
        onClick={() => onChange("row")}
      >
        Table
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeView === "trajectory"}
        disabled={trajectoryDisabled}
        title={trajectoryDisabled ? trajectoryDisabledReason : "查看 Trajectory 气泡流"}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm font-medium",
          activeView === "trajectory"
            ? "border-primary bg-primary text-primary-foreground"
            : "bg-background text-muted-foreground hover:text-foreground",
          trajectoryDisabled && "cursor-not-allowed opacity-50 hover:text-muted-foreground",
        )}
        onClick={() => onChange("trajectory")}
      >
        Trajectory
      </button>
    </div>
  );
}

function ResultPlaceholder({
  error,
  isExecuting,
  execution,
  columns,
  rows,
  returnedRows,
  activeView,
  trajectoryError,
  trajectoryLoading,
  trajectories,
  trajectoryWarnings,
  onRowClick,
  onUseSqlTemplate,
}: ResultPlaceholderProps) {
  if (isExecuting) {
    return <LoadingState label="正在执行 SQL..." rows={6} />;
  }

  if (error !== null) {
    return <ErrorState error={error} />;
  }

  if (execution !== null) {
    if (activeView === "trajectory") {
      return (
        <TrajectoryResult
          isLoading={trajectoryLoading}
          error={trajectoryError}
          trajectories={trajectories}
          warnings={trajectoryWarnings}
        />
      );
    }

    if (rows.length > 0) {
      return <RowTable columns={columns} rows={rows} onRowClick={onRowClick} />;
    }

    return (
      <EmptyState title={`已返回 ${returnedRows} 行`} description="当前 SQL 没有结果行。" />
    );
  }

  return (
    <EmptyState
      icon={<DatabaseZap className="h-6 w-6" aria-hidden="true" />}
      title="还没有执行结果"
      description="选择连接并运行 SQL 后，可以在 Table 和 Trajectory 视图之间切换。"
      action={
        <Button variant="outline" onClick={onUseSqlTemplate}>
          从模板开始
        </Button>
      }
    />
  );
}

interface TrajectoryResultProps {
  isLoading: boolean;
  error: unknown;
  trajectories: Trajectory[] | undefined;
  warnings: Warning[] | undefined;
}

function TrajectoryResult({
  isLoading,
  error,
  trajectories,
  warnings,
}: TrajectoryResultProps) {
  if (isLoading) {
    return <LoadingState label="正在聚合 Trajectory..." rows={5} />;
  }

  if (error !== null && error !== undefined) {
    return <ErrorState error={error} />;
  }

  if (trajectories === undefined) {
    return (
      <EmptyState title="Trajectory 未聚合" description="切换到 Trajectory 后开始聚合。" />
    );
  }

  return (
    <div className="space-y-3">
      {warnings !== undefined && warnings.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <div className="font-medium">聚合 warning</div>
          <ul className="mt-1 space-y-1">
            {warnings.map((warning, index) => (
              <li key={`${warning.code}:${index}`}>
                {warning.code}: {warning.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {trajectories.length === 1 ? (
        <SingleTrajectoryView trajectory={trajectories[0]} />
      ) : (
        <div className="flex h-full min-h-[220px] items-center justify-center rounded-lg border border-dashed bg-background text-sm text-muted-foreground">
          检测到 {trajectories.length} 条 trajectories
        </div>
      )}
    </div>
  );
}

function readEditorCollapsedPreference(): boolean {
  return window.localStorage.getItem(SQL_EDITOR_COLLAPSED_KEY) === "true";
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

function getQueryPageTitle(queryId: number | null, queryName: string | null | undefined): string {
  if (queryId === null) {
    return "新建查询";
  }

  const normalizedName = queryName?.trim();
  return normalizedName ? normalizedName : `查询 #${queryId}`;
}

function isTrajectoryConfigComplete(
  config: ReturnType<typeof useQueryStore.getState>["trajectoryConfig"],
): boolean {
  return (
    config !== null &&
    config.group_by.trim().length > 0 &&
    config.role_column.trim().length > 0 &&
    config.content_column.trim().length > 0
  );
}

function getTrajectoryRequestKey(
  queryId: number,
  executedAt: string,
  config: NonNullable<ReturnType<typeof useQueryStore.getState>["trajectoryConfig"]>,
): string {
  return [queryId, executedAt, JSON.stringify(config)].join(":");
}

function getTrajectoryDisabledReason({
  configComplete,
  hasRows,
  hasQueryId,
}: {
  configComplete: boolean;
  hasRows: boolean;
  hasQueryId: boolean;
}): string {
  if (!configComplete) {
    return "请先配置 group_by / role_column / content_column";
  }
  if (!hasRows) {
    return "请先执行查询并返回结果行";
  }
  if (!hasQueryId) {
    return "当前查询结果缺少 query_id";
  }
  return "";
}
