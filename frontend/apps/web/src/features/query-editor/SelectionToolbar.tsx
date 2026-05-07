import { useMemo, useState } from "react";
import { Bot, ChevronDown, Tag, X } from "lucide-react";

import type { LabelField } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { BatchLabelDialog } from "@/features/labeling/BatchLabelDialog";
import { useQueryStore } from "@/stores/queryStore";

interface SelectionToolbarProps {
  queryId: number | null;
  labelFields: LabelField[];
  filteredSelectedCount: number;
}

export function SelectionToolbar({
  queryId,
  labelFields,
  filteredSelectedCount,
}: SelectionToolbarProps) {
  const selectedRowIds = useQueryStore((state) => state.selectedRowIds);
  const clearSelection = useQueryStore((state) => state.clearSelection);
  const [batchField, setBatchField] = useState<LabelField | null>(null);
  const selectedRowIdentities = useMemo(
    () => Array.from(selectedRowIds),
    [selectedRowIds],
  );
  const selectedCount = selectedRowIdentities.length;

  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-b bg-primary/5 px-3 py-2">
      <div className="text-sm font-medium text-foreground">
        已选 {selectedCount} 行
        {filteredSelectedCount !== selectedCount ? (
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            当前筛选内 {filteredSelectedCount} 行
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 bg-background"
              disabled={queryId === null || labelFields.length === 0}
            >
              <Tag className="h-3.5 w-3.5" aria-hidden="true" />
              批量打标
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>选择字段</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {labelFields.map((field) => (
              <DropdownMenuItem
                key={field.key}
                className="gap-2"
                onSelect={() => setBatchField(field)}
              >
                <Tag className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate" title={field.label}>
                  {field.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  {getFieldTypeLabel(field)}
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="outline" size="sm" className="gap-1.5 bg-background" disabled>
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          用 LLM 分析
        </Button>
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={clearSelection}>
          <X className="h-3.5 w-3.5" aria-hidden="true" />
          取消选择
        </Button>
      </div>

      {queryId !== null && batchField !== null ? (
        <BatchLabelDialog
          open={batchField !== null}
          queryId={queryId}
          field={batchField}
          rowIdentities={selectedRowIdentities}
          onOpenChange={(open) => {
            if (!open) {
              setBatchField(null);
            }
          }}
        />
      ) : null}
    </div>
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
