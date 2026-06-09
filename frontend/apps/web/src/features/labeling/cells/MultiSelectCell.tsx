import { useEffect, useMemo, useRef, useState } from "react";
import { Check, X } from "lucide-react";

import { useQueuedUpsertLabel } from "@/api/hooks/useLabels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  coerceStringArrayValue,
  getLabelOptions,
  getOptionByValue,
  useCloseOnRowTableScroll,
  type MultiSelectLabelField,
} from "@/features/labeling/cells/utils";

type MultiSelectCellProps = {
  queryId: number;
  resultKey: string | null;
  field: MultiSelectLabelField;
  rowId: string;
  value: unknown;
};

export function MultiSelectCell({
  queryId,
  resultKey,
  field,
  rowId,
  value,
}: MultiSelectCellProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const { commitLabel } = useQueuedUpsertLabel(queryId, resultKey);
  const options = getLabelOptions(field);
  const selectedValues = useMemo(() => coerceStringArrayValue(value), [value]);
  const [draftValues, setDraftValues] = useState<string[]>(selectedValues);

  useCloseOnRowTableScroll(open, setOpen, triggerRef);

  useEffect(() => {
    if (open) {
      setDraftValues(selectedValues);
    }
  }, [open, selectedValues]);

  function commit(nextValues: string[]) {
    void commitLabel({
      rowIdentity: rowId,
      fieldKey: field.key,
      value: nextValues.length === 0 ? null : nextValues,
    });
  }

  function toggleValue(optionValue: string) {
    setDraftValues((current) => {
      const selected = current.includes(optionValue);
      const nextValues = selected
        ? current.filter((item) => item !== optionValue)
        : [...current, optionValue];
      commit(nextValues);
      return nextValues;
    });
  }

  const visibleBadges = selectedValues.slice(0, 2);
  const overflowCount = selectedValues.length - visibleBadges.length;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          ref={triggerRef}
          type="button"
          data-row-click-stop
          className={cn(
            "flex h-full min-w-0 flex-1 items-center rounded px-1 text-left",
            "hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          )}
        >
          {selectedValues.length === 0 ? (
            <span className="text-xs text-muted-foreground">未标</span>
          ) : (
            <span className="flex min-w-0 items-center gap-1">
              {visibleBadges.map((item) => {
                const option = getOptionByValue(options, item);
                return (
                  <OptionBadge
                    key={item}
                    label={option?.label ?? item}
                    color={option?.color ?? null}
                  />
                );
              })}
              {overflowCount > 0 ? (
                <Badge variant="muted" className="shrink-0 px-1.5">
                  +{overflowCount}
                </Badge>
              ) : null}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60" onClick={(event) => event.stopPropagation()}>
        <div className="max-h-72 overflow-y-auto">
          {options.map((option) => {
            const checked = draftValues.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                role="checkbox"
                aria-checked={checked}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                onClick={() => toggleValue(option.value)}
              >
                <span
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                    checked ? "border-primary bg-primary text-primary-foreground" : "bg-background",
                  )}
                  aria-hidden="true"
                >
                  {checked ? <Check className="h-3 w-3" aria-hidden="true" /> : null}
                </span>
                <ColorDot color={option.color ?? null} />
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-1 flex items-center justify-between gap-2 border-t pt-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => {
              setDraftValues([]);
              commit([]);
            }}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            清除
          </button>
          <Button size="sm" className="h-7 px-2" onClick={() => setOpen(false)}>
            完成
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function OptionBadge({ label, color }: { label: string; color: string | null }) {
  return (
    <Badge
      variant="outline"
      className="max-w-[7rem] gap-1.5 truncate px-1.5"
      title={label}
    >
      <ColorDot color={color} />
      <span className="truncate">{label}</span>
    </Badge>
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
