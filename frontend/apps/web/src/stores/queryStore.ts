import { create } from "zustand";

import type { Column, ExecutionInfo, ExecutionResult, FieldRender, Row, Warning } from "@/api/types";
export type { Column, ExecutionInfo, ExecutionResult, FieldRender, Row, Warning } from "@/api/types";

export type SortDirection = "asc" | "desc";
export type ColumnPinDirection = "left" | "right";
export type RowHeightMode = "compact" | "medium" | "large" | "tall";

export interface SortConfig {
  column: string;
  direction: SortDirection;
}

export interface TableConfig {
  column_widths: Record<string, number>;
  hidden_columns: string[];
  frozen_columns: string[];
  pinned_columns: Record<string, ColumnPinDirection>;
  row_height: RowHeightMode;
  rich_preview: boolean;
  sort: SortConfig[];
}

export interface QueryState {
  connectionId: number | null;
  sql: string;
  queryId: number | null;
  columns: Column[];
  rows: Row[];
  execution: ExecutionInfo | null;
  suggestedRenders: Record<string, FieldRender>;
  fieldRenders: Record<string, FieldRender>;
  manualFieldRenderColumns: string[];
  tableConfig: TableConfig;
  warnings: Warning[];
  isExecuting: boolean;
  setConnectionId(id: number | null): void;
  setSql(sql: string): void;
  setResult(result: ExecutionResult): void;
  setFieldRender(col: string, render: FieldRender): void;
  toggleHiddenColumn(col: string): void;
  setColumnPin(col: string, dir: ColumnPinDirection | null): void;
  setRowHeight(mode: RowHeightMode): void;
  setRichPreview(enabled: boolean): void;
  setSort(col: string, dir: SortDirection | null): void;
  reset(): void;
}

export const initialTableConfig: TableConfig = {
  column_widths: {},
  hidden_columns: [],
  frozen_columns: [],
  pinned_columns: {},
  row_height: "compact",
  rich_preview: false,
  sort: [],
};

const initialResultState = {
  queryId: null,
  columns: [] as Column[],
  rows: [] as Row[],
  execution: null,
  suggestedRenders: {} as Record<string, FieldRender>,
  fieldRenders: {} as Record<string, FieldRender>,
  manualFieldRenderColumns: [] as string[],
  tableConfig: initialTableConfig,
  warnings: [] as Warning[],
};

export const useQueryStore = create<QueryState>((set) => ({
  connectionId: null,
  sql: "",
  ...initialResultState,
  isExecuting: false,
  setConnectionId: (id) => set({ connectionId: id }),
  setSql: (sql) => set({ sql }),
  setResult: (result) =>
    set((state) => {
      if (isSameResult(state, result)) {
        return { isExecuting: false };
      }

      return {
        queryId: result.query_id,
        columns: result.columns,
        rows: result.rows,
        execution: result.execution,
        suggestedRenders: result.suggested_field_renders,
        fieldRenders: mergeFieldRenders(result, state.fieldRenders, state.manualFieldRenderColumns),
        manualFieldRenderColumns: filterManualFieldRenderColumns(
          result,
          state.manualFieldRenderColumns,
        ),
        tableConfig: filterTableConfig(state.tableConfig, result.columns),
        warnings: result.warnings,
        isExecuting: false,
      };
    }),
  setFieldRender: (col, render) =>
    set((state) => ({
      fieldRenders: {
        ...state.fieldRenders,
        [col]: render,
      },
      manualFieldRenderColumns: state.manualFieldRenderColumns.includes(col)
        ? state.manualFieldRenderColumns
        : [...state.manualFieldRenderColumns, col],
    })),
  toggleHiddenColumn: (col) =>
    set((state) => {
      const hidden = new Set(state.tableConfig.hidden_columns);
      if (hidden.has(col)) {
        hidden.delete(col);
      } else {
        hidden.add(col);
      }

      return {
        tableConfig: {
          ...state.tableConfig,
          hidden_columns: Array.from(hidden),
        },
      };
    }),
  setColumnPin: (col, dir) =>
    set((state) => {
      const pinnedColumns = { ...state.tableConfig.pinned_columns };
      const frozenColumns = new Set(state.tableConfig.frozen_columns);

      if (dir === null) {
        delete pinnedColumns[col];
        frozenColumns.delete(col);
      } else {
        pinnedColumns[col] = dir;
        if (dir === "left") {
          frozenColumns.add(col);
        } else {
          frozenColumns.delete(col);
        }
      }

      return {
        tableConfig: {
          ...state.tableConfig,
          pinned_columns: pinnedColumns,
          frozen_columns: Array.from(frozenColumns),
        },
      };
    }),
  setSort: (col, dir) =>
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        sort: dir === null ? [] : [{ column: col, direction: dir }],
      },
    })),
  setRowHeight: (mode) =>
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        row_height: mode,
      },
    })),
  setRichPreview: (enabled) =>
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        rich_preview: enabled,
      },
    })),
  reset: () =>
    set({
      connectionId: null,
      sql: "",
      ...initialResultState,
      isExecuting: false,
    }),
}));

function isSameResult(state: QueryState, result: ExecutionResult): boolean {
  const execution = state.execution;

  return (
    state.queryId === result.query_id &&
    state.columns === result.columns &&
    state.rows === result.rows &&
    state.suggestedRenders === result.suggested_field_renders &&
    state.warnings === result.warnings &&
    execution !== null &&
    execution.executed_at === result.execution.executed_at &&
    execution.duration_ms === result.execution.duration_ms &&
    execution.row_count === result.execution.row_count &&
    execution.truncated === result.execution.truncated
  );
}

function mergeFieldRenders(
  result: ExecutionResult,
  previousFieldRenders: Record<string, FieldRender>,
  manualColumns: string[],
): Record<string, FieldRender> {
  const nextFieldRenders = { ...result.suggested_field_renders };
  const returnedColumns = new Set(result.columns.map((column) => column.name));

  for (const columnName of manualColumns) {
    if (returnedColumns.has(columnName) && previousFieldRenders[columnName] !== undefined) {
      nextFieldRenders[columnName] = previousFieldRenders[columnName];
    }
  }

  return nextFieldRenders;
}

function filterManualFieldRenderColumns(
  result: ExecutionResult,
  manualColumns: string[],
): string[] {
  const returnedColumns = new Set(result.columns.map((column) => column.name));
  return manualColumns.filter((columnName) => returnedColumns.has(columnName));
}

function filterTableConfig(tableConfig: TableConfig, columns: Column[]): TableConfig {
  const returnedColumns = new Set(columns.map((column) => column.name));
  const pinnedColumns = Object.fromEntries(
    Object.entries(tableConfig.pinned_columns).filter(([columnName]) =>
      returnedColumns.has(columnName),
    ),
  );

  return {
    column_widths: Object.fromEntries(
      Object.entries(tableConfig.column_widths).filter(([columnName]) =>
        returnedColumns.has(columnName),
      ),
    ),
    hidden_columns: tableConfig.hidden_columns.filter((columnName) =>
      returnedColumns.has(columnName),
    ),
    frozen_columns: tableConfig.frozen_columns.filter((columnName) =>
      returnedColumns.has(columnName),
    ),
    pinned_columns: pinnedColumns,
    row_height: tableConfig.row_height,
    rich_preview: tableConfig.rich_preview,
    sort: tableConfig.sort.filter((sortConfig) => returnedColumns.has(sortConfig.column)),
  };
}
