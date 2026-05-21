import { apiClient } from "@/api/client";
import type {
  SelectionSnapshot,
  SelectionSnapshotCreate,
} from "@/api/types";

export async function createSelectionSnapshot(
  queryId: number,
  payload: SelectionSnapshotCreate,
): Promise<SelectionSnapshot> {
  const { data, error, response } = await apiClient.POST(
    "/queries/{query_id}/selection-snapshots",
    {
      params: { path: { query_id: queryId } },
      body: payload,
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(
      `Failed to create selection snapshot with status ${response.status}`,
    );
  }

  return data;
}

export async function getSelectionSnapshot(
  selectionId: string,
): Promise<SelectionSnapshot> {
  const { data, error, response } = await apiClient.GET(
    "/selections/{selection_id}",
    {
      params: { path: { selection_id: selectionId } },
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load selection snapshot with status ${response.status}`);
  }

  return data;
}
