import { apiClient } from "@/api/client";
import type {
  Annotation,
  AnnotationClearFilters,
  AnnotationCreate,
  AnnotationFilters,
} from "@/api/types";

export async function listAnnotations(
  queryId: number,
  filters?: AnnotationFilters,
): Promise<Annotation[]> {
  const { data, error, response } = await apiClient.GET(
    "/queries/{query_id}/annotations",
    {
      params: {
        path: { query_id: queryId },
        query: filters,
      },
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to load annotations with status ${response.status}`);
  }

  return data;
}

export async function createAnnotation(
  queryId: number,
  payload: AnnotationCreate,
): Promise<Annotation> {
  const { data, error, response } = await apiClient.POST(
    "/queries/{query_id}/annotations",
    {
      params: { path: { query_id: queryId } },
      body: payload,
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to create annotation with status ${response.status}`);
  }

  return data;
}

export async function deleteAnnotation(
  queryId: number,
  annotationId: number,
): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    "/queries/{query_id}/annotations/{annotation_id}",
    {
      params: { path: { query_id: queryId, annotation_id: annotationId } },
    },
  );

  if (error !== undefined) {
    throw { error, response };
  }
  if (!response.ok) {
    throw new Error(`Failed to delete annotation with status ${response.status}`);
  }
}

export async function clearAnnotations(
  queryId: number,
  filters: AnnotationClearFilters,
): Promise<{ deleted: number }> {
  const { data, error, response } = await apiClient.DELETE(
    "/queries/{query_id}/annotations",
    {
      params: {
        path: { query_id: queryId },
        query: filters,
      },
    },
  );

  if (error !== undefined) {
    throw { data, error, response };
  }
  if (!response.ok || data === undefined) {
    throw new Error(`Failed to clear annotations with status ${response.status}`);
  }

  return { deleted: data.deleted_count };
}
