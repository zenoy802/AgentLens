import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import {
  getTrajectoryRoles,
  normalizeTrajectoryRole,
} from "@/features/trajectory-view/trajectoryRoles";
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
  const selectedKeySet = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const visibleTrajectories = useMemo(
    () => trajectoryOptions.filter((option) => selectedKeySet.has(option.key)),
    [selectedKeySet, trajectoryOptions],
  );
  const pinnedMessageCount = useMemo(() => {
    let count = 0;
    pinnedMessagesByColumn.forEach((messages) => {
      count += messages.size;
    });
    return count;
  }, [pinnedMessagesByColumn]);

  useEffect(() => {
    scrollRefs.current.length = visibleTrajectories.length;
  }, [visibleTrajectories.length]);

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
      const nextSet = new Set(selectedKeys);
      if (selected) {
        if (nextSet.size >= MAX_SELECTED_TRAJECTORIES) {
          toast.warning(`最多选择 ${MAX_SELECTED_TRAJECTORIES} 条 trajectory`);
          return;
        }
        nextSet.add(trajectoryKey);
      } else {
        nextSet.delete(trajectoryKey);
      }
      onSelectionChange(
        allKeys.filter((key) => nextSet.has(key)).slice(0, MAX_SELECTED_TRAJECTORIES),
      );
    },
    [allKeys, onSelectionChange, selectedKeys],
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

    const cleanupCallbacks = visibleTrajectories
      .map((_, index) => {
        const node = scrollRefs.current[index];
        if (node === null || node === undefined) {
          return null;
        }

        const handleNativeScroll = () => handleScroll(index, node);
        node.addEventListener("scroll", handleNativeScroll, { passive: true });
        return () => node.removeEventListener("scroll", handleNativeScroll);
      })
      .filter((cleanup): cleanup is () => void => cleanup !== null);

    return () => {
      cleanupCallbacks.forEach((cleanup) => cleanup());
    };
  }, [handleScroll, scrollRefVersion, syncScroll, visibleTrajectories]);

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
        selectedKeys={selectedKeys}
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
                selectedKeys={selectedKeys}
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
          selectedKeys={selectedKeys}
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
                  const roleOptions = getTrajectoryRoles([option.trajectory]);
                  return (
                    <TrajectoryColumn
                      key={option.key}
                      index={index}
                      trajectory={option.trajectory}
                      trajectoryKey={option.key}
                      displayLabel={option.label}
                      selected={selectedKeySet.has(option.key)}
                      displayMode={columnDisplayModes.get(columnKey) ?? "all"}
                      selectedRoles={columnRoleFilters.get(columnKey) ?? roleOptions}
                      showMeta={columnMetaVisibility.get(columnKey) ?? DEFAULT_SHOW_META}
                      width={columnWidths.get(columnKey) ?? DEFAULT_COLUMN_WIDTH}
                      pinnedMessageKeys={
                        pinnedMessagesByColumn.get(columnKey) ?? EMPTY_MESSAGE_KEYS
                      }
                      setScrollRef={setScrollRef}
                      onSelectedChange={handleSelectedChange}
                      onDisplayModeChange={(mode, nextRoles) =>
                        handleColumnDisplayModeChange(columnKey, mode, nextRoles)
                      }
                      onShowMetaChange={(showMeta) =>
                        handleColumnMetaVisibilityChange(columnKey, showMeta)
                      }
                      onWidthChange={(width) => handleColumnWidthChange(columnKey, width)}
                      onMessagePinnedChange={(messageKey, pinned) =>
                        handleMessagePinnedChange(columnKey, messageKey, pinned)
                      }
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
  selectedKeys,
  maxSelection,
  isFullscreen,
  onSelectedChange,
}: {
  trajectoryOptions: TrajectoryOption[];
  selectedKeys: string[];
  maxSelection: number;
  isFullscreen: boolean;
  onSelectedChange: (trajectoryKey: string, selected: boolean) => void;
}) {
  const selectedKeySet = new Set(selectedKeys);
  const selectedCount = trajectoryOptions.filter((option) =>
    selectedKeySet.has(option.key),
  ).length;

  return (
    <aside className="flex min-h-0 flex-col border-r bg-muted/20">
      <div className="border-b px-3 py-2">
        <div className="text-sm font-semibold">选择对比</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          最多 {maxSelection} 条
        </div>
      </div>
      <div
        className={cn(
          "min-h-0 flex-1 space-y-1 overflow-y-auto p-2",
          !isFullscreen && "max-h-[680px]",
        )}
      >
        {trajectoryOptions.map((option) => {
          const checked = selectedKeySet.has(option.key);
          const atSelectionLimit = !checked && selectedCount >= maxSelection;
          return (
            <label
              key={option.key}
              title={atSelectionLimit ? `最多选择 ${maxSelection} 条 trajectory` : option.label}
              className={cn(
                "flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-background",
                atSelectionLimit && "text-muted-foreground",
              )}
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
