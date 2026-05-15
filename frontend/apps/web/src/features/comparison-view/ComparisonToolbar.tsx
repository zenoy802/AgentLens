import {
  CheckSquare,
  Download,
  Pin,
  RefreshCw,
} from "lucide-react";
import { useMemo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

interface ComparisonToolbarProps {
  allKeys: string[];
  selectedKeys: string[];
  selectedMessageCount: number;
  syncScroll: boolean;
  maxSelection: number;
  trailingAction?: ReactNode;
  onSelectionChange: (keys: string[]) => void;
  onSyncScrollChange: (enabled: boolean) => void;
  onExportComparison: () => void;
}

export function ComparisonToolbar({
  allKeys,
  selectedKeys,
  selectedMessageCount,
  syncScroll,
  maxSelection,
  trailingAction,
  onSelectionChange,
  onSyncScrollChange,
  onExportComparison,
}: ComparisonToolbarProps) {
  const selectedKeySet = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const selectedCount = allKeys.filter((key) => selectedKeySet.has(key)).length;

  function selectAll() {
    onSelectionChange(allKeys.slice(0, maxSelection));
  }

  function invertSelection() {
    onSelectionChange(
      allKeys.filter((key) => !selectedKeySet.has(key)).slice(0, maxSelection),
    );
  }

  return (
    <div className="flex min-h-11 flex-wrap items-center gap-2 rounded-lg border bg-background px-3 py-2">
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={allKeys.length === 0}
        title={`最多选择 ${maxSelection} 条 trajectory`}
        onClick={selectAll}
      >
        <CheckSquare className="h-3.5 w-3.5" aria-hidden="true" />
        全选
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={allKeys.length === 0}
        title={`最多选择 ${maxSelection} 条 trajectory`}
        onClick={invertSelection}
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        反选
      </Button>
      <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
      <div className="inline-flex h-8 items-center gap-2 rounded-md px-1 text-sm text-muted-foreground">
        <span>同步滚动</span>
        <Switch
          checked={syncScroll}
          aria-label="同步滚动"
          onCheckedChange={onSyncScrollChange}
        />
      </div>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={selectedCount === 0}
        onClick={onExportComparison}
      >
        <Download className="h-3.5 w-3.5" aria-hidden="true" />
        导出对比
      </Button>
      <div className="inline-flex h-8 items-center gap-1.5 rounded-md px-1 text-sm text-muted-foreground">
        <Pin className="h-3.5 w-3.5" aria-hidden="true" />
        已选 <span className="font-medium text-foreground">{selectedMessageCount}</span> 条
      </div>
      <div className="ml-auto text-sm text-muted-foreground">
        显示 <span className="font-medium text-foreground">{selectedCount}</span> /{" "}
        {allKeys.length} 条
      </div>
      {trailingAction}
    </div>
  );
}
