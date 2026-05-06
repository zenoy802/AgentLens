import { memo } from "react";

import type { LabelField } from "@/api/types";
import { MultiSelectCell } from "@/features/labeling/cells/MultiSelectCell";
import { SingleSelectCell } from "@/features/labeling/cells/SingleSelectCell";
import { TextLabelCell } from "@/features/labeling/cells/TextLabelCell";
import { labelFieldsEqual, labelValuesEqual } from "@/features/labeling/cells/utils";

type LabelCellProps = {
  queryId: number;
  field: LabelField;
  rowId: string;
  value: unknown;
};

function LabelCellComponent({ queryId, field, rowId, value }: LabelCellProps) {
  if (field.type === "single_select") {
    return <SingleSelectCell queryId={queryId} field={field} rowId={rowId} value={value} />;
  }
  if (field.type === "multi_select") {
    return <MultiSelectCell queryId={queryId} field={field} rowId={rowId} value={value} />;
  }
  return <TextLabelCell queryId={queryId} field={field} rowId={rowId} value={value} />;
}

export const LabelCell = memo(
  LabelCellComponent,
  (prev, next) =>
    prev.queryId === next.queryId &&
    labelFieldsEqual(prev.field, next.field) &&
    prev.rowId === next.rowId &&
    labelValuesEqual(prev.value, next.value),
);
