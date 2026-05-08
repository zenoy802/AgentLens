import { useLabelSchema } from "@/api/hooks/useLabelSchema";
import type { Column, FieldRender, LabelField, Row } from "@/api/types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { LabelCell } from "@/features/labeling/cells/LabelCell";
import { CellDispatcher } from "@/features/row-view/cells/CellDispatcher";
import { getRowIdentityValue } from "@/features/row-view/rowIdentity";
import { useLabelsStore } from "@/stores/labelsStore";
import { useQueryStore } from "@/stores/queryStore";

interface RowDetailSheetProps {
  open: boolean;
  queryId: number | null;
  resultKey: string | null;
  row: Row | null;
  rowId: string | null;
  columns: Column[];
  rowNumber: number | null;
  onOpenChange: (open: boolean) => void;
}

export function RowDetailSheet({
  open,
  queryId,
  resultKey,
  row,
  rowId,
  columns,
  rowNumber,
  onOpenChange,
}: RowDetailSheetProps) {
  const fieldRenders = useQueryStore((state) => state.fieldRenders);
  const labelSchema = useLabelSchema(open ? queryId : null);
  const labelFields = labelSchema.data?.fields ?? [];

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
            <LabelSection
              queryId={queryId}
              resultKey={resultKey}
              rowId={rowId}
              fields={labelFields}
            />
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

function LabelSection({
  queryId,
  resultKey,
  rowId,
  fields,
}: {
  queryId: number | null;
  resultKey: string | null;
  rowId: string | null;
  fields: LabelField[];
}) {
  if (queryId === null || rowId === null) {
    return null;
  }

  return (
    <section className="space-y-3 rounded-lg border bg-card p-4">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          打标
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          Row Identity: {rowId}
        </div>
      </div>
      {fields.length === 0 ? (
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          暂无打标字段。
        </div>
      ) : (
        <div className="space-y-2">
          {fields.map((field) => (
            <RowLabelEditor
              key={field.key}
              queryId={queryId}
              resultKey={resultKey}
              rowId={rowId}
              field={field}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function RowLabelEditor({
  queryId,
  resultKey,
  rowId,
  field,
}: {
  queryId: number;
  resultKey: string | null;
  rowId: string;
  field: LabelField;
}) {
  const value = useLabelsStore((state) => state.labelsByRow[rowId]?.[field.key]);

  return (
    <div className="grid gap-2 rounded-md border bg-background p-3 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-center">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium" title={field.label}>
          {field.label}
        </div>
        <div className="truncate text-xs text-muted-foreground" title={field.key}>
          {field.key}
        </div>
      </div>
      <div className="flex min-h-9 min-w-0 rounded-md border bg-muted/20 p-1">
        <LabelCell
          queryId={queryId}
          resultKey={resultKey}
          field={field}
          rowId={rowId}
          value={value}
        />
      </div>
    </div>
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
