import { useMemo } from "react";
import {
  useMutation,
  useQuery,
  useQueries as useTanstackQueries,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type {
  NamedQueryListResponse,
  NamedQueryPromote,
  NamedQueryRead,
  NamedQueryUpdate,
} from "@/api/types";

export type {
  NamedQueryListResponse,
  NamedQueryPromote,
  NamedQueryRead,
  NamedQueryUpdate,
};

export type QueryListParams = {
  connection_id?: number;
  is_named?: boolean;
  search?: string;
  include_expired?: boolean;
  order_by?: "created_at" | "last_executed_at";
  page?: number;
  page_size?: number;
};

export const queryKeys = {
  all: ["queries"] as const,
  list: (params: QueryListParams) => ["queries", "list", params] as const,
  detail: (id: number) => ["queries", "detail", id] as const,
};

export function useQueries(params: QueryListParams = {}) {
  return useQuery({
    queryKey: queryKeys.list(params),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/queries", {
        params: {
          query: {
            connection_id: params.connection_id,
            is_named: params.is_named,
            search: params.search,
            include_expired: params.include_expired,
            order_by: params.order_by,
            page: params.page,
            page_size: params.page_size,
          },
        },
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load queries with status ${response.status}`);
      }

      return data;
    },
  });
}

export function useQueryById(id: number) {
  return useQuery({
    queryKey: queryKeys.detail(id),
    enabled: Number.isFinite(id) && id > 0,
    queryFn: () => fetchQueryById(id),
  });
}

export const useQuery_Q = useQueryById;

export type QueryDetailState = {
  data: NamedQueryRead | undefined;
  isError: boolean;
  isLoading: boolean;
};

export function useQueryDetailsByIds(ids: number[]): Map<number, QueryDetailState> {
  const uniqueIds = useMemo(() => {
    return [...new Set(ids.filter((id) => Number.isFinite(id) && id > 0))].sort(
      (left, right) => left - right,
    );
  }, [ids]);

  const results = useTanstackQueries({
    queries: uniqueIds.map((id) => ({
      queryKey: queryKeys.detail(id),
      queryFn: () => fetchQueryById(id),
    })),
  });

  return useMemo(() => {
    return new Map(
      uniqueIds.map((id, index) => {
        const result = results[index];
        return [
          id,
          {
            data: result?.data,
            isError: result?.isError ?? false,
            isLoading: result?.isLoading ?? true,
          },
        ];
      }),
    );
  }, [results, uniqueIds]);
}

async function fetchQueryById(id: number): Promise<NamedQueryRead> {
  const { data, error, response } = await apiClient.GET("/queries/{query_id}", {
    params: { path: { query_id: id } },
  });

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load query with status ${response.status}`);
  }

  return data;
}

export function useDeleteQuery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      const { error, response } = await apiClient.DELETE("/queries/{query_id}", {
        params: { path: { query_id: id } },
      });

      if (error !== undefined) {
        throw { error, response };
      }
      if (!response.ok) {
        throw new Error(`Failed to delete query with status ${response.status}`);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.all });
    },
  });
}

export function useUpdateQuery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: { id: number; payload: NamedQueryUpdate }) => {
      const { data, error, response } = await apiClient.PATCH("/queries/{query_id}", {
        params: { path: { query_id: variables.id } },
        body: variables.payload,
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to update query with status ${response.status}`);
      }

      return data;
    },
    onSuccess: async (query) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.detail(query.id) }),
      ]);
    },
  });
}

export function usePromoteQuery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: { id: number; payload: NamedQueryPromote }) => {
      const { data, error, response } = await apiClient.POST("/queries/{query_id}/promote", {
        params: { path: { query_id: variables.id } },
        body: variables.payload,
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to promote query with status ${response.status}`);
      }

      return data;
    },
    onSuccess: async (query) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.detail(query.id) }),
      ]);
    },
  });
}
