import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { QueryHistoryListResponse, QueryHistoryRead } from "@/api/types";

export type { QueryHistoryListResponse, QueryHistoryRead };

export type QueryHistoryParams = {
  connection_id?: number;
  page?: number;
  page_size?: number;
  limit?: number;
};

export const queryHistoryKeys = {
  all: ["query-history"] as const,
  list: (params: QueryHistoryParams) => ["query-history", "list", params] as const,
};

export function useQueryHistory(params: QueryHistoryParams = {}) {
  return useQuery({
    queryKey: queryHistoryKeys.list(params),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/query-history", {
        params: {
          query: {
            connection_id: params.connection_id,
            page: params.page,
            page_size: params.page_size,
            limit: params.limit,
          },
        },
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load query history with status ${response.status}`);
      }

      return data;
    },
  });
}
