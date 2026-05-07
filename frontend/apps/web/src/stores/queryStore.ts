import { create } from "zustand";

import type {
  Column,
  ExecutionInfo,
  ExecutionResult,
  FieldRender,
  Row,
  ViewConfigPayload,
  ViewConfigRead,
  Warning,
} from "@/api/types";

export type {
  Column,
  ExecutionInfo,
  ExecutionResult,
  FieldRender,
  Row,
  ViewConfigPayload,
  ViewConfigRead,
  Warning,
} from "@/api/types";

export type SortDirection = "asc" | "desc";
export type ColumnPinDirection = "left" | "right";
export type RowHeightMode = "compact" | "medium" | "large" | "tall";

export interface SortConfig {
  column: string;
  direction: SortDirection;
}

export interface TableConfig {
  [key: string]: unknown;
  column_widths: Record<string, number>;
  hidden_columns: string[];
  frozen_columns: string[];
  pinned_columns: Record<string, ColumnPinDirection>;
  row_height: RowHeightMode;
  rich_preview: boolean;
  sort: SortConfig[];
}

export interface TrajectoryConfig {
  group_by: string;
  role_column: string;
  content_column: string;
  tool_calls_column?: string | null;
  order_by?: string | null;
  order_direction: SortDirection;
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
  trajectoryConfig: TrajectoryConfig | null;
  rowIdentityColumn: string | null;
  warnings: Warning[];
  selectedRowIds: Set<string>;
  isExecuting: boolean;
  isDirty: boolean;
  setConnectionId(id: number | null): void;
  setSql(sql: string): void;
  setResult(result: ExecutionResult): void;
  markDirty(): void;
  markClean(): void;
  setFieldRender(col: string, render: FieldRender): void;
  removeFieldRender(col: string): void;
  toggleHiddenColumn(col: string): void;
  setColumnWidth(col: string, width: number): void;
  toggleFrozenColumn(col: string): void;
  setColumnPin(col: string, dir: ColumnPinDirection | null): void;
  setRowHeight(mode: RowHeightMode): void;
  setRichPreview(enabled: boolean): void;
  setSort(col: string, dir: SortDirection | null): void;
  setTrajectoryConfig(cfg: TrajectoryConfig | null): void;
  setRowIdentityColumn(col: string | null): void;
  setSelectedRowIds(rowIds: Iterable<string>): void;
  setRowsSelected(rowIds: Iterable<string>, selected: boolean): void;
  clearSelection(): void;
  applyViewConfig(vc: ViewConfigRead): void;
  mergeSuggestedRenders(suggested: Record<string, FieldRender>): void;
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
  trajectoryConfig: null as TrajectoryConfig | null,
  rowIdentityColumn: null as string | null,
  warnings: [] as Warning[],
  selectedRowIds: new Set<string>(),
  isDirty: false,
};

export const useQueryStore = create<QueryState>((set, get) => ({
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
        fieldRenders: filterFieldRenders(state.fieldRenders, result.columns),
        manualFieldRenderColumns: filterColumnNames(
          state.manualFieldRenderColumns,
          result.columns,
        ),
        tableConfig: filterTableConfig(state.tableConfig, result.columns),
        warnings: result.warnings,
        selectedRowIds: new Set(),
        isExecuting: false,
      };
    }),
  markDirty: () => set({ isDirty: true }),
  markClean: () => set({ isDirty: false }),
  setFieldRender: (col, render) => {
    set((state) => ({
      fieldRenders: {
        ...state.fieldRenders,
        [col]: render,
      },
      manualFieldRenderColumns: state.manualFieldRenderColumns.includes(col)
        ? state.manualFieldRenderColumns
        : [...state.manualFieldRenderColumns, col],
    }));
    get().markDirty();
  },
  removeFieldRender: (col) => {
    set((state) => {
      const fieldRenders = { ...state.fieldRenders };
      delete fieldRenders[col];

      return {
        fieldRenders,
        manualFieldRenderColumns: state.manualFieldRenderColumns.filter(
          (columnName) => columnName !== col,
        ),
      };
    });
    get().markDirty();
  },
  toggleHiddenColumn: (col) => {
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
    });
    get().markDirty();
  },
  setColumnWidth: (col, width) => {
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        column_widths: {
          ...state.tableConfig.column_widths,
          [col]: width,
        },
      },
    }));
    get().markDirty();
  },
  toggleFrozenColumn: (col) => {
    set((state) => {
      const frozenColumns = new Set(state.tableConfig.frozen_columns);
      const pinnedColumns = { ...state.tableConfig.pinned_columns };

      if (frozenColumns.has(col)) {
        frozenColumns.delete(col);
        delete pinnedColumns[col];
      } else {
        frozenColumns.add(col);
        pinnedColumns[col] = "left";
      }

      return {
        tableConfig: {
          ...state.tableConfig,
          frozen_columns: Array.from(frozenColumns),
          pinned_columns: pinnedColumns,
        },
      };
    });
    get().markDirty();
  },
  setColumnPin: (col, dir) => {
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
    });
    get().markDirty();
  },
  setSort: (col, dir) => {
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        sort: dir === null ? [] : [{ column: col, direction: dir }],
      },
    }));
    get().markDirty();
  },
  setRowHeight: (mode) => {
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        row_height: mode,
      },
    }));
    get().markDirty();
  },
  setRichPreview: (enabled) => {
    set((state) => ({
      tableConfig: {
        ...state.tableConfig,
        rich_preview: enabled,
      },
    }));
    get().markDirty();
  },
  setTrajectoryConfig: (cfg) => {
    set({ trajectoryConfig: cfg });
    get().markDirty();
  },
  setRowIdentityColumn: (col) => {
    set({ rowIdentityColumn: col });
    get().markDirty();
  },
  setSelectedRowIds: (rowIds) =>
    set({ selectedRowIds: createSelectedRowIdsSet(rowIds) }),
  setRowsSelected: (rowIds, selected) =>
    set((state) => {
      const nextSelectedRowIds = new Set(state.selectedRowIds);
      let changed = false;

      for (const rowId of rowIds) {
        if (rowId.length === 0) {
          continue;
        }
        if (selected) {
          if (!nextSelectedRowIds.has(rowId)) {
            nextSelectedRowIds.add(rowId);
            changed = true;
          }
          continue;
        }
        if (nextSelectedRowIds.delete(rowId)) {
          changed = true;
        }
      }

      return changed ? { selectedRowIds: nextSelectedRowIds } : {};
    }),
  clearSelection: () =>
    set((state) =>
      state.selectedRowIds.size === 0 ? {} : { selectedRowIds: new Set<string>() },
    ),
  applyViewConfig: (vc) => {
    const fieldRenders = vc.field_renders ?? {};
    set({
      fieldRenders,
      manualFieldRenderColumns: Object.keys(fieldRenders),
      tableConfig: normalizeTableConfig(vc.table_config),
      trajectoryConfig: vc.trajectory_config ?? null,
      rowIdentityColumn: vc.row_identity_column ?? null,
    });
    get().markClean();
  },
  mergeSuggestedRenders: (suggested) =>
    set((state) => {
      let changed = false;
      const fieldRenders = { ...state.fieldRenders };

      for (const [columnName, render] of Object.entries(suggested)) {
        if (fieldRenders[columnName] === undefined) {
          fieldRenders[columnName] = render;
          changed = true;
        }
      }

      return changed ? { fieldRenders } : {};
    }),
  reset: () =>
    set({
      connectionId: null,
      sql: "",
      ...initialResultState,
      selectedRowIds: new Set(),
      isExecuting: false,
    }),
}));

function createSelectedRowIdsSet(rowIds: Iterable<string>): Set<string> {
  const selectedRowIds = new Set<string>();
  for (const rowId of rowIds) {
    if (rowId.length > 0) {
      selectedRowIds.add(rowId);
    }
  }
  return selectedRowIds;
}

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

function filterFieldRenders(
  fieldRenders: Record<string, FieldRender>,
  columns: Column[],
): Record<string, FieldRender> {
  const returnedColumns = new Set(columns.map((column) => column.name));
  return Object.fromEntries(
    Object.entries(fieldRenders).filter(([columnName]) => returnedColumns.has(columnName)),
  );
}

function filterColumnNames(columnNames: string[], columns: Column[]): string[] {
  const returnedColumns = new Set(columns.map((column) => column.name));
  return columnNames.filter((columnName) => returnedColumns.has(columnName));
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

function normalizeTableConfig(tableConfig: ViewConfigRead["table_config"]): TableConfig {
  if (!isRecord(tableConfig)) {
    return initialTableConfig;
  }

  const source = tableConfig;

  return {
    column_widths: normalizeNumberRecord(source.column_widths),
    hidden_columns: normalizeStringArray(source.hidden_columns),
    frozen_columns: normalizeStringArray(source.frozen_columns),
    pinned_columns: normalizePinnedColumns(source.pinned_columns),
    row_height: normalizeRowHeight(source.row_height),
    rich_preview:
      typeof source.rich_preview === "boolean"
        ? source.rich_preview
        : initialTableConfig.rich_preview,
    sort: normalizeSortConfig(source.sort),
  };
}

function normalizeNumberRecord(value: unknown): Record<string, number> {
  if (!isRecord(value)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, number] => {
      const [, width] = entry;
      return typeof width === "number" && Number.isFinite(width);
    }),
  );
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function normalizePinnedColumns(value: unknown): Record<string, ColumnPinDirection> {
  if (!isRecord(value)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, ColumnPinDirection] => {
      const [, direction] = entry;
      return direction === "left" || direction === "right";
    }),
  );
}

function normalizeRowHeight(value: unknown): RowHeightMode {
  if (value === "compact" || value === "medium" || value === "large" || value === "tall") {
    return value;
  }

  return initialTableConfig.row_height;
}

function normalizeSortConfig(value: unknown): SortConfig[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }

    const { column, direction } = item;
    if (typeof column !== "string" || (direction !== "asc" && direction !== "desc")) {
      return [];
    }

    return [{ column, direction }];
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function getViewConfigPayloadFromState(state: QueryState): ViewConfigPayload {
  return {
    field_renders: state.fieldRenders,
    table_config: state.tableConfig,
    trajectory_config: state.trajectoryConfig,
    row_identity_column: state.rowIdentityColumn,
  };
}

export function viewConfigPayloadMatchesState(
  payload: ViewConfigPayload,
  state: QueryState,
): boolean {
  return JSON.stringify(payload) === JSON.stringify(getViewConfigPayloadFromState(state));
}

export function viewConfigIsEmpty(viewConfig: ViewConfigRead): boolean {
  return (
    Object.keys(viewConfig.field_renders ?? {}).length === 0 &&
    tableConfigIsEmpty(viewConfig.table_config) &&
    viewConfig.trajectory_config == null &&
    viewConfig.row_identity_column == null
  );
}

function tableConfigIsEmpty(tableConfig: ViewConfigRead["table_config"]): boolean {
  if (!isRecord(tableConfig)) {
    return true;
  }

  const knownKeys = new Set([
    "column_widths",
    "hidden_columns",
    "frozen_columns",
    "sort",
    "pinned_columns",
    "row_height",
    "rich_preview",
  ]);
  const knownValuesAreEmpty =
    objectIsEmpty(tableConfig.column_widths) &&
    arrayIsEmpty(tableConfig.hidden_columns) &&
    arrayIsEmpty(tableConfig.frozen_columns) &&
    arrayIsEmpty(tableConfig.sort) &&
    objectIsEmpty(tableConfig.pinned_columns) &&
    (tableConfig.row_height == null || tableConfig.row_height === initialTableConfig.row_height) &&
    (tableConfig.rich_preview == null ||
      tableConfig.rich_preview === initialTableConfig.rich_preview);

  return (
    knownValuesAreEmpty &&
    Object.entries(tableConfig).every(
      ([key, value]) => knownKeys.has(key) || viewConfigValueIsEmpty(value),
    )
  );
}

function viewConfigValueIsEmpty(value: unknown): boolean {
  if (value == null || value === false) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  if (isRecord(value)) {
    return Object.keys(value).length === 0;
  }
  return false;
}

function objectIsEmpty(value: unknown): boolean {
  return !isRecord(value) || Object.keys(value).length === 0;
}

function arrayIsEmpty(value: unknown): boolean {
  return !Array.isArray(value) || value.length === 0;
}
