import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import type {
  TrajectoryAggregateResponse,
  TrajectoryConfig,
} from "@/api/types";
import { formatApiError } from "@/lib/formatApiError";

export interface UseTrajectoriesOptions {
  useSavedConfig?: boolean;
  config?: TrajectoryConfig;
}

export function useTrajectories(queryId: number, options?: UseTrajectoriesOptions) {
  return useMutation({
    mutationFn: async (
      override?: UseTrajectoriesOptions,
    ): Promise<TrajectoryAggregateResponse> => {
      const activeOptions = override ?? options ?? {};
      const useSavedConfig = activeOptions.useSavedConfig ?? true;
      const { data, error, response } = await apiClient.POST(
        "/queries/{query_id}/trajectories",
        {
          params: { path: { query_id: queryId } },
          body: {
            use_saved_config: useSavedConfig,
            trajectory_config: activeOptions.config ?? null,
          },
        },
      );

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Trajectory 聚合失败，HTTP ${response.status}`);
      }

      return data as TrajectoryAggregateResponse;
    },
    onError: (err) => toast.error(formatApiError(err)),
  });
}
