import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { RenderRuleCreate, RenderRuleRead, RenderRuleUpdate } from "@/api/types";

export type { RenderRuleCreate, RenderRuleRead, RenderRuleUpdate };

export const renderRuleKeys = {
  all: ["render-rules"] as const,
  list: () => ["render-rules", "list"] as const,
  detail: (id: number) => ["render-rules", "detail", id] as const,
};

export function useRenderRules() {
  return useQuery({
    queryKey: renderRuleKeys.list(),
    queryFn: fetchRenderRules,
  });
}

async function fetchRenderRules(): Promise<RenderRuleRead[]> {
  const { data, error, response } = await apiClient.GET("/render-rules");

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load render rules with status ${response.status}`);
  }

  return data;
}

export function useCreateRenderRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RenderRuleCreate) => {
      const { data, error, response } = await apiClient.POST("/render-rules", {
        body: payload,
      });
      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to create render rule with status ${response.status}`);
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: renderRuleKeys.all });
    },
  });
}

export function useUpdateRenderRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: RenderRuleUpdate }) => {
      const { data, error, response } = await apiClient.PATCH("/render-rules/{rule_id}", {
        params: { path: { rule_id: id } },
        body: payload,
      });
      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to update render rule with status ${response.status}`);
      }
      return data;
    },
    onSuccess: async (data) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: renderRuleKeys.all }),
        queryClient.invalidateQueries({ queryKey: renderRuleKeys.detail(data.id) }),
      ]);
    },
  });
}

export function useDeleteRenderRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { error, response } = await apiClient.DELETE("/render-rules/{rule_id}", {
        params: { path: { rule_id: id } },
      });
      if (error !== undefined) {
        throw { error, response };
      }
      if (!response.ok) {
        throw new Error(`Failed to delete render rule with status ${response.status}`);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: renderRuleKeys.all });
    },
  });
}
