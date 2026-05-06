import { useRef, useState } from "react";
import { Check, X } from "lucide-react";

import { useQueuedUpsertLabel } from "@/api/hooks/useLabels";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  coerceStringValue,
  getLabelOptions,
  getOptionByValue,
  useCloseOnRowTableScroll,
  type SingleSelectLabelField,
} from "@/features/labeling/cells/utils";

type SingleSelectCellProps = {
  queryId: number;
  field: SingleSelectLabelField;
  rowId: string;
  value: unknown;
};

export function SingleSelectCell({ queryId, field, rowId, value }: SingleSelectCellProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const { commitLabel } = useQueuedUpsertLabel(queryId);
  const options = getLabelOptions(field);
  const selectedValue = coerceStringValue(value);
  const selectedOption =
    selectedValue === null ? undefined : getOptionByValue(options, selectedValue);

  useCloseOnRowTableScroll(open, setOpen, triggerRef);

  function save(nextValue: string | null) {
    void commitLabel({
      rowIdentity: rowId,
      fieldKey: field.key,
      value: nextValue,
    });
    setOpen(false);
  }

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
          {selectedOption === undefined ? (
            <span className="text-xs text-muted-foreground">未标</span>
          ) : (
            <OptionBadge label={selectedOption.label} color={selectedOption.color ?? null} />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-52" onClick={(event) => event.stopPropagation()}>
        <div className="max-h-72 overflow-y-auto">
          {options.map((option) => {
            const selected = option.value === selectedValue;
            return (
              <button
                key={option.value}
                type="button"
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                onClick={() => save(option.value)}
              >
                <ColorDot color={option.color ?? null} />
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {selected ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : null}
              </button>
            );
          })}
        </div>
        <div className="mt-1 border-t pt-1">
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => save(null)}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            清除
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function OptionBadge({ label, color }: { label: string; color: string | null }) {
  return (
    <Badge
      variant="outline"
      className="max-w-full gap-1.5 truncate px-1.5"
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
