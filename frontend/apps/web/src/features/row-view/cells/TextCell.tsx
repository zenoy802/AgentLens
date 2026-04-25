import { getLineClampStyle } from "@/features/row-view/cells/cellUtils";

export function TextCell({ value, previewLines = 1 }: { value: unknown; previewLines?: number }) {
  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  const str = String(value);
  return (
    <div className="min-w-0" title={str} style={getLineClampStyle(previewLines)}>
      {str}
    </div>
  );
}
