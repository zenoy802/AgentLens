import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type {
  RunSnapshotCreate,
  RunSnapshotRead,
  TraceContractCreate,
  TraceContractValidateRequest,
} from "@/api/types";
import { locallyHandledMutationMeta } from "@/api/mutationMeta";

export type ContractListParams = {
  named_query_id?: number;
  include_archived?: boolean;
  cursor?: string;
  limit?: number;
};

export type SnapshotListParams = {
  status?: RunSnapshotRead["status"];
  trace_contract_id?: string;
  cursor?: string;
  limit?: number;
};

export const traceContractKeys = {
  all: ["trace-contracts"] as const,
  list: (params: ContractListParams) => ["trace-contracts", "list", params] as const,
  detail: (id: string) => ["trace-contracts", "detail", id] as const,
};

export const snapshotKeys = {
  all: ["run-snapshots"] as const,
  list: (params: SnapshotListParams) => ["run-snapshots", "list", params] as const,
  detail: (id: string) => ["run-snapshots", "detail", id] as const,
};

export function snapshotPollingInterval(
  status: RunSnapshotRead["status"] | undefined,
): number | false {
  return status === "building" ? 1_500 : false;
}

export function useTraceContracts(params: ContractListParams = {}) {
  return useQuery({
    queryKey: traceContractKeys.list(params),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/trace-contracts", {
        params: { query: params },
      });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load trace contracts: HTTP ${response.status}`);
      }
      return data;
    },
  });
}

export function useTraceContract(id: string) {
  return useQuery({
    queryKey: traceContractKeys.detail(id),
    enabled: id.length > 0,
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/trace-contracts/{contract_id}",
        { params: { path: { contract_id: id } } },
      );
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load trace contract: HTTP ${response.status}`);
      }
      return data;
    },
  });
}

export function useValidateTraceContract() {
  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: async (body: TraceContractValidateRequest) => {
      const { data, error, response } = await apiClient.POST("/trace-contracts/validate", {
        body,
      });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Trace contract validation failed: HTTP ${response.status}`);
      }
      return data;
    },
  });
}

export function useCreateTraceContract() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: async (body: TraceContractCreate) => {
      const { data, error, response } = await apiClient.POST("/trace-contracts", { body });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Trace contract create failed: HTTP ${response.status}`);
      }
      return data;
    },
    onSuccess: async (contract) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: traceContractKeys.all }),
        queryClient.setQueryData(traceContractKeys.detail(contract.id), contract),
      ]);
    },
  });
}

export function useRunSnapshots(params: SnapshotListParams = {}) {
  return useQuery({
    queryKey: snapshotKeys.list(params),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/run-snapshots", {
        params: { query: params },
      });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load snapshots: HTTP ${response.status}`);
      }
      return data;
    },
    refetchInterval: (query) => {
      const hasBuilding = query.state.data?.items.some((item) => item.status === "building");
      return hasBuilding === true ? 1_500 : false;
    },
    refetchIntervalInBackground: false,
  });
}

export function useRunSnapshot(id: string, enabled = true) {
  return useQuery({
    queryKey: snapshotKeys.detail(id),
    enabled: enabled && id.length > 0,
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/run-snapshots/{snapshot_id}", {
        params: { path: { snapshot_id: id } },
      });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Failed to load snapshot: HTTP ${response.status}`);
      }
      return data;
    },
    refetchInterval: (query) => snapshotPollingInterval(query.state.data?.status),
    refetchIntervalInBackground: false,
  });
}

export function useCreateRunSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: async (body: RunSnapshotCreate) => {
      const { data, error, response } = await apiClient.POST("/run-snapshots", { body });
      if (error !== undefined) throw { data, error, response };
      if (!response.ok || data === undefined) {
        throw new Error(`Snapshot create failed: HTTP ${response.status}`);
      }
      return data;
    },
    onSuccess: async (snapshot) => {
      queryClient.setQueryData(snapshotKeys.detail(snapshot.id), snapshot);
      await queryClient.invalidateQueries({ queryKey: snapshotKeys.all });
    },
  });
}
