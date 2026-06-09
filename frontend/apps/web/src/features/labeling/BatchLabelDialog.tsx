import { useEffect, useMemo, useState } from "react";
import { Check, X } from "lucide-react";

import { useBatchUpsertLabels } from "@/api/hooks/useLabels";
import type { LabelField } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  getLabelOptions,
  type MultiSelectLabelField,
  type SingleSelectLabelField,
} from "@/features/labeling/cells/utils";

type LabelValue = string | string[] | null;

interface BatchLabelDialogProps {
  open: boolean;
  queryId: number;
  resultKey: string | null;
  field: LabelField;
  rowIdentities: string[];
  onOpenChange(open: boolean): void;
}

export function BatchLabelDialog({
  open,
  queryId,
  resultKey,
  field,
  rowIdentities,
  onOpenChange,
}: BatchLabelDialogProps) {
  const batchUpsertLabels = useBatchUpsertLabels(queryId, resultKey);
  const [singleValue, setSingleValue] = useState<string | null | undefined>(undefined);
  const [multiValues, setMultiValues] = useState<string[] | null>(null);
  const [textValue, setTextValue] = useState("");
  const [textTouched, setTextTouched] = useState(false);
  const [textCleared, setTextCleared] = useState(false);
  const selectedCount = rowIdentities.length;

  useEffect(() => {
    if (!open) {
      return;
    }
    setSingleValue(undefined);
    setMultiValues(null);
    setTextValue("");
    setTextTouched(false);
    setTextCleared(false);
  }, [field.key, open]);

  const hasExplicitValue = useMemo(() => {
    if (field.type === "single_select") {
      return singleValue !== undefined;
    }
    if (field.type === "multi_select") {
      return multiValues !== null;
    }
    return textTouched || textCleared;
  }, [field.type, multiValues, singleValue, textCleared, textTouched]);

  const submitValue = useMemo<LabelValue>(() => {
    if (field.type === "single_select") {
      return singleValue ?? null;
    }
    if (field.type === "multi_select") {
      return multiValues === null || multiValues.length === 0 ? null : multiValues;
    }
    return textCleared ? null : textValue;
  }, [field.type, multiValues, singleValue, textCleared, textValue]);

  function handleApply() {
    if (selectedCount === 0 || !hasExplicitValue || batchUpsertLabels.isPending) {
      return;
    }

    batchUpsertLabels.mutate(
      {
        rowIdentities,
        fieldKey: field.key,
        value: submitValue,
      },
      {
        onSuccess: () => onOpenChange(false),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>批量打标</DialogTitle>
          <DialogDescription>
            字段：{field.label}（{getFieldTypeLabel(field)}）
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="text-sm text-muted-foreground">
            将对 {selectedCount} 行统一设置为：
          </div>
          {field.type === "single_select" ? (
            <SingleSelectBatchEditor
              field={field}
              value={singleValue}
              onChange={setSingleValue}
            />
          ) : field.type === "multi_select" ? (
            <MultiSelectBatchEditor
              field={field}
              values={multiValues ?? []}
              clearSelected={multiValues !== null && multiValues.length === 0}
              onChange={setMultiValues}
            />
          ) : (
            <TextBatchEditor
              value={textValue}
              cleared={textCleared}
              onChange={(nextValue) => {
                setTextValue(nextValue);
                setTextTouched(true);
                setTextCleared(false);
              }}
              onClear={() => {
                setTextValue("");
                setTextTouched(false);
                setTextCleared(true);
              }}
            />
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            disabled={batchUpsertLabels.isPending}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            disabled={selectedCount === 0 || !hasExplicitValue || batchUpsertLabels.isPending}
            onClick={handleApply}
          >
            {batchUpsertLabels.isPending ? "应用中..." : "应用"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SingleSelectBatchEditor({
  field,
  value,
  onChange,
}: {
  field: SingleSelectLabelField;
  value: string | null | undefined;
  onChange(value: string | null): void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={`设置 ${field.label}`}>
      {getLabelOptions(field).map((option) => (
        <OptionButton
          key={option.value}
          selectionRole="radio"
          selected={value === option.value}
          label={option.label}
          color={option.color ?? null}
          onClick={() => onChange(option.value)}
        />
      ))}
      <ClearButton
        selected={value === null}
        selectionRole="radio"
        onClick={() => onChange(null)}
      />
    </div>
  );
}

function MultiSelectBatchEditor({
  field,
  values,
  clearSelected,
  onChange,
}: {
  field: MultiSelectLabelField;
  values: string[];
  clearSelected: boolean;
  onChange(values: string[]): void;
}) {
  function toggleValue(value: string) {
    onChange(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={`设置 ${field.label}`}>
      {getLabelOptions(field).map((option) => (
        <OptionButton
          key={option.value}
          selectionRole="checkbox"
          selected={values.includes(option.value)}
          label={option.label}
          color={option.color ?? null}
          onClick={() => toggleValue(option.value)}
        />
      ))}
      <ClearButton selected={clearSelected} onClick={() => onChange([])} />
    </div>
  );
}

function TextBatchEditor({
  value,
  cleared,
  onChange,
  onClear,
}: {
  value: string;
  cleared: boolean;
  onChange(value: string): void;
  onClear(): void;
}) {
  return (
    <div className="space-y-2">
      <textarea
        aria-label="批量文本标签"
        className={cn(
          "min-h-28 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm shadow-sm",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        )}
        value={value}
        placeholder={cleared ? "将清除所选行的此字段" : "输入要统一写入的文本"}
        onChange={(event) => onChange(event.target.value)}
      />
      <Button
        variant="outline"
        size="sm"
        className={cn("gap-1.5", cleared && "border-primary text-primary")}
        onClick={onClear}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
        清除
      </Button>
    </div>
  );
}

function OptionButton({
  selectionRole,
  selected,
  label,
  color,
  onClick,
}: {
  selectionRole: "radio" | "checkbox";
  selected: boolean;
  label: string;
  color: string | null;
  onClick(): void;
}) {
  return (
    <button
      type="button"
      role={selectionRole}
      aria-checked={selected}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm",
        "hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        selected && "border-primary bg-primary/10 text-primary",
      )}
      onClick={onClick}
    >
      <ColorDot color={color} />
      <span className="min-w-0 max-w-48 truncate">{label}</span>
      {selected ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : null}
    </button>
  );
}

function ClearButton({
  selected,
  selectionRole,
  onClick,
}: {
  selected: boolean;
  selectionRole?: "radio";
  onClick(): void;
}) {
  return (
    <button
      type="button"
      role={selectionRole}
      aria-checked={selectionRole === undefined ? undefined : selected}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm text-muted-foreground",
        "hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        selected && "border-primary bg-primary/10 text-primary",
      )}
      onClick={onClick}
    >
      <X className="h-3.5 w-3.5" aria-hidden="true" />
      清除
    </button>
  );
}

function ColorDot({ color }: { color: string | null }) {
  return (
    <span
      className="h-2 w-2 shrink-0 rounded-full border border-border"
      style={color === null ? undefined : { backgroundColor: color, borderColor: color }}
      aria-hidden="true"
    />
  );
}

function getFieldTypeLabel(field: LabelField): string {
  if (field.type === "single_select") {
    return "单选";
  }
  if (field.type === "multi_select") {
    return "多选";
  }
  return "文本";
}
