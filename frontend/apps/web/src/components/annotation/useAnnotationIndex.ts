import { useMemo } from "react";

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
  staleIds: ReadonlySet<number>;
  orphanIds: ReadonlySet<number>;
  unknownColumnIds: ReadonlySet<number>;
  staleAnnotations: Annotation[];
  orphanAnnotations: Annotation[];
  unknownColumnAnnotations: Annotation[];

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

const EMPTY_ROW_VISUAL_STATE: RowAnnotationVisualState = {
  annotations: EMPTY_ANNOTATIONS,
  count: 0,
  colors: [],
  segments: [],
  hasStale: false,
  hasOrphan: false,
};

const EMPTY_CELL_VISUAL_STATE: CellAnnotationVisualState = {
  annotations: EMPTY_ANNOTATIONS,
  count: 0,
  color: null,
  hasStale: false,
  hasOrphan: false,
};

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
    const rowVisualStates = new Map<string, RowAnnotationVisualState>();
    const cellVisualStates = new Map<string, CellAnnotationVisualState>();
    const staleIds = new Set<number>();
    const orphanIds = new Set<number>();
    const unknownColumnIds = new Set<number>();
    const byAuthor: Record<string, number> = {};
    const staleAnnotations: Annotation[] = [];
    const orphanAnnotations: Annotation[] = [];
    const unknownColumnAnnotations: Annotation[] = [];

    for (const annotation of annotations) {
      byAuthor[annotation.author] = (byAuthor[annotation.author] ?? 0) + 1;

      const isOrphan =
        rowIdentitySet !== null && !rowIdentitySet.has(annotation.row_identity);
      if (isOrphan) {
        orphanIds.add(annotation.id);
        orphanAnnotations.push(annotation);
      }

      const isStale =
        annotation.result_fingerprint !== null &&
        annotation.result_fingerprint.length > 0 &&
        currentFingerprints?.result !== undefined &&
        currentFingerprints.result.length > 0 &&
        annotation.result_fingerprint !== currentFingerprints.result;
      if (isStale) {
        staleIds.add(annotation.id);
        staleAnnotations.push(annotation);
      }

      if (annotation.column_key === null) {
        const existing = rowAnnotations.get(annotation.row_identity) ?? [];
        existing.push(annotation);
        rowAnnotations.set(annotation.row_identity, existing);
      } else {
        const isUnknownColumn =
          columnKeySet !== null && !columnKeySet.has(annotation.column_key);
        if (isUnknownColumn) {
          unknownColumnIds.add(annotation.id);
          unknownColumnAnnotations.push(annotation);
        }
        const key = getCellKey(annotation.row_identity, annotation.column_key);
        const existing = cellAnnotations.get(key) ?? [];
        existing.push(annotation);
        cellAnnotations.set(key, existing);
      }
    }

    for (const [rowIdentity, items] of rowAnnotations.entries()) {
      rowVisualStates.set(rowIdentity, {
        annotations: items,
        count: items.length,
        colors: getUniqueColors(items),
        segments: getAuthorSegmentColors(items),
        hasStale: items.some((annotation) => staleIds.has(annotation.id)),
        hasOrphan: items.some((annotation) => orphanIds.has(annotation.id)),
      });
    }

    for (const [cellKey, items] of cellAnnotations.entries()) {
      cellVisualStates.set(cellKey, {
        annotations: items,
        count: items.length,
        color: items[0]?.color ?? null,
        hasStale: items.some((annotation) => staleIds.has(annotation.id)),
        hasOrphan: items.some((annotation) => orphanIds.has(annotation.id)),
      });
    }

    return {
      byAuthor,
      cellAnnotations,
      cellVisualStates,
      orphanIds,
      orphanAnnotations,
      rowAnnotations,
      rowVisualStates,
      staleIds,
      staleAnnotations,
      unknownColumnIds,
      unknownColumnAnnotations,
    };
  }, [annotations, columnKeySet, currentFingerprints?.result, rowIdentitySet]);

  return useMemo(
    () => ({
      annotations,
      totalCount: annotations.length,
      byAuthor: index.byAuthor,
      staleIds: index.staleIds,
      orphanIds: index.orphanIds,
      unknownColumnIds: index.unknownColumnIds,
      staleAnnotations: index.staleAnnotations,
      orphanAnnotations: index.orphanAnnotations,
      unknownColumnAnnotations: index.unknownColumnAnnotations,
      getRowAnnotations: (rowIdentity: string) =>
        index.rowAnnotations.get(rowIdentity) ?? EMPTY_ANNOTATIONS,
      getCellAnnotations: (rowIdentity: string, columnKey: string) =>
        index.cellAnnotations.get(getCellKey(rowIdentity, columnKey)) ?? EMPTY_ANNOTATIONS,
      getRowVisualState: (rowIdentity: string) =>
        index.rowVisualStates.get(rowIdentity) ?? EMPTY_ROW_VISUAL_STATE,
      getCellVisualState: (rowIdentity: string, columnKey: string) =>
        index.cellVisualStates.get(getCellKey(rowIdentity, columnKey)) ??
        EMPTY_CELL_VISUAL_STATE,
      getStaleAnnotations: () => index.staleAnnotations,
      getOrphanAnnotations: () => index.orphanAnnotations,
      getUnknownColumnAnnotations: () => index.unknownColumnAnnotations,
    }),
    [annotations, index],
  );
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
