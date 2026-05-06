import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { queryKeys } from "@/api/hooks/useQueries";
import type { LabelField, LabelSchemaRead } from "@/api/types";
import { formatApiError } from "@/lib/formatApiError";

export const labelSchemaKey = (queryId: number) => ["label-schema", queryId] as const;

export function useLabelSchema(queryId: number | null) {
  return useQuery({
    queryKey: queryId === null ? ["label-schema", "null"] : labelSchemaKey(queryId),
    enabled: queryId !== null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<LabelSchemaRead> => {
      const { data, error, response } = await apiClient.GET("/queries/{query_id}/label-schema", {
        params: { path: { query_id: queryId! } },
      });

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load label schema with status ${response.status}`);
      }

      return data;
    },
  });
}

type SaveLabelSchemaArgs = {
  queryId: number;
  fields: LabelField[];
};

export function useSaveLabelSchema() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ queryId, fields }: SaveLabelSchemaArgs): Promise<LabelSchemaRead> => {
      const { data, error, response } = await apiClient.PUT(
        "/queries/{query_id}/label-schema",
        {
          params: { path: { query_id: queryId } },
          body: { fields },
        },
      );

      if (error !== undefined) {
        throw { data, error, response };
      }
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to save label schema with status ${response.status}`);
      }

      return data;
    },
    onSuccess: async (data, { queryId }) => {
      queryClient.setQueryData(labelSchemaKey(queryId), data);
      if (data.cascade_deleted_records > 0) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.all });
      }
    },
    onError: (err) => {
      toast.error(formatApiError(err));
    },
  });
}
