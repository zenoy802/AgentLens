import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types.gen";
import { queryHistoryKeys } from "@/api/hooks/useQueryHistory";
import { queryKeys } from "@/api/hooks/useQueries";
import { formatApiError } from "@/lib/formatApiError";

export type ExecuteRequest = components["schemas"]["ExecuteRequest"];
export type ExecutionResult = components["schemas"]["ExecutionResult"];

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

      return data;
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
