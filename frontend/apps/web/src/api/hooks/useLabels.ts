import { useCallback, useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import type {
  LabelBatchResult,
  LabelRecordRead,
  LabelsByRowResponse,
} from "@/api/types";
import { formatApiError } from "@/lib/formatApiError";
import { useLabelsStore } from "@/stores/labelsStore";

const MAX_LABEL_ROWS_PER_REQUEST = 1000;
const ROW_IDENTITY_KEY_SEPARATOR = "\u001f";
const CELL_MUTATION_KEY_SEPARATOR = "\u001e";
const labelMutationQueues = new Map<string, Promise<void>>();

type LabelsByRow = Record<string, Record<string, unknown>>;
type LabelValue = string | string[] | null;

type UpsertLabelArgs = {
  rowIdentity: string;
  fieldKey: string;
  value: LabelValue;
};

type BatchUpsertLabelArgs = {
  rowIdentities: string[];
  fieldKey: string;
  value: LabelValue;
};

type LabelSnapshot = {
  queryId: number;
  rowIdentity: string;
  fieldKey: string;
  hadPreviousValue: boolean;
  previousValue: unknown;
};

export const labelsKeys = {
  all: ["labels"] as const,
  query: (queryId: number) => [...labelsKeys.all, queryId] as const,
  rows: (queryId: number, rowIdentitiesKey: string) =>
    [...labelsKeys.query(queryId), rowIdentitiesKey] as const,
};

export function useLabels(queryId: number | null, rowIdentities: string[]) {
  const setActiveQuery = useLabelsStore((state) => state.setActiveQuery);
  const setLabels = useLabelsStore((state) => state.setLabels);
  const setLabelsForQuery = useLabelsStore((state) => state.setLabelsForQuery);
  const normalizedRowIdentities = useMemo(
    () => Array.from(new Set(rowIdentities.filter((item) => item.length > 0))).sort(),
    [rowIdentities],
  );
  const normalizedRowIdentitiesKey = normalizedRowIdentities.join(
    ROW_IDENTITY_KEY_SEPARATOR,
  );
  const enabled = queryId !== null && normalizedRowIdentities.length > 0;

  const query = useQuery({
    queryKey:
      queryId === null
        ? labelsKeys.rows(0, "null")
        : labelsKeys.rows(queryId, normalizedRowIdentitiesKey),
    enabled,
    gcTime: 0,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<LabelsByRowResponse> => {
      const chunks = chunkRowIdentities(normalizedRowIdentities);
      const responses = await Promise.all(
        chunks.map(async (chunk) => {
          const { data, error, response } = await apiClient.POST(
            "/queries/{query_id}/labels/query",
            {
              params: { path: { query_id: queryId! } },
              body: { row_identities: chunk },
            },
          );

          if (error !== undefined) {
            throw { data, error, response };
          }
          if (!response.ok || data === undefined) {
            throw new Error(`Failed to load labels with status ${response.status}`);
          }

          return data;
        }),
      );

      return {
        labels_by_row: responses.reduce<LabelsByRow>(
          (merged, item) => ({ ...merged, ...item.labels_by_row }),
          {},
        ),
      };
    },
  });

  useEffect(() => {
    setActiveQuery(queryId);
  }, [queryId, setActiveQuery]);

  useEffect(() => {
    if (!enabled) {
      if (queryId === null) {
        setLabels({});
      }
      return;
    }
    if (query.data !== undefined) {
      setLabelsForQuery(queryId, query.data.labels_by_row);
    }
  }, [enabled, query.data, queryId, setLabels, setLabelsForQuery]);

  return query;
}

export function useUpsertLabel(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (args: UpsertLabelArgs): Promise<LabelRecordRead | null> => {
      const { data, error, response } = await apiClient.POST(
        "/queries/{query_id}/labels",
        {
          params: { path: { query_id: queryId } },
          body: {
            row_identity: args.rowIdentity,
            field_key: args.fieldKey,
            value: args.value,
          },
        },
      );

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok) {
        throw new Error(`Failed to save label with status ${response.status}`);
      }

      return data ?? null;
    },
    onMutate: async (args): Promise<LabelSnapshot> => {
      await queryClient.cancelQueries({ queryKey: labelsKeys.query(queryId) });
      useLabelsStore
        .getState()
        .markPendingLabelForQuery(queryId, args.rowIdentity, args.fieldKey);
      const snapshot = getLabelSnapshot(queryId, args.rowIdentity, args.fieldKey);
      applyOptimisticLabel(queryId, args.rowIdentity, args.fieldKey, args.value);
      return snapshot;
    },
    onError: (error, _args, snapshot) => {
      if (snapshot !== undefined) {
        restoreLabelSnapshot(snapshot);
      }
      toast.error(formatApiError(error));
    },
    onSuccess: (record, args) => {
      if (record === null) {
        useLabelsStore
          .getState()
          .removeLabelForQuery(queryId, args.rowIdentity, args.fieldKey);
        return;
      }
      useLabelsStore
        .getState()
        .patchLabelForQuery(queryId, record.row_identity, record.field_key, record.value);
    },
    onSettled: async (_data, _error, args) => {
      useLabelsStore
        .getState()
        .clearPendingLabelForQuery(queryId, args.rowIdentity, args.fieldKey);
      await queryClient.invalidateQueries({ queryKey: labelsKeys.query(queryId) });
    },
  });
}

export function useQueuedUpsertLabel(queryId: number) {
  const upsert = useUpsertLabel(queryId);
  const { isPending, mutateAsync } = upsert;

  const commitLabel = useCallback(
    (args: UpsertLabelArgs): Promise<void> => {
      const queueKey = getCellMutationQueueKey(queryId, args.rowIdentity, args.fieldKey);
      const previous = labelMutationQueues.get(queueKey) ?? Promise.resolve();
      const next = previous
        .catch(() => undefined)
        .then(() =>
          mutateAsync(args).then(
            () => undefined,
            () => undefined,
          ),
        )
        .finally(() => {
          if (labelMutationQueues.get(queueKey) === next) {
            labelMutationQueues.delete(queueKey);
          }
        });
      labelMutationQueues.set(queueKey, next);
      return next;
    },
    [mutateAsync, queryId],
  );

  return {
    commitLabel,
    isPending,
  };
}

function getCellMutationQueueKey(
  queryId: number,
  rowIdentity: string,
  fieldKey: string,
): string {
  return [queryId, rowIdentity, fieldKey].join(CELL_MUTATION_KEY_SEPARATOR);
}

export function useBatchUpsertLabels(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (args: BatchUpsertLabelArgs): Promise<LabelBatchResult> => {
      const { data, error, response } = await apiClient.POST(
        "/queries/{query_id}/labels/batch",
        {
          params: { path: { query_id: queryId } },
          body: {
            row_identities: args.rowIdentities,
            field_key: args.fieldKey,
            value: args.value,
          },
        },
      );

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to save labels with status ${response.status}`);
      }

      return data;
    },
    onMutate: async (args): Promise<LabelSnapshot[]> => {
      await queryClient.cancelQueries({ queryKey: labelsKeys.query(queryId) });
      for (const rowIdentity of args.rowIdentities) {
        useLabelsStore
          .getState()
          .markPendingLabelForQuery(queryId, rowIdentity, args.fieldKey);
      }
      const snapshots = args.rowIdentities.map((rowIdentity) =>
        getLabelSnapshot(queryId, rowIdentity, args.fieldKey),
      );
      for (const rowIdentity of args.rowIdentities) {
        applyOptimisticLabel(queryId, rowIdentity, args.fieldKey, args.value);
      }
      return snapshots;
    },
    onError: (error, _args, snapshots) => {
      if (snapshots !== undefined) {
        restoreLabelSnapshots(snapshots);
      }
      toast.error(formatApiError(error));
    },
    onSuccess: (result, _args, snapshots) => {
      const errors = result.errors ?? [];
      if (errors.length > 0 && snapshots !== undefined) {
        const failedRows = new Set(errors.map((item) => item.row_identity));
        restoreLabelSnapshots(
          snapshots.filter((snapshot) => failedRows.has(snapshot.rowIdentity)),
        );
        toast.error(`批量打标完成，${errors.length} 行失败`);
      }
    },
    onSettled: async (_data, _error, args) => {
      for (const rowIdentity of args.rowIdentities) {
        useLabelsStore
          .getState()
          .clearPendingLabelForQuery(queryId, rowIdentity, args.fieldKey);
      }
      await queryClient.invalidateQueries({ queryKey: labelsKeys.query(queryId) });
    },
  });
}

function chunkRowIdentities(rowIdentities: string[]): string[][] {
  const chunks: string[][] = [];
  for (let index = 0; index < rowIdentities.length; index += MAX_LABEL_ROWS_PER_REQUEST) {
    chunks.push(rowIdentities.slice(index, index + MAX_LABEL_ROWS_PER_REQUEST));
  }
  return chunks;
}

function getLabelSnapshot(queryId: number, rowIdentity: string, fieldKey: string): LabelSnapshot {
  const state = useLabelsStore.getState();
  const rowLabels = state.activeQueryId === queryId ? state.labelsByRow[rowIdentity] : undefined;
  return {
    queryId,
    rowIdentity,
    fieldKey,
    hadPreviousValue: rowLabels !== undefined && fieldKey in rowLabels,
    previousValue: rowLabels?.[fieldKey],
  };
}

function applyOptimisticLabel(
  queryId: number,
  rowIdentity: string,
  fieldKey: string,
  value: LabelValue,
) {
  if (value === null) {
    useLabelsStore.getState().removeLabelForQuery(queryId, rowIdentity, fieldKey);
    return;
  }
  useLabelsStore.getState().patchLabelForQuery(queryId, rowIdentity, fieldKey, value);
}

function restoreLabelSnapshot(snapshot: LabelSnapshot) {
  if (snapshot.hadPreviousValue) {
    useLabelsStore
      .getState()
      .patchLabelForQuery(
        snapshot.queryId,
        snapshot.rowIdentity,
        snapshot.fieldKey,
        snapshot.previousValue,
      );
    return;
  }
  useLabelsStore
    .getState()
    .removeLabelForQuery(snapshot.queryId, snapshot.rowIdentity, snapshot.fieldKey);
}

function restoreLabelSnapshots(snapshots: LabelSnapshot[]) {
  for (const snapshot of snapshots) {
    restoreLabelSnapshot(snapshot);
  }
}
