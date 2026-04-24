import type { Column, Row } from "@/api/types";

const PRIMARY_ROW_IDENTITY_KEY = "_row_identity";
const FALLBACK_ROW_IDENTITY_KEY = "_agent_lens_row_identity";

export function getRowIdentityKey(columns: Column[]): string {
  const columnNames = new Set(columns.map((column) => column.name));

  if (!columnNames.has(PRIMARY_ROW_IDENTITY_KEY)) {
    return PRIMARY_ROW_IDENTITY_KEY;
  }

  if (!columnNames.has(FALLBACK_ROW_IDENTITY_KEY)) {
    return FALLBACK_ROW_IDENTITY_KEY;
  }

  for (let suffix = 2; suffix < Number.MAX_SAFE_INTEGER; suffix += 1) {
    const candidate = `${FALLBACK_ROW_IDENTITY_KEY}_${suffix}`;
    if (!columnNames.has(candidate)) {
      return candidate;
    }
  }

  return FALLBACK_ROW_IDENTITY_KEY;
}

export function getRowIdentityValue(row: Row, columns: Column[]): unknown {
  return row[getRowIdentityKey(columns)];
}

export function getStableRowIdentity(row: Row, columns: Column[], index: number): string {
  const value = getRowIdentityValue(row, columns);
  if (value == null) {
    return `row-${index + 1}`;
  }

  try {
    return String(value);
  } catch {
    return `row-${index + 1}`;
  }
}
