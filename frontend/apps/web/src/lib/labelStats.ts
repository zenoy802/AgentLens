import type { LabelField, LabelOption, LabelSchemaRead } from "@/api/types";

export type LabelSchema = Pick<LabelSchemaRead, "fields">;

export type LabelStats = {
  [fieldKey: string]: {
    field: LabelField;
    total: number;
    labeled: number;
    distribution: Array<{ option: LabelOption | null; count: number }>;
  };
};

type LabelsByRow = Record<string, Record<string, unknown>>;

export function computeStats(
  schema: LabelSchema,
  labelsByRow: LabelsByRow,
  rowIds: string[],
): LabelStats {
  const total = rowIds.length;
  const stats: LabelStats = {};

  for (const field of schema.fields) {
    if (field.type === "single_select") {
      const { distribution, labeled } = computeSingleSelectStats(
        field,
        labelsByRow,
        rowIds,
      );
      stats[field.key] = { field, total, labeled, distribution };
      continue;
    }

    if (field.type === "multi_select") {
      const { distribution, labeled } = computeMultiSelectStats(
        field,
        labelsByRow,
        rowIds,
      );
      stats[field.key] = { field, total, labeled, distribution };
      continue;
    }

    const labeled = rowIds.filter((rowId) =>
      textLabelIsFilled(labelsByRow[rowId]?.[field.key]),
    ).length;
    stats[field.key] = {
      field,
      total,
      labeled,
      distribution: [{ option: null, count: total - labeled }],
    };
  }

  return stats;
}

export function labelValueMatchesSelectedOptions(
  field: LabelField,
  value: unknown,
  selectedValues: string[],
): boolean {
  if (selectedValues.length === 0 || field.type === "text") {
    return true;
  }

  if (field.type === "single_select") {
    return typeof value === "string" && selectedValues.includes(value);
  }

  if (!Array.isArray(value)) {
    return false;
  }

  return value.some(
    (item) => typeof item === "string" && selectedValues.includes(item),
  );
}

function computeSingleSelectStats(
  field: Extract<LabelField, { type: "single_select" }>,
  labelsByRow: LabelsByRow,
  rowIds: string[],
): {
  labeled: number;
  distribution: Array<{ option: LabelOption | null; count: number }>;
} {
  const options = field.options ?? [];
  const countsByValue = new Map(options.map((option) => [option.value, 0]));
  let labeled = 0;

  for (const rowId of rowIds) {
    const value = labelsByRow[rowId]?.[field.key];
    if (typeof value !== "string" || !countsByValue.has(value)) {
      continue;
    }

    countsByValue.set(value, (countsByValue.get(value) ?? 0) + 1);
    labeled += 1;
  }

  return {
    labeled,
    distribution: [
      ...options.map((option) => ({
        option,
        count: countsByValue.get(option.value) ?? 0,
      })),
      { option: null, count: rowIds.length - labeled },
    ],
  };
}

function computeMultiSelectStats(
  field: Extract<LabelField, { type: "multi_select" }>,
  labelsByRow: LabelsByRow,
  rowIds: string[],
): {
  labeled: number;
  distribution: Array<{ option: LabelOption | null; count: number }>;
} {
  const options = field.options ?? [];
  const optionValues = new Set(options.map((option) => option.value));
  const countsByValue = new Map(options.map((option) => [option.value, 0]));
  let labeled = 0;

  for (const rowId of rowIds) {
    const value = labelsByRow[rowId]?.[field.key];
    if (!Array.isArray(value)) {
      continue;
    }

    const selectedValues = new Set(
      value.filter((item): item is string => typeof item === "string"),
    );
    let rowHasKnownOption = false;
    for (const selectedValue of selectedValues) {
      if (!optionValues.has(selectedValue)) {
        continue;
      }
      countsByValue.set(
        selectedValue,
        (countsByValue.get(selectedValue) ?? 0) + 1,
      );
      rowHasKnownOption = true;
    }

    if (rowHasKnownOption) {
      labeled += 1;
    }
  }

  return {
    labeled,
    distribution: [
      ...options.map((option) => ({
        option,
        count: countsByValue.get(option.value) ?? 0,
      })),
      { option: null, count: rowIds.length - labeled },
    ],
  };
}

function textLabelIsFilled(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}
