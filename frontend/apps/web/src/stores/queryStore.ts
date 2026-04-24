import { create } from "zustand";

import type { Column, ExecutionInfo, ExecutionResult, FieldRender, Row, Warning } from "@/api/types";
export type { Column, ExecutionInfo, ExecutionResult, FieldRender, Row, Warning } from "@/api/types";

export interface QueryState {
  connectionId: number | null;
  sql: string;
  queryId: number | null;
  columns: Column[];
  rows: Row[];
  execution: ExecutionInfo | null;
  suggestedRenders: Record<string, FieldRender>;
  warnings: Warning[];
  isExecuting: boolean;
  setConnectionId(id: number | null): void;
  setSql(sql: string): void;
  setResult(result: ExecutionResult): void;
  reset(): void;
}

const initialResultState = {
  queryId: null,
  columns: [] as Column[],
  rows: [] as Row[],
  execution: null,
  suggestedRenders: {} as Record<string, FieldRender>,
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
        warnings: result.warnings,
        isExecuting: false,
      };
    }),
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
