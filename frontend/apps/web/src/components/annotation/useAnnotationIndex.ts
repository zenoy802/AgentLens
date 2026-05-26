import { useCallback, useMemo } from "react";

import type {
  Annotation,
  AnnotationColor,
  Column,
  QueryFingerprints,
  Row as RowData,
} from "@/api/types";
import { getRowIdentityValue } from "@/features/row-view/rowIdentity";
import { useAnnotations } from "@/hooks/useAnnotations";

const PRIMARY_ROW_IDENTITY_KEY = "_row_identity";
const FALLBACK_ROW_IDENTITY_KEY = "_agent_lens_row_identity";
const EMPTY_ANNOTATIONS: Annotation[] = [];

export interface RowAnnotationVisualState {
  annotations: Annotation[];
  count: number;
  colors: AnnotationColor[];
  segments: AnnotationColor[];
  hasStale: boolean;
  hasOrphan: boolean;
}

export interface CellAnnotationVisualState {
  annotations: Annotation[];
  count: number;
  color: AnnotationColor | null;
  hasStale: boolean;
  hasOrphan: boolean;
}

export interface AnnotationIndex {
  annotations: Annotation[];
  totalCount: number;
  byAuthor: Record<string, number>;

  getRowAnnotations(rowIdentity: string): Annotation[];
  getCellAnnotations(rowIdentity: string, columnKey: string): Annotation[];

  getRowVisualState(rowIdentity: string): RowAnnotationVisualState;
  getCellVisualState(
    rowIdentity: string,
    columnKey: string,
  ): CellAnnotationVisualState;

  getStaleAnnotations(): Annotation[];
  getOrphanAnnotations(): Annotation[];
  getUnknownColumnAnnotations(): Annotation[];
}

export function useAnnotationIndex(
  queryId: number | null,
  rows: RowData[],
  currentFingerprints?: QueryFingerprints | null,
  columns?: Column[],
): AnnotationIndex {
  const annotationsQuery = useAnnotations(queryId);
  const annotations = annotationsQuery.data ?? EMPTY_ANNOTATIONS;
  const resultSchemaLoaded = columns !== undefined && columns.length > 0;

  const rowIdentitySet = useMemo(() => {
    if (!resultSchemaLoaded) {
      return null;
    }
    const rowIdentities = new Set<string>();
    for (const row of rows) {
      const rowIdentity = getExistingRowIdentity(row, columns);
      if (rowIdentity !== null) {
        rowIdentities.add(rowIdentity);
      }
    }
    return rowIdentities;
  }, [columns, resultSchemaLoaded, rows]);
  const columnKeySet = useMemo(
    () =>
      !resultSchemaLoaded
        ? null
        : new Set(columns.map((column) => column.name)),
    [columns, resultSchemaLoaded],
  );

  const index = useMemo(() => {
    const rowAnnotations = new Map<string, Annotation[]>();
    const cellAnnotations = new Map<string, Annotation[]>();
    const staleIds = new Set<number>();
    const orphanIds = new Set<number>();
    const unknownColumnIds = new Set<number>();
    const byAuthor: Record<string, number> = {};

    for (const annotation of annotations) {
      byAuthor[annotation.author] = (byAuthor[annotation.author] ?? 0) + 1;

      if (rowIdentitySet !== null && !rowIdentitySet.has(annotation.row_identity)) {
        orphanIds.add(annotation.id);
      }

      if (
        annotation.result_fingerprint !== null &&
        annotation.result_fingerprint.length > 0 &&
        currentFingerprints?.result !== undefined &&
        currentFingerprints.result.length > 0 &&
        annotation.result_fingerprint !== currentFingerprints.result
      ) {
        staleIds.add(annotation.id);
      }

      if (annotation.column_key === null) {
        const existing = rowAnnotations.get(annotation.row_identity) ?? [];
        existing.push(annotation);
        rowAnnotations.set(annotation.row_identity, existing);
      } else {
        if (columnKeySet !== null && !columnKeySet.has(annotation.column_key)) {
          unknownColumnIds.add(annotation.id);
        }
        const key = getCellKey(annotation.row_identity, annotation.column_key);
        const existing = cellAnnotations.get(key) ?? [];
        existing.push(annotation);
        cellAnnotations.set(key, existing);
      }
    }

    return {
      byAuthor,
      cellAnnotations,
      orphanIds,
      rowAnnotations,
      staleIds,
      unknownColumnIds,
    };
  }, [annotations, columnKeySet, currentFingerprints?.result, rowIdentitySet]);

  const getRowAnnotations = useCallback(
    (rowIdentity: string) => index.rowAnnotations.get(rowIdentity) ?? EMPTY_ANNOTATIONS,
    [index.rowAnnotations],
  );

  const getCellAnnotations = useCallback(
    (rowIdentity: string, columnKey: string) =>
      index.cellAnnotations.get(getCellKey(rowIdentity, columnKey)) ?? EMPTY_ANNOTATIONS,
    [index.cellAnnotations],
  );

  const getRowVisualState = useCallback(
    (rowIdentity: string): RowAnnotationVisualState => {
      const rowAnnotations = getRowAnnotations(rowIdentity);
      const colors = getUniqueColors(rowAnnotations);
      return {
        annotations: rowAnnotations,
        count: rowAnnotations.length,
        colors,
        segments: getAuthorSegmentColors(rowAnnotations),
        hasStale: rowAnnotations.some((annotation) => index.staleIds.has(annotation.id)),
        hasOrphan: rowAnnotations.some((annotation) => index.orphanIds.has(annotation.id)),
      };
    },
    [getRowAnnotations, index.orphanIds, index.staleIds],
  );

  const getCellVisualState = useCallback(
    (rowIdentity: string, columnKey: string): CellAnnotationVisualState => {
      const cellAnnotations = getCellAnnotations(rowIdentity, columnKey);
      return {
        annotations: cellAnnotations,
        count: cellAnnotations.length,
        color: cellAnnotations[0]?.color ?? null,
        hasStale: cellAnnotations.some((annotation) => index.staleIds.has(annotation.id)),
        hasOrphan: cellAnnotations.some((annotation) => index.orphanIds.has(annotation.id)),
      };
    },
    [getCellAnnotations, index.orphanIds, index.staleIds],
  );

  const getStaleAnnotations = useCallback(
    () => annotations.filter((annotation) => index.staleIds.has(annotation.id)),
    [annotations, index.staleIds],
  );

  const getOrphanAnnotations = useCallback(
    () => annotations.filter((annotation) => index.orphanIds.has(annotation.id)),
    [annotations, index.orphanIds],
  );
  const getUnknownColumnAnnotations = useCallback(
    () => annotations.filter((annotation) => index.unknownColumnIds.has(annotation.id)),
    [annotations, index.unknownColumnIds],
  );

  return {
    annotations,
    totalCount: annotations.length,
    byAuthor: index.byAuthor,
    getRowAnnotations,
    getCellAnnotations,
    getRowVisualState,
    getCellVisualState,
    getStaleAnnotations,
    getOrphanAnnotations,
    getUnknownColumnAnnotations,
  };
}

function getExistingRowIdentity(row: RowData, columns?: Column[]): string | null {
  if (columns !== undefined) {
    const value = getRowIdentityValue(row, columns);
    return value == null ? null : String(value);
  }

  const fallbackKey = Object.keys(row)
    .filter(
      (key) =>
        key === FALLBACK_ROW_IDENTITY_KEY ||
        key.startsWith(`${FALLBACK_ROW_IDENTITY_KEY}_`),
    )
    .sort(compareFallbackIdentityKeys)
    .at(0);
  if (fallbackKey !== undefined) {
    const value = row[fallbackKey];
    if (value != null) {
      return String(value);
    }
  }

  const primary = row[PRIMARY_ROW_IDENTITY_KEY];
  if (primary != null) {
    return String(primary);
  }

  return null;
}

function compareFallbackIdentityKeys(left: string, right: string): number {
  return getFallbackIdentityRank(right) - getFallbackIdentityRank(left);
}

function getFallbackIdentityRank(key: string): number {
  if (key === FALLBACK_ROW_IDENTITY_KEY) {
    return 1;
  }
  const suffix = key.slice(FALLBACK_ROW_IDENTITY_KEY.length + 1);
  const parsed = Number.parseInt(suffix, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getCellKey(rowIdentity: string, columnKey: string): string {
  return `${rowIdentity}\u001f${columnKey}`;
}

function getUniqueColors(annotations: Annotation[]): AnnotationColor[] {
  return Array.from(new Set(annotations.map((annotation) => annotation.color)));
}

function getAuthorSegmentColors(annotations: Annotation[]): AnnotationColor[] {
  const colorsByAuthor = new Map<string, AnnotationColor>();
  for (const annotation of annotations) {
    if (!colorsByAuthor.has(annotation.author)) {
      colorsByAuthor.set(annotation.author, annotation.color);
    }
  }

  const colors = Array.from(colorsByAuthor.values());
  if (colors.length <= 5) {
    return colors;
  }
  return [...colors.slice(0, 4), "gray"];
}
