import { useMemo, useState } from "react";
import { Download, Tags } from "lucide-react";

import { useLabels } from "@/api/hooks/useLabels";
import { useLabelSchema } from "@/api/hooks/useLabelSchema";
import type { LabelOption } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SchemaEditorDialog } from "@/features/labeling/SchemaEditorDialog";
import { getStableRowIdentity } from "@/features/row-view/rowIdentity";
import { formatApiError } from "@/lib/formatApiError";
import {
  computeStats,
  type LabelSchema,
  type LabelStats,
} from "@/lib/labelStats";
import { cn } from "@/lib/utils";
import { useLabelsStore } from "@/stores/labelsStore";
import { useQueryStore } from "@/stores/queryStore";

type LabelingPanelProps = {
  open: boolean;
  queryId: number | null;
  onExportLabels: () => void;
  onOpenChange: (open: boolean) => void;
};

export function LabelingPanel({
  open,
  queryId,
  onExportLabels,
  onOpenChange,
}: LabelingPanelProps) {
  const [schemaEditorOpen, setSchemaEditorOpen] = useState(false);
  const schema = useLabelSchema(open ? queryId : null);
  const fieldCount = schema.data?.fields.length ?? 0;

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-0 p-0 sm:max-w-lg"
        >
          <SheetHeader className="border-b p-4 pr-12">
            <SheetTitle>打标</SheetTitle>
            <SheetDescription>
              查看当前结果集的打标分布，并快速筛选表格行。
            </SheetDescription>
          </SheetHeader>

          <div className="flex gap-2 border-b p-4">
            <Button
              variant="outline"
              className="flex-1 gap-2"
              onClick={() => setSchemaEditorOpen(true)}
              disabled={queryId === null}
            >
              <Tags className="h-4 w-4" aria-hidden="true" />
              编辑 Schema
            </Button>
            <Button
              variant="outline"
              className="flex-1 gap-2"
              onClick={onExportLabels}
              disabled={queryId === null}
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              导出打标
            </Button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {open ? (
              <LabelStatsContent
                fieldCount={fieldCount}
                queryId={queryId}
                schemaData={schema.data}
                isError={schema.isError}
                isLoading={schema.isLoading}
                error={schema.error}
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>

      <SchemaEditorDialog
        open={schemaEditorOpen}
        queryId={queryId}
        onOpenChange={setSchemaEditorOpen}
      />
    </>
  );
}

function LabelStatsContent({
  fieldCount,
  queryId,
  schemaData,
  isError,
  isLoading,
  error,
}: {
  fieldCount: number;
  queryId: number | null;
  schemaData: LabelSchema | undefined;
  isError: boolean;
  isLoading: boolean;
  error: unknown;
}) {
  const columns = useQueryStore((state) => state.columns);
  const rows = useQueryStore((state) => state.rows);
  const filters = useQueryStore((state) => state.filters);
  const toggleLabelFilterValue = useQueryStore((state) => state.toggleLabelFilterValue);
  const labelsByRow = useLabelsStore((state) => state.labelsByRow);
  const rowIds = useMemo(
    () => rows.map((row, index) => getStableRowIdentity(row, columns, index)),
    [columns, rows],
  );
  useLabels(queryId, rowIds);

  const stats = useMemo(
    () =>
      schemaData === undefined
        ? {}
        : computeStats(schemaData, labelsByRow, rowIds),
    [labelsByRow, rowIds, schemaData],
  );

  return (
    <StatsContent
      fieldCount={fieldCount}
      filters={filters}
      isError={isError}
      isLoading={isLoading}
      rowCount={rowIds.length}
      stats={stats}
      error={error}
      onToggleOption={toggleLabelFilterValue}
    />
  );
}

function StatsContent({
  fieldCount,
  filters,
  isError,
  isLoading,
  rowCount,
  stats,
  error,
  onToggleOption,
}: {
  fieldCount: number;
  filters: Record<string, string[]>;
  isError: boolean;
  isLoading: boolean;
  rowCount: number;
  stats: LabelStats;
  error: unknown;
  onToggleOption: (fieldKey: string, value: string) => void;
}) {
  if (isLoading) {
    return (
      <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
        正在加载打标统计...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
        {formatApiError(error)}
      </div>
    );
  }

  if (fieldCount === 0) {
    return (
      <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        暂无打标字段。先编辑 Schema 后即可查看统计。
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="text-sm font-semibold">统计</div>
        <div className="mt-1 text-xs text-muted-foreground">
          当前结果集 {rowCount} 行，点击选项可切换表格筛选。
        </div>
      </div>

      {Object.values(stats).map((fieldStats) => (
        <FieldStatsBlock
          key={fieldStats.field.key}
          selectedValues={filters[fieldStats.field.key] ?? []}
          stats={fieldStats}
          onToggleOption={onToggleOption}
        />
      ))}
    </div>
  );
}

function FieldStatsBlock({
  selectedValues,
  stats,
  onToggleOption,
}: {
  selectedValues: string[];
  stats: LabelStats[string];
  onToggleOption: (fieldKey: string, value: string) => void;
}) {
  const { field, total, labeled, distribution } = stats;

  if (field.type === "text") {
    return (
      <section className="space-y-2 rounded-lg border bg-card p-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="min-w-0 truncate text-sm font-semibold" title={field.label}>
            {field.label}
          </h3>
          <span className="shrink-0 text-xs text-muted-foreground">
            text
          </span>
        </div>
        <StatBar
          count={labeled}
          label="已填写"
          maxCount={Math.max(total, 1)}
          total={total}
        />
      </section>
    );
  }

  const maxCount = Math.max(1, ...distribution.map((item) => item.count));

  return (
    <section className="space-y-2 rounded-lg border bg-card p-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="min-w-0 truncate text-sm font-semibold" title={field.label}>
          {field.label}
        </h3>
        <span className="shrink-0 text-xs text-muted-foreground">
          {labeled}/{total}
        </span>
      </div>

      <div className="space-y-1.5">
        {distribution.map((item) =>
          item.option === null ? (
            <StatBar
              key="__unlabeled"
              count={item.count}
              label="未打标"
              maxCount={maxCount}
              option={null}
              total={total}
            />
          ) : (
            <StatBarButton
              key={item.option.value}
              active={selectedValues.includes(item.option.value)}
              count={item.count}
              maxCount={maxCount}
              option={item.option}
              total={total}
              onClick={() => onToggleOption(field.key, item.option!.value)}
            />
          ),
        )}
      </div>
    </section>
  );
}

function StatBarButton({
  active,
  count,
  maxCount,
  option,
  total,
  onClick,
}: {
  active: boolean;
  count: number;
  maxCount: number;
  option: LabelOption;
  total: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "w-full rounded-md px-2 py-1 text-left transition-colors hover:bg-accent",
        active && "bg-primary/10 text-primary hover:bg-primary/15",
      )}
      aria-pressed={active}
      onClick={onClick}
    >
      <StatBar
        count={count}
        label={option.label}
        maxCount={maxCount}
        option={option}
        total={total}
      />
    </button>
  );
}

function StatBar({
  count,
  label,
  maxCount,
  option,
  total,
}: {
  count: number;
  label: string;
  maxCount: number;
  option?: LabelOption | null;
  total: number;
}) {
  const width = maxCount <= 0 ? 0 : (count / maxCount) * 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-sm">
        <OptionDot option={option ?? null} />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {count}
          {total > 0 ? ` (${Math.round((count / total) * 100)}%)` : ""}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary/70"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function OptionDot({ option }: { option: LabelOption | null }) {
  if (option === null) {
    return (
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full border border-muted-foreground bg-background"
        aria-hidden="true"
      />
    );
  }

  return (
    <span
      className="h-2.5 w-2.5 shrink-0 rounded-full border border-border"
      style={
        option.color === undefined || option.color === null
          ? undefined
          : { backgroundColor: option.color, borderColor: option.color }
      }
      aria-hidden="true"
    />
  );
}
