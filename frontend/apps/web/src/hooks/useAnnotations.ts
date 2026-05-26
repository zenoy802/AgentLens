import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearAnnotations,
  createAnnotation,
  deleteAnnotation,
  listAnnotations,
} from "@/api/annotations";
import type {
  AnnotationClearFilters,
  AnnotationCreate,
  AnnotationFilters,
} from "@/api/types";
import { locallyHandledMutationMeta } from "@/api/mutationMeta";

export const annotationKeys = {
  all: ["annotations"] as const,
  query: (queryId: number) => [...annotationKeys.all, queryId] as const,
  list: (queryId: number, filters?: AnnotationFilters) =>
    [...annotationKeys.query(queryId), filters ?? {}] as const,
};

export function useAnnotations(
  queryId: number | null,
  filters?: AnnotationFilters,
) {
  return useQuery({
    queryKey:
      queryId === null
        ? annotationKeys.list(0, filters)
        : annotationKeys.list(queryId, filters),
    enabled: queryId !== null,
    queryFn: () => listAnnotations(queryId!, filters),
    staleTime: 5_000,
    refetchOnWindowFocus: false,
  });
}

export function useCreateAnnotation(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: (payload: AnnotationCreate) => createAnnotation(queryId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: annotationKeys.query(queryId) });
    },
  });
}

export function useDeleteAnnotation(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: (annotationId: number) => deleteAnnotation(queryId, annotationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: annotationKeys.query(queryId) });
    },
  });
}

export function useClearAnnotations(queryId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: locallyHandledMutationMeta,
    mutationFn: (filters: AnnotationClearFilters) => clearAnnotations(queryId, filters),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: annotationKeys.query(queryId) });
    },
  });
}
