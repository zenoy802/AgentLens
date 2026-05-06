import { create } from "zustand";

export interface LabelsState {
  activeQueryId: number | null;
  labelsByRow: Record<string, Record<string, unknown>>;
  pendingLabelsByRow: Record<string, Record<string, true>>;
  setActiveQuery(queryId: number | null): void;
  setLabels(data: Record<string, Record<string, unknown>>): void;
  setLabelsForQuery(queryId: number, data: Record<string, Record<string, unknown>>): void;
  patchLabel(rowId: string, fieldKey: string, value: unknown): void;
  patchLabelForQuery(
    queryId: number,
    rowId: string,
    fieldKey: string,
    value: unknown,
  ): void;
  removeLabel(rowId: string, fieldKey: string): void;
  removeLabelForQuery(queryId: number, rowId: string, fieldKey: string): void;
  markPendingLabelForQuery(queryId: number, rowId: string, fieldKey: string): void;
  clearPendingLabelForQuery(queryId: number, rowId: string, fieldKey: string): void;
}

export const useLabelsStore = create<LabelsState>((set) => ({
  activeQueryId: null,
  labelsByRow: {},
  pendingLabelsByRow: {},
  setActiveQuery: (queryId) =>
    set((state) =>
      state.activeQueryId === queryId
        ? {}
        : {
            activeQueryId: queryId,
            labelsByRow: {},
            pendingLabelsByRow: {},
          },
    ),
  setLabels: (data) => set({ labelsByRow: data, pendingLabelsByRow: {} }),
  setLabelsForQuery: (queryId, data) =>
    set((state) =>
      state.activeQueryId === queryId
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
  patchLabelForQuery: (queryId, rowId, fieldKey, value) =>
    set((state) =>
      state.activeQueryId === queryId
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
  removeLabelForQuery: (queryId, rowId, fieldKey) =>
    set((state) => {
      if (state.activeQueryId !== queryId) {
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
  markPendingLabelForQuery: (queryId, rowId, fieldKey) =>
    set((state) =>
      state.activeQueryId === queryId
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
  clearPendingLabelForQuery: (queryId, rowId, fieldKey) =>
    set((state) => {
      if (state.activeQueryId !== queryId) {
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

function mergeServerLabelsWithPendingEdits(
  serverLabelsByRow: Record<string, Record<string, unknown>>,
  currentLabelsByRow: Record<string, Record<string, unknown>>,
  pendingLabelsByRow: Record<string, Record<string, true>>,
): Record<string, Record<string, unknown>> {
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
