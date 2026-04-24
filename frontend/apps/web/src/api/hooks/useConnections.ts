import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { ConnectionListResponse, ConnectionRead } from "@/api/types";

export type { ConnectionListResponse, ConnectionRead };

const CONNECTION_PAGE_SIZE = 100;

export function useConnections() {
  return useQuery({
    queryKey: ["connections", "list"],
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
    throw new Error(`Failed to load connections: ${JSON.stringify(error)}`);
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load connections with status ${response.status}`);
  }

  return data;
}
