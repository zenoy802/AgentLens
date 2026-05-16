import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Maximize2 } from "lucide-react";
import { toast } from "sonner";

import type { Trajectory } from "@/api/types";
import { EmptyState } from "@/components/common/EmptyState";
import { FullscreenViewDialog } from "@/components/common/FullscreenViewDialog";
import { Checkbox } from "@/components/ui/checkbox";
import {
  getTrajectoryOptions,
  type TrajectoryOption,
} from "@/features/trajectory-view/trajectoryOptions";
import { normalizeTrajectoryRole } from "@/features/trajectory-view/trajectoryRoles";
import { downloadBlob } from "@/lib/download";
import { cn } from "@/lib/utils";

import { ComparisonToolbar } from "./ComparisonToolbar";
import { generateComparisonMarkdown } from "./exportComparison";
import { TrajectoryColumn } from "./TrajectoryColumn";
import { DEFAULT_COLUMN_WIDTH, type ColumnDisplayMode } from "./types";

export interface ComparisonViewProps {
  trajectories: Trajectory[];
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
  syncScroll: boolean;
  isFullscreen?: boolean;
  onSyncScrollChange: (enabled: boolean) => void;
}

const MAX_SELECTED_TRAJECTORIES = 10;
const DEFAULT_SHOW_META = true;
const EMPTY_MESSAGE_KEYS = new Set<string>();
const SELECTION_ROW_HEIGHT = 36;

export function ComparisonView({
  trajectories,
  selectedKeys,
  onSelectionChange,
  syncScroll,
  isFullscreen = false,
  onSyncScrollChange,
}: ComparisonViewProps) {
  const scrollRefs = useRef<Array<HTMLDivElement | null>>([]);
  const syncingRef = useRef(false);
  const [scrollRefVersion, setScrollRefVersion] = useState(0);
  const [columnDisplayModes, setColumnDisplayModes] = useState<
    Map<string, ColumnDisplayMode>
  >(() => new Map());
  const [columnRoleFilters, setColumnRoleFilters] = useState<Map<string, string[]>>(
    () => new Map(),
  );
  const [columnMetaVisibility, setColumnMetaVisibility] = useState<Map<string, boolean>>(
    () => new Map(),
  );
  const [columnWidths, setColumnWidths] = useState<Map<string, number>>(() => new Map());
  const [pinnedMessagesByColumn, setPinnedMessagesByColumn] = useState<
    Map<string, Set<string>>
  >(() => new Map());
  const trajectoryOptions = useMemo(() => getTrajectoryOptions(trajectories), [trajectories]);
  const allKeys = useMemo(() => trajectoryOptions.map((option) => option.key), [
    trajectoryOptions,
  ]);
  const optionByKey = useMemo(
    () => new Map(trajectoryOptions.map((option) => [option.key, option])),
    [trajectoryOptions],
  );
  const keyOrder = useMemo(
    () => new Map(allKeys.map((key, index) => [key, index])),
    [allKeys],
  );
  const validSelectedKeys = useMemo(
    () => filterCurrentTrajectoryKeys(selectedKeys, keyOrder),
    [keyOrder, selectedKeys],
  );
  const selectedKeysRef = useRef(validSelectedKeys);
  selectedKeysRef.current = validSelectedKeys;
  const selectedKeySet = useMemo(() => new Set(validSelectedKeys), [validSelectedKeys]);
  const visibleTrajectories = useMemo(
    () =>
      validSelectedKeys.flatMap((key) => {
        const option = optionByKey.get(key);
        return option === undefined ? [] : [option];
      }),
    [optionByKey, validSelectedKeys],
  );
  const visibleTrajectoryCount = visibleTrajectories.length;
  const pinnedMessageCount = useMemo(() => {
    let count = 0;
    for (const messages of pinnedMessagesByColumn.values()) {
      count += messages.size;
    }
    return count;
  }, [pinnedMessagesByColumn]);

  useEffect(() => {
    scrollRefs.current.length = visibleTrajectoryCount;
  }, [visibleTrajectoryCount]);

  const handleScroll = useCallback(
    (sourceIdx: number, source: HTMLDivElement) => {
      if (!syncScroll) {
        return;
      }
      if (syncingRef.current) {
        return;
      }

      syncingRef.current = true;
      const sourceScrollable = source.scrollHeight - source.clientHeight;
      const ratio = sourceScrollable <= 0 ? 0 : source.scrollTop / sourceScrollable;

      scrollRefs.current.forEach((ref, index) => {
        if (index !== sourceIdx && ref !== null) {
          const targetScrollable = ref.scrollHeight - ref.clientHeight;
          ref.scrollTop = ratio * Math.max(0, targetScrollable);
        }
      });

      requestAnimationFrame(() => {
        syncingRef.current = false;
      });
    },
    [syncScroll],
  );

  const setScrollRef = useCallback(
    (index: number, node: HTMLDivElement | null) => {
      if (scrollRefs.current[index] === node) {
        return;
      }
      scrollRefs.current[index] = node;
      setScrollRefVersion((version) => version + 1);
    },
    [],
  );

  const handleSelectedChange = useCallback(
    (trajectoryKey: string, selected: boolean) => {
      const nextSet = new Set(selectedKeysRef.current);
      if (selected) {
        if (!nextSet.has(trajectoryKey) && nextSet.size >= MAX_SELECTED_TRAJECTORIES) {
          toast.warning(`最多选择 ${MAX_SELECTED_TRAJECTORIES} 条 trajectory`);
          return;
        }
        nextSet.add(trajectoryKey);
      } else {
        nextSet.delete(trajectoryKey);
      }
      onSelectionChange(
        sortTrajectoryKeys([...nextSet], keyOrder).slice(0, MAX_SELECTED_TRAJECTORIES),
      );
    },
    [keyOrder, onSelectionChange],
  );

  const handleColumnDisplayModeChange = useCallback(
    (columnKey: string, mode: ColumnDisplayMode, nextRoles: string[]) => {
      setColumnDisplayModes((current) => {
        const next = new Map(current);
        next.set(columnKey, mode);
        return next;
      });
      setColumnRoleFilters((current) => {
        const next = new Map(current);
        next.set(columnKey, nextRoles);
        return next;
      });
    },
    [],
  );

  const handleColumnMetaVisibilityChange = useCallback(
    (columnKey: string, showMeta: boolean) => {
      setColumnMetaVisibility((current) => {
        const next = new Map(current);
        next.set(columnKey, showMeta);
        return next;
      });
    },
    [],
  );

  const handleColumnWidthChange = useCallback((columnKey: string, width: number) => {
    setColumnWidths((current) => {
      const next = new Map(current);
      next.set(columnKey, width);
      return next;
    });
  }, []);

  const handleMessagePinnedChange = useCallback(
    (columnKey: string, messageKey: string, pinned: boolean) => {
      setPinnedMessagesByColumn((current) => {
        const next = new Map(current);
        const messageKeys = new Set(next.get(columnKey) ?? EMPTY_MESSAGE_KEYS);
        if (pinned) {
          messageKeys.add(messageKey);
        } else {
          messageKeys.delete(messageKey);
        }

        if (messageKeys.size === 0) {
          next.delete(columnKey);
        } else {
          next.set(columnKey, messageKeys);
        }
        return next;
      });
    },
    [],
  );

  const handleExportComparison = useCallback(() => {
    if (visibleTrajectories.length === 0) {
      toast.warning("请选择至少 1 条 trajectory");
      return;
    }

    const exportTrajectories = visibleTrajectories.map((option) =>
      filterTrajectoryForExport(
        option.trajectory,
        columnRoleFilters.get(option.key),
      ),
    );
    const markdown = generateComparisonMarkdown(exportTrajectories);
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    downloadBlob(blob, getExportFilename());
    toast.success("对比视图已导出");
  }, [columnRoleFilters, visibleTrajectories]);

  useEffect(() => {
    if (!syncScroll) {
      return;
    }

    const cleanupCallbacks = Array.from(
      { length: visibleTrajectoryCount },
      (_, index) => {
        const node = scrollRefs.current[index];
        if (node === null || node === undefined) {
          return null;
        }

        const handleNativeScroll = () => handleScroll(index, node);
        node.addEventListener("scroll", handleNativeScroll, { passive: true });
        return () => node.removeEventListener("scroll", handleNativeScroll);
      },
    ).filter((cleanup): cleanup is () => void => cleanup !== null);

    return () => {
      cleanupCallbacks.forEach((cleanup) => cleanup());
    };
  }, [handleScroll, scrollRefVersion, syncScroll, visibleTrajectoryCount]);

  return (
    <div
      className={cn(
        "space-y-3",
        isFullscreen && "flex h-full min-h-0 flex-col space-y-0 gap-3",
      )}
      data-trajectory-comparison-view
    >
      <ComparisonToolbar
        allKeys={allKeys}
        selectedKeys={validSelectedKeys}
        selectedMessageCount={pinnedMessageCount}
        syncScroll={syncScroll}
        maxSelection={MAX_SELECTED_TRAJECTORIES}
        trailingAction={
          !isFullscreen ? (
            <FullscreenViewDialog
              title="Trajectory 对比"
              description={`显示 ${visibleTrajectories.length} / ${trajectoryOptions.length} 条`}
              trigger={
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground hover:text-foreground"
                  aria-label="全屏查看 trajectory 对比"
                  title="全屏"
                >
                  <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              }
            >
              <ComparisonView
                trajectories={trajectories}
                selectedKeys={validSelectedKeys}
                onSelectionChange={onSelectionChange}
                syncScroll={syncScroll}
                isFullscreen
                onSyncScrollChange={onSyncScrollChange}
              />
            </FullscreenViewDialog>
          ) : null
        }
        onSelectionChange={onSelectionChange}
        onSyncScrollChange={onSyncScrollChange}
        onExportComparison={handleExportComparison}
      />

      <div
        className={cn(
          "grid grid-cols-[180px_minmax(0,1fr)] overflow-hidden rounded-lg border bg-background md:grid-cols-[220px_minmax(0,1fr)]",
          isFullscreen && "min-h-0 flex-1",
        )}
      >
        <SelectionSidebar
          trajectoryOptions={trajectoryOptions}
          selectedKeySet={selectedKeySet}
          selectedCount={validSelectedKeys.length}
          maxSelection={MAX_SELECTED_TRAJECTORIES}
          isFullscreen={isFullscreen}
          onSelectedChange={handleSelectedChange}
        />
        <div className={cn("min-w-0", isFullscreen && "min-h-0")}>
          {visibleTrajectories.length > 0 ? (
            <div className={cn("overflow-x-auto", isFullscreen && "h-full min-h-0")}>
              <div
                className={cn(
                  "flex min-w-max",
                  isFullscreen ? "h-full min-h-0" : "h-[680px]",
                )}
              >
                {visibleTrajectories.map((option, index) => {
                  const columnKey = option.key;
                  return (
                    <TrajectoryColumn
                      key={option.key}
                      index={index}
                      trajectory={option.trajectory}
                      trajectoryKey={option.key}
                      displayLabel={option.label}
                      selected
                      displayMode={columnDisplayModes.get(columnKey) ?? "all"}
                      selectedRoles={columnRoleFilters.get(columnKey)}
                      showMeta={columnMetaVisibility.get(columnKey) ?? DEFAULT_SHOW_META}
                      width={columnWidths.get(columnKey) ?? DEFAULT_COLUMN_WIDTH}
                      pinnedMessageKeys={
                        pinnedMessagesByColumn.get(columnKey) ?? EMPTY_MESSAGE_KEYS
                      }
                      setScrollRef={setScrollRef}
                      onSelectedChange={handleSelectedChange}
                      onDisplayModeChange={handleColumnDisplayModeChange}
                      onShowMetaChange={handleColumnMetaVisibilityChange}
                      onWidthChange={handleColumnWidthChange}
                      onMessagePinnedChange={handleMessagePinnedChange}
                    />
                  );
                })}
              </div>
            </div>
          ) : (
            <EmptyState
              title="请选择至少 1 条 trajectory"
              description="在左侧勾选要横向对比的 trajectory。"
              className={cn("rounded-none border-0", isFullscreen ? "h-full" : "h-[320px]")}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function SelectionSidebar({
  trajectoryOptions,
  selectedKeySet,
  selectedCount,
  maxSelection,
  isFullscreen,
  onSelectedChange,
}: {
  trajectoryOptions: TrajectoryOption[];
  selectedKeySet: Set<string>;
  selectedCount: number;
  maxSelection: number;
  isFullscreen: boolean;
  onSelectedChange: (trajectoryKey: string, selected: boolean) => void;
}) {
  const scrollParentRef = useRef<HTMLDivElement | null>(null);
  const rowVirtualizer = useVirtualizer({
    count: trajectoryOptions.length,
    estimateSize: () => SELECTION_ROW_HEIGHT,
    getItemKey: (index) => trajectoryOptions[index]?.key ?? index,
    getScrollElement: () => scrollParentRef.current,
    overscan: 12,
  });

  return (
    <aside className="flex min-h-0 flex-col border-r bg-muted/20">
      <div className="border-b px-3 py-2">
        <div className="text-sm font-semibold">选择对比</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          最多 {maxSelection} 条
        </div>
      </div>
      <div
        ref={scrollParentRef}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto p-2",
          !isFullscreen && "max-h-[680px]",
        )}
      >
        <div
          className="relative w-full"
          style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualItem) => {
            const option = trajectoryOptions[virtualItem.index];
            if (option === undefined) {
              return null;
            }

            const checked = selectedKeySet.has(option.key);
            const atSelectionLimit = !checked && selectedCount >= maxSelection;
            return (
              <label
                key={option.key}
                title={
                  atSelectionLimit
                    ? `最多选择 ${maxSelection} 条 trajectory`
                    : option.label
                }
                className={cn(
                  "absolute left-0 top-0 flex h-8 w-full min-w-0 items-center gap-2 rounded-md px-2 text-sm hover:bg-background",
                  atSelectionLimit && "text-muted-foreground",
                )}
                style={{ transform: `translateY(${virtualItem.start}px)` }}
              >
                <Checkbox
                  checked={checked}
                  aria-label={`选择 trajectory ${option.label}`}
                  onCheckedChange={(selected) =>
                    onSelectedChange(option.key, selected === true)
                  }
                />
                <span className="truncate" title={option.label}>
                  {option.label}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function filterTrajectoryForExport(
  trajectory: Trajectory,
  roleFilter: string[] | undefined,
): Trajectory {
  if (roleFilter === undefined) {
    return trajectory;
  }

  const allowedRoles = new Set(roleFilter.map((role) => normalizeTrajectoryRole(role)));
  const messages = trajectory.messages.filter((message) =>
    allowedRoles.has(normalizeTrajectoryRole(message.role)),
  );
  return {
    ...trajectory,
    message_count: messages.length,
    messages,
  };
}

function getExportFilename(): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `agentlens-comparison-${timestamp}.md`;
}

function filterCurrentTrajectoryKeys(
  keys: string[],
  keyOrder: Map<string, number>,
): string[] {
  return sortTrajectoryKeys([...new Set(keys)].filter((key) => keyOrder.has(key)), keyOrder);
}

function sortTrajectoryKeys(keys: string[], keyOrder: Map<string, number>): string[] {
  return keys.sort((left, right) => {
    const leftOrder = keyOrder.get(left) ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = keyOrder.get(right) ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.localeCompare(right);
  });
}
