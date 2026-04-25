import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import type { ViewConfigPayload, ViewConfigRead } from "@/api/types";
import { formatApiError } from "@/lib/formatApiError";

export const viewConfigKey = (queryId: number) => ["view-config", queryId] as const;

export function useViewConfig(queryId: number | null) {
  return useQuery({
    queryKey: queryId === null ? ["view-config", "null"] : viewConfigKey(queryId),
    enabled: queryId !== null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<ViewConfigRead> => {
      const { data, error, response } = await apiClient.GET("/queries/{query_id}/view-config", {
        params: { path: { query_id: queryId! } },
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load view config with status ${response.status}`);
      }

      return data;
    },
  });
}

interface SaveViewConfigArgs {
  queryId: number;
  payload: ViewConfigPayload;
}

const pendingViewConfigSaves = new Map<number, Promise<void>>();

export async function waitForPendingViewConfigSave(queryId: number): Promise<void> {
  await pendingViewConfigSaves.get(queryId);
}

export function useSaveViewConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ queryId, payload }: SaveViewConfigArgs): Promise<ViewConfigRead> => {
      return enqueueViewConfigSave(queryId, async () => {
        const { data, error, response } = await apiClient.PUT("/queries/{query_id}/view-config", {
          params: { path: { query_id: queryId } },
          body: payload,
        });

        if (error !== undefined) {
          throw { data, error, response };
        }
        if (!response.ok || data === undefined) {
          throw new Error(`Failed to save view config with status ${response.status}`);
        }

        return data;
      });
    },
    onSuccess: (data, { queryId }) => {
      queryClient.setQueryData(viewConfigKey(queryId), data);
    },
    onError: (err) => {
      toast.error(formatApiError(err));
    },
  });
}

async function enqueueViewConfigSave<T>(queryId: number, task: () => Promise<T>): Promise<T> {
  const previous = pendingViewConfigSaves.get(queryId) ?? Promise.resolve();
  const queued = previous.catch(() => undefined).then(task);
  const settled = queued.then(
    () => undefined,
    () => undefined,
  );

  pendingViewConfigSaves.set(queryId, settled);
  try {
    return await queued;
  } finally {
    if (pendingViewConfigSaves.get(queryId) === settled) {
      pendingViewConfigSaves.delete(queryId);
    }
  }
}
