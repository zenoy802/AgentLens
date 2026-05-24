import { getLineClampStyle } from "@/features/row-view/cells/cellUtils";

export function TextCell({ value, previewLines = 1 }: { value: unknown; previewLines?: number }) {
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
