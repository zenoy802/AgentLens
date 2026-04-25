import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type {
  ConnectionCreate,
  ConnectionListResponse,
  ConnectionRead,
  ConnectionUpdate,
} from "@/api/types";

export type { ConnectionCreate, ConnectionListResponse, ConnectionRead, ConnectionUpdate };

const CONNECTION_PAGE_SIZE = 100;

export const connectionKeys = {
  all: ["connections"] as const,
  list: () => ["connections", "list"] as const,
  detail: (id: number) => ["connections", "detail", id] as const,
};

export function useConnections() {
  return useQuery({
    queryKey: connectionKeys.list(),
    queryFn: fetchAllConnections,
  });
}

async function fetchAllConnections(): Promise<ConnectionListResponse> {
  const firstPage = await fetchConnectionPage(1);
  const items = [...firstPage.items];

  for (let page = 2; page <= firstPage.pagination.total_pages; page += 1) {
    const nextPage = await fetchConnectionPage(page);
    items.push(...nextPage.items);
  }

  return {
    items,
    pagination: {
      ...firstPage.pagination,
      page: 1,
      page_size: CONNECTION_PAGE_SIZE,
      total: items.length,
      total_pages: 1,
    },
  };
}

async function fetchConnectionPage(page: number): Promise<ConnectionListResponse> {
  const { data, error, response } = await apiClient.GET("/connections", {
    params: { query: { page, page_size: CONNECTION_PAGE_SIZE } },
  });

  if (error !== undefined) {
    throw error;
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load connections with status ${response.status}`);
  }

  return data;
}

export function useConnection(id: number) {
  return useQuery({
    queryKey: connectionKeys.detail(id),
    enabled: Number.isFinite(id) && id > 0,
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/connections/{connection_id}", {
        params: { path: { connection_id: id } },
      });
      if (error !== undefined) {
        throw error;
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load connection with status ${response.status}`);
      }
      return data;
    },
  });
}

export function useCreateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ConnectionCreate) => {
      const { data, error, response } = await apiClient.POST("/connections", { body: payload });
      if (error !== undefined) {
        throw error;
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to create connection with status ${response.status}`);
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: connectionKeys.all });
    },
  });
}

export function useUpdateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: ConnectionUpdate }) => {
      const { data, error, response } = await apiClient.PATCH("/connections/{connection_id}", {
        params: { path: { connection_id: id } },
        body: payload,
      });
      if (error !== undefined) {
        throw error;
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to update connection with status ${response.status}`);
      }
      return data;
    },
    onSuccess: async (data) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: connectionKeys.all }),
        queryClient.invalidateQueries({ queryKey: connectionKeys.detail(data.id) }),
      ]);
    },
  });
}

export function useDeleteConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { error, response } = await apiClient.DELETE("/connections/{connection_id}", {
        params: { path: { connection_id: id } },
      });
      if (error !== undefined) {
        throw error;
      }
      if (!response.ok) {
        throw new Error(`Failed to delete connection with status ${response.status}`);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: connectionKeys.all });
    },
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: async (id: number) => {
      const { data, error, response } = await apiClient.POST("/connections/{connection_id}/test", {
        params: { path: { connection_id: id } },
      });
      if (error !== undefined) {
        throw error;
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to test connection with status ${response.status}`);
      }
      return data;
    },
  });
}
