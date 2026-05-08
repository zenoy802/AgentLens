import { create } from "zustand";

type LabelsByRow = Record<string, Record<string, unknown>>;
type PendingLabelsByRow = Record<string, Record<string, true>>;

export interface LabelsState {
  activeQueryId: number | null;
  activeResultKey: string | null;
  labelsByRow: LabelsByRow;
  pendingLabelsByRow: PendingLabelsByRow;
  setActiveQuery(queryId: number | null, resultKey?: string | null): void;
  setLabels(data: LabelsByRow): void;
  setLabelsForQuery(queryId: number, resultKey: string | null, data: LabelsByRow): void;
  patchLabel(rowId: string, fieldKey: string, value: unknown): void;
  patchLabelForQuery(
    queryId: number,
    resultKey: string | null,
    rowId: string,
    fieldKey: string,
    value: unknown,
  ): void;
  removeLabel(rowId: string, fieldKey: string): void;
  removeLabelForQuery(
    queryId: number,
    resultKey: string | null,
    rowId: string,
    fieldKey: string,
  ): void;
  markPendingLabelForQuery(
    queryId: number,
    resultKey: string | null,
    rowId: string,
    fieldKey: string,
  ): void;
  clearPendingLabelForQuery(
    queryId: number,
    resultKey: string | null,
    rowId: string,
    fieldKey: string,
  ): void;
}

export const useLabelsStore = create<LabelsState>((set) => ({
  activeQueryId: null,
  activeResultKey: null,
  labelsByRow: {},
  pendingLabelsByRow: {},
  setActiveQuery: (queryId, resultKey = null) =>
    set((state) => {
      const nextResultKey = queryId === null ? null : resultKey;
      return state.activeQueryId === queryId && state.activeResultKey === nextResultKey
        ? {}
        : {
            activeQueryId: queryId,
            activeResultKey: nextResultKey,
            labelsByRow: {},
            pendingLabelsByRow: {},
          };
    }),
  setLabels: (data) => set({ labelsByRow: data, pendingLabelsByRow: {} }),
  setLabelsForQuery: (queryId, resultKey, data) =>
    set((state) =>
      labelsContextMatches(state, queryId, resultKey)
        ? {
            labelsByRow: mergeServerLabelsWithPendingEdits(
              data,
              state.labelsByRow,
              state.pendingLabelsByRow,
            ),
          }
        : {},
    ),
  patchLabel: (rowId, fieldKey, value) =>
    set((state) => ({
      labelsByRow: {
        ...state.labelsByRow,
        [rowId]: {
          ...state.labelsByRow[rowId],
          [fieldKey]: value,
        },
      },
    })),
  patchLabelForQuery: (queryId, resultKey, rowId, fieldKey, value) =>
    set((state) =>
      labelsContextMatches(state, queryId, resultKey)
        ? {
            labelsByRow: {
              ...state.labelsByRow,
              [rowId]: {
                ...state.labelsByRow[rowId],
                [fieldKey]: value,
              },
            },
          }
        : {},
    ),
  removeLabel: (rowId, fieldKey) =>
    set((state) => {
      const rowLabels = state.labelsByRow[rowId];
      if (rowLabels === undefined || !(fieldKey in rowLabels)) {
        return {};
      }

      const nextRowLabels = { ...rowLabels };
      delete nextRowLabels[fieldKey];

      const labelsByRow = { ...state.labelsByRow };
      if (Object.keys(nextRowLabels).length === 0) {
        delete labelsByRow[rowId];
      } else {
        labelsByRow[rowId] = nextRowLabels;
      }

      return { labelsByRow };
    }),
  removeLabelForQuery: (queryId, resultKey, rowId, fieldKey) =>
    set((state) => {
      if (!labelsContextMatches(state, queryId, resultKey)) {
        return {};
      }

      const rowLabels = state.labelsByRow[rowId];
      if (rowLabels === undefined || !(fieldKey in rowLabels)) {
        return {};
      }

      const nextRowLabels = { ...rowLabels };
      delete nextRowLabels[fieldKey];

      const labelsByRow = { ...state.labelsByRow };
      if (Object.keys(nextRowLabels).length === 0) {
        delete labelsByRow[rowId];
      } else {
        labelsByRow[rowId] = nextRowLabels;
      }

      return { labelsByRow };
    }),
  markPendingLabelForQuery: (queryId, resultKey, rowId, fieldKey) =>
    set((state) =>
      labelsContextMatches(state, queryId, resultKey)
        ? {
            pendingLabelsByRow: {
              ...state.pendingLabelsByRow,
              [rowId]: {
                ...state.pendingLabelsByRow[rowId],
                [fieldKey]: true,
              },
            },
          }
        : {},
    ),
  clearPendingLabelForQuery: (queryId, resultKey, rowId, fieldKey) =>
    set((state) => {
      if (!labelsContextMatches(state, queryId, resultKey)) {
        return {};
      }

      const rowPendingLabels = state.pendingLabelsByRow[rowId];
      if (rowPendingLabels === undefined || !(fieldKey in rowPendingLabels)) {
        return {};
      }

      const nextRowPendingLabels = { ...rowPendingLabels };
      delete nextRowPendingLabels[fieldKey];

      const pendingLabelsByRow = { ...state.pendingLabelsByRow };
      if (Object.keys(nextRowPendingLabels).length === 0) {
        delete pendingLabelsByRow[rowId];
      } else {
        pendingLabelsByRow[rowId] = nextRowPendingLabels;
      }

      return { pendingLabelsByRow };
    }),
}));

function labelsContextMatches(
  state: Pick<LabelsState, "activeQueryId" | "activeResultKey">,
  queryId: number,
  resultKey: string | null,
): boolean {
  return state.activeQueryId === queryId && state.activeResultKey === resultKey;
}

function mergeServerLabelsWithPendingEdits(
  serverLabelsByRow: LabelsByRow,
  currentLabelsByRow: LabelsByRow,
  pendingLabelsByRow: PendingLabelsByRow,
): LabelsByRow {
  const labelsByRow = Object.fromEntries(
    Object.entries(serverLabelsByRow).map(([rowId, rowLabels]) => [
      rowId,
      { ...rowLabels },
    ]),
  );

  for (const [rowId, pendingFields] of Object.entries(pendingLabelsByRow)) {
    const currentRowLabels = currentLabelsByRow[rowId];
    for (const fieldKey of Object.keys(pendingFields)) {
      if (currentRowLabels !== undefined && fieldKey in currentRowLabels) {
        labelsByRow[rowId] = {
          ...labelsByRow[rowId],
          [fieldKey]: currentRowLabels[fieldKey],
        };
        continue;
      }

      const nextRowLabels = { ...labelsByRow[rowId] };
      delete nextRowLabels[fieldKey];
      if (Object.keys(nextRowLabels).length === 0) {
        delete labelsByRow[rowId];
      } else {
        labelsByRow[rowId] = nextRowLabels;
      }
    }
  }

  return labelsByRow;
}
