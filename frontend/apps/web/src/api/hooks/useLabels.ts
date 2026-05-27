import { useCallback, useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { labelSchemaKey } from "@/api/hooks/useLabelSchema";
import type {
  LabelBatchResult,
  LabelRecordRead,
  LabelsByRowResponse,
} from "@/api/types";
import { locallyHandledMutationMeta } from "@/api/mutationMeta";
import { formatApiError, getApiError } from "@/lib/formatApiError";
import { useLabelsStore } from "@/stores/labelsStore";

const MAX_LABEL_ROWS_PER_REQUEST = 1000;
const PARALLEL_LABEL_FETCH_THRESHOLD = 1000;
const CELL_MUTATION_KEY_SEPARATOR = "\u001e";
const labelMutationQueues = new Map<string, Promise<void>>();

type LabelsByRow = Record<string, Record<string, unknown>>;
type LabelValue = string | string[] | null;

type UpsertLabelArgs = {
  rowIdentity: string;
  fieldKey: string;
  value: LabelValue;
};

type UpsertLabelMutationArgs = UpsertLabelArgs & {
  resultKey: string | null;
};

type BatchUpsertLabelArgs = {
  rowIdentities: string[];
  fieldKey: string;
  value: LabelValue;
};

type LabelSnapshot = {
  queryId: number;
  resultKey: string | null;
  rowIdentity: string;
  fieldKey: string;
  hadPreviousValue: boolean;
  previousValue: unknown;
};

export const labelsKeys = {
  all: ["labels"] as const,
  query: (queryId: number) => [...labelsKeys.all, queryId] as const,
  rows: (queryId: number, rowIdentitiesKey: string, resultKey: string) =>
    [...labelsKeys.query(queryId), rowIdentitiesKey, resultKey] as const,
};

export function useLabels(
  queryId: number | null,
  rowIdentities: string[],
  resultKey = "current",
) {
  const setActiveQuery = useLabelsStore((state) => state.setActiveQuery);
  const setLabels = useLabelsStore((state) => state.setLabels);
  const setLabelsForQuery = useLabelsStore((state) => state.setLabelsForQuery);
  const normalizedRowIdentities = useMemo(
    () => Array.from(new Set(rowIdentities.filter((item) => item.length > 0))).sort(),
    [rowIdentities],
  );
  const rowIdentitiesCacheKey = useMemo(
    () => getRowIdentitiesCacheKey(normalizedRowIdentities),
    [normalizedRowIdentities],
  );
  const enabled = queryId !== null && normalizedRowIdentities.length > 0;

  const query = useQuery({
    queryKey:
      queryId === null
        ? labelsKeys.rows(0, "null", resultKey)
        : labelsKeys.rows(queryId, rowIdentitiesCacheKey, resultKey),
    enabled,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<LabelsByRowResponse> => {
      const chunks =
        normalizedRowIdentities.length > PARALLEL_LABEL_FETCH_THRESHOLD
          ? chunkRowIdentities(normalizedRowIdentities)
          : [normalizedRowIdentities];
      const responses = await Promise.all(chunks.map((chunk) => fetchLabelsChunk(queryId!, chunk)));

      return {
        labels_by_row: mergeLabelResponses(responses),
      };
    },
  });

  useEffect(() => {
    setActiveQuery(queryId, resultKey);
  }, [queryId, resultKey, setActiveQuery]);

  useEffect(() => {
    if (!enabled) {
      if (queryId === null) {
        setLabels({});
      }
      return;
    }
    if (query.data !== undefined) {
      setLabelsForQuery(queryId, resultKey, query.data.labels_by_row);
    }
  }, [enabled, query.data, queryId, resultKey, setLabels, setLabelsForQuery]);

  return query;
}

export function useUpsertLabel(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: async (args: UpsertLabelMutationArgs): Promise<LabelRecordRead | null> => {
      if (!activeLabelContextMatches(queryId, args.resultKey)) {
        return null;
      }

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
        .markPendingLabelForQuery(
          queryId,
          args.resultKey,
          args.rowIdentity,
          args.fieldKey,
        );
      const snapshot = getLabelSnapshot(
        queryId,
        args.resultKey,
        args.rowIdentity,
        args.fieldKey,
      );
      applyOptimisticLabel(
        queryId,
        args.resultKey,
        args.rowIdentity,
        args.fieldKey,
        args.value,
      );
      return snapshot;
    },
    onError: (error, _args, snapshot) => {
      if (snapshot !== undefined) {
        restoreLabelSnapshot(snapshot);
      }
      if (isLabelFieldNotFound(error)) {
        toast.error("LABEL_FIELD_NOT_FOUND: 打标字段已变更，已重新拉取 schema");
        void queryClient.invalidateQueries({ queryKey: labelSchemaKey(queryId) });
        return;
      }
      toast.error(formatApiError(error));
    },
    onSuccess: (record, args, snapshot) => {
      const resultKey = snapshot?.resultKey ?? args.resultKey;
      if (record === null) {
        useLabelsStore
          .getState()
          .removeLabelForQuery(queryId, resultKey, args.rowIdentity, args.fieldKey);
        return;
      }
      useLabelsStore
        .getState()
        .patchLabelForQuery(
          queryId,
          resultKey,
          record.row_identity,
          record.field_key,
          record.value,
        );
    },
    onSettled: async (_data, _error, args, snapshot) => {
      const resultKey = snapshot?.resultKey ?? args.resultKey;
      useLabelsStore
        .getState()
        .clearPendingLabelForQuery(queryId, resultKey, args.rowIdentity, args.fieldKey);
      if (activeLabelContextMatches(queryId, resultKey)) {
        await queryClient.invalidateQueries({ queryKey: labelsKeys.query(queryId) });
      }
    },
  });
}

export function useQueuedUpsertLabel(queryId: number, resultKey: string | null) {
  const upsert = useUpsertLabel(queryId);
  const { isPending, mutateAsync } = upsert;

  const commitLabel = useCallback(
    (args: UpsertLabelArgs): Promise<void> => {
      const queueKey = getCellMutationQueueKey(
        queryId,
        resultKey,
        args.rowIdentity,
        args.fieldKey,
      );
      const previous = labelMutationQueues.get(queueKey) ?? Promise.resolve();
      const next = previous
        .catch(() => undefined)
        .then(() =>
          mutateAsync({ ...args, resultKey }).then(
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
    [mutateAsync, queryId, resultKey],
  );

  return {
    commitLabel,
    isPending,
  };
}

function getCellMutationQueueKey(
  queryId: number,
  resultKey: string | null,
  rowIdentity: string,
  fieldKey: string,
): string {
  return [queryId, resultKey ?? "", rowIdentity, fieldKey].join(
    CELL_MUTATION_KEY_SEPARATOR,
  );
}

export function useBatchUpsertLabels(queryId: number, resultKey: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: async (args: BatchUpsertLabelArgs): Promise<LabelBatchResult> => {
      if (!activeLabelContextMatches(queryId, resultKey)) {
        return {
          affected: 0,
          skipped: args.rowIdentities.length,
          errors: [],
        };
      }

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
      const snapshots = args.rowIdentities.map((rowIdentity) =>
        getLabelSnapshot(queryId, resultKey, rowIdentity, args.fieldKey),
      );
      const labelsStore = useLabelsStore.getState();
      labelsStore.markPendingLabelsForQuery(
        queryId,
        resultKey,
        args.rowIdentities,
        args.fieldKey,
      );
      labelsStore.patchLabelsForQuery(
        queryId,
        resultKey,
        args.rowIdentities,
        args.fieldKey,
        args.value,
      );
      return snapshots;
    },
    onError: (error, _args, snapshots) => {
      if (snapshots !== undefined) {
        restoreActiveQueryLabelSnapshots(snapshots);
      }
      toast.error(formatApiError(error));
    },
    onSuccess: (result, _args, snapshots) => {
      const errors = result.errors ?? [];
      toast.success(`已应用到 ${result.affected} 行`);
      if (errors.length > 0) {
        if (snapshots !== undefined) {
          const failedRows = new Set(errors.map((item) => item.row_identity));
          restoreActiveQueryLabelSnapshots(
            snapshots.filter((snapshot) => failedRows.has(snapshot.rowIdentity)),
          );
        }
        toast.warning(`${errors.length} 行失败`);
        if (errors.some((error) => error.code === "LABEL_FIELD_NOT_FOUND")) {
          toast.error("LABEL_FIELD_NOT_FOUND: 打标字段已变更，已重新拉取 schema");
          void queryClient.invalidateQueries({ queryKey: labelSchemaKey(queryId) });
        }
      }
    },
    onSettled: async (_data, _error, args, snapshots) => {
      const settledResultKey = snapshots?.[0]?.resultKey ?? resultKey;
      useLabelsStore
        .getState()
        .clearPendingLabelsForQuery(
          queryId,
          settledResultKey,
          args.rowIdentities,
          args.fieldKey,
        );
      if (activeLabelContextMatches(queryId, settledResultKey)) {
        await queryClient.invalidateQueries({ queryKey: labelsKeys.query(queryId) });
      }
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

async function fetchLabelsChunk(
  queryId: number,
  rowIdentities: string[],
): Promise<LabelsByRowResponse> {
  const { data, error, response } = await apiClient.POST(
    "/queries/{query_id}/labels/query",
    {
      params: { path: { query_id: queryId } },
      body: { row_identities: rowIdentities },
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load labels with status ${response.status}`);
  }

  return data;
}

function mergeLabelResponses(responses: LabelsByRowResponse[]): LabelsByRow {
  const merged: LabelsByRow = {};
  for (const item of responses) {
    Object.assign(merged, item.labels_by_row);
  }
  return merged;
}

function getRowIdentitiesCacheKey(rowIdentities: string[]): string {
  if (rowIdentities.length === 0) {
    return "0";
  }

  let hash = 2166136261;
  for (const rowIdentity of rowIdentities) {
    for (let index = 0; index < rowIdentity.length; index += 1) {
      hash ^= rowIdentity.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
  }

  return [
    rowIdentities.length,
    rowIdentities[0],
    rowIdentities[rowIdentities.length - 1],
    (hash >>> 0).toString(36),
  ].join(":");
}

function getLabelSnapshot(
  queryId: number,
  resultKey: string | null,
  rowIdentity: string,
  fieldKey: string,
): LabelSnapshot {
  const state = useLabelsStore.getState();
  const rowLabels =
    state.activeQueryId === queryId && state.activeResultKey === resultKey
      ? state.labelsByRow[rowIdentity]
      : undefined;
  return {
    queryId,
    resultKey,
    rowIdentity,
    fieldKey,
    hadPreviousValue: rowLabels !== undefined && fieldKey in rowLabels,
    previousValue: rowLabels?.[fieldKey],
  };
}

function applyOptimisticLabel(
  queryId: number,
  resultKey: string | null,
  rowIdentity: string,
  fieldKey: string,
  value: LabelValue,
) {
  if (value === null) {
    useLabelsStore.getState().removeLabelForQuery(queryId, resultKey, rowIdentity, fieldKey);
    return;
  }
  useLabelsStore
    .getState()
    .patchLabelForQuery(queryId, resultKey, rowIdentity, fieldKey, value);
}

function restoreLabelSnapshot(snapshot: LabelSnapshot) {
  if (snapshot.hadPreviousValue) {
    useLabelsStore
      .getState()
      .patchLabelForQuery(
        snapshot.queryId,
        snapshot.resultKey,
        snapshot.rowIdentity,
        snapshot.fieldKey,
        snapshot.previousValue,
      );
    return;
  }
  useLabelsStore
    .getState()
    .removeLabelForQuery(
      snapshot.queryId,
      snapshot.resultKey,
      snapshot.rowIdentity,
      snapshot.fieldKey,
    );
}

function restoreActiveQueryLabelSnapshots(snapshots: LabelSnapshot[]) {
  for (const snapshot of snapshots) {
    const state = useLabelsStore.getState();
    if (
      state.activeQueryId === snapshot.queryId &&
      state.activeResultKey === snapshot.resultKey
    ) {
      restoreLabelSnapshot(snapshot);
    }
  }
}

function activeLabelContextMatches(queryId: number, resultKey: string | null): boolean {
  const state = useLabelsStore.getState();
  return state.activeQueryId === queryId && state.activeResultKey === resultKey;
}

function isLabelFieldNotFound(error: unknown): boolean {
  return getApiError(error)?.error.code === "LABEL_FIELD_NOT_FOUND";
}
