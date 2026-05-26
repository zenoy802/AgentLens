import { memo } from "react";

import { getLineClampStyle } from "@/features/row-view/cells/cellUtils";

interface TextCellProps {
  value: unknown;
  previewLines?: number;
}

function TextCellComponent({ value, previewLines = 1 }: TextCellProps) {
  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  const str = formatTextValue(value);
  return (
    <div className="min-w-0" title={str} style={getLineClampStyle(previewLines)}>
      {str}
    </div>
  );
}

export const TextCell = memo(
  TextCellComponent,
  (prev, next) => Object.is(prev.value, next.value) && prev.previewLines === next.previewLines,
);

function formatTextValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }

  try {
    const serialized = JSON.stringify(value);
    if (serialized !== undefined) {
      return serialized;
    }
  } catch {
    // Fall back to String(value) for cyclic or otherwise non-JSON objects.
  }
  return String(value);
}
