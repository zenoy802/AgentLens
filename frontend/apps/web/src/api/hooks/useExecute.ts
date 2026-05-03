import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import type { ExecuteRequest, ExecutionResult, QueryExecuteRequest } from "@/api/types";
import { queryHistoryKeys } from "@/api/hooks/useQueryHistory";
import { queryKeys } from "@/api/hooks/useQueries";
import { formatApiError } from "@/lib/formatApiError";

export type { ExecuteRequest, ExecutionResult, QueryExecuteRequest };

interface ExecuteSavedQueryArgs {
  queryId: number;
  payload?: QueryExecuteRequest;
}

export function useExecute() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: ExecuteRequest): Promise<ExecutionResult> => {
      const { data, error, response } = await apiClient.POST("/execute", { body });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`执行失败，HTTP ${response.status}`);
      }

      return data as ExecutionResult;
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryHistoryKeys.all }),
      ]);
    },
    onError: (err) => toast.error(formatApiError(err)),
  });
}

export function useExecuteQuery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      queryId,
      payload = {},
    }: ExecuteSavedQueryArgs): Promise<ExecutionResult> => {
      const { data, error, response } = await apiClient.POST("/queries/{query_id}/execute", {
        params: { path: { query_id: queryId } },
        body: payload,
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`执行失败，HTTP ${response.status}`);
      }

      return data as ExecutionResult;
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.detail(result.query_id) }),
        queryClient.invalidateQueries({ queryKey: queryHistoryKeys.all }),
      ]);
    },
    onError: (err) => toast.error(formatApiError(err)),
  });
}
