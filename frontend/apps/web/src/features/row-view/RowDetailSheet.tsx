import type { Column, FieldRender, Row } from "@/api/types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { CellDispatcher } from "@/features/row-view/cells/CellDispatcher";
import { getRowIdentityValue } from "@/features/row-view/rowIdentity";
import { useQueryStore } from "@/stores/queryStore";

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
  const fieldRenders = useQueryStore((state) => state.fieldRenders);

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
              <FieldValue
                key={column.name}
                label={column.name}
                value={row[column.name]}
                render={fieldRenders[column.name] ?? getDefaultRender(row[column.name])}
              />
            ))}
            <FieldValue
              label="Row Identity"
              value={getRowIdentityValue(row, columns)}
              render={{ type: "text" }}
            />
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function FieldValue({
  label,
  value,
  render,
}: {
  label: string;
  value: unknown;
  render: FieldRender;
}) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="h-px bg-border" />
      <div className="min-w-0 rounded-md bg-muted/40 p-3 text-sm text-foreground">
        <CellDispatcher value={value} render={render} presentation="detail" />
      </div>
    </div>
  );
}

function getDefaultRender(value: unknown): FieldRender {
  return typeof value === "object" && value !== null ? { type: "json", collapsed: false } : { type: "text" };
}
