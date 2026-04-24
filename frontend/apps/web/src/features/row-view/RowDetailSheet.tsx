import type { Column, Row } from "@/api/types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { getRowIdentityValue } from "@/features/row-view/rowIdentity";

interface RowDetailSheetProps {
  open: boolean;
  row: Row | null;
  columns: Column[];
  rowNumber: number | null;
  onOpenChange: (open: boolean) => void;
}

export function RowDetailSheet({
  open,
  row,
  columns,
  rowNumber,
  onOpenChange,
}: RowDetailSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="border-b pb-4">
          <SheetTitle>行详情{rowNumber !== null ? ` (#${rowNumber})` : ""}</SheetTitle>
          <SheetDescription className="sr-only">
            当前结果行的完整字段和值。
          </SheetDescription>
        </SheetHeader>

        {row !== null ? (
          <div className="space-y-6 py-6">
            {columns.map((column) => (
              <FieldValue key={column.name} label={column.name} value={row[column.name]} />
            ))}
            <FieldValue label="Row Identity" value={getRowIdentityValue(row, columns)} />
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function FieldValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="h-px bg-border" />
      <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 font-mono text-xs leading-relaxed text-foreground">
        {formatDetailValue(value)}
      </pre>
    </div>
  );
}

function formatDetailValue(value: unknown): string {
  if (value == null) {
    return "NULL";
  }

  if (typeof value === "object") {
    try {
      const json = JSON.stringify(value, bigintReplacer, 2);
      return json ?? safeString(value);
    } catch {
      return safeString(value);
    }
  }

  return safeString(value);
}

function bigintReplacer(_key: string, value: unknown): unknown {
  return typeof value === "bigint" ? value.toString() : value;
}

function safeString(value: unknown): string {
  try {
    return String(value);
  } catch {
    return "[unserializable value]";
  }
}
