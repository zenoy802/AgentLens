import { useCallback, useEffect, useMemo, useRef, type UIEvent } from "react";

import type { Trajectory } from "@/api/types";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import {
  getTrajectoryOptions,
  type TrajectoryOption,
} from "@/features/trajectory-view/trajectoryOptions";
import { getTrajectoryRoles } from "@/features/trajectory-view/trajectoryRoles";

import { ComparisonToolbar } from "./ComparisonToolbar";
import { TrajectoryColumn } from "./TrajectoryColumn";

export interface ComparisonViewProps {
  trajectories: Trajectory[];
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
  syncScroll: boolean;
  roleFilter: string[];
  onSyncScrollChange: (enabled: boolean) => void;
  onRoleFilterChange: (roles: string[]) => void;
}

const MAX_SELECTED_TRAJECTORIES = 10;

export function ComparisonView({
  trajectories,
  selectedKeys,
  onSelectionChange,
  syncScroll,
  roleFilter,
  onSyncScrollChange,
  onRoleFilterChange,
}: ComparisonViewProps) {
  const scrollRefs = useRef<Array<HTMLDivElement | null>>([]);
  const syncingRef = useRef(false);
  const trajectoryOptions = useMemo(() => getTrajectoryOptions(trajectories), [trajectories]);
  const allKeys = useMemo(() => trajectoryOptions.map((option) => option.key), [
    trajectoryOptions,
  ]);
  const allRoles = useMemo(() => getTrajectoryRoles(trajectories), [trajectories]);
  const selectedKeySet = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const visibleTrajectories = useMemo(
    () => trajectoryOptions.filter((option) => selectedKeySet.has(option.key)),
    [selectedKeySet, trajectoryOptions],
  );
  const showSidebar = trajectoryOptions.length > 6;

  useEffect(() => {
    scrollRefs.current.length = visibleTrajectories.length;
  }, [visibleTrajectories.length]);

  useEffect(
    () => () => {
      scrollRefs.current = [];
    },
    [],
  );

  const setScrollRef = useCallback((index: number, node: HTMLDivElement | null) => {
    scrollRefs.current[index] = node;
  }, []);

  const handleSelectedChange = useCallback(
    (trajectoryKey: string, selected: boolean) => {
      const nextSet = new Set(selectedKeys);
      if (selected) {
        if (nextSet.size >= MAX_SELECTED_TRAJECTORIES) {
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

  const handleScroll = useCallback(
    (sourceIdx: number, ev: UIEvent<HTMLDivElement>) => {
      if (!syncScroll) {
        return;
      }
      if (syncingRef.current) {
        return;
      }

      syncingRef.current = true;
      const source = scrollRefs.current[sourceIdx] ?? ev.currentTarget;
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

  return (
    <div className="space-y-3">
      <ComparisonToolbar
        allKeys={allKeys}
        selectedKeys={selectedKeys}
        allRoles={allRoles}
        roleFilter={roleFilter}
        syncScroll={syncScroll}
        maxSelection={MAX_SELECTED_TRAJECTORIES}
        onSelectionChange={onSelectionChange}
        onRoleFilterChange={onRoleFilterChange}
        onSyncScrollChange={onSyncScrollChange}
      />

      <div
        className={cn(
          "overflow-hidden rounded-lg border bg-background",
          showSidebar && "grid grid-cols-[220px_minmax(0,1fr)]",
        )}
      >
        {showSidebar ? (
          <SelectionSidebar
            trajectoryOptions={trajectoryOptions}
            selectedKeys={selectedKeys}
            maxSelection={MAX_SELECTED_TRAJECTORIES}
            onSelectedChange={handleSelectedChange}
          />
        ) : null}
        <div className="min-w-0">
          {visibleTrajectories.length > 0 ? (
            <div className="overflow-x-auto">
              <div className="flex h-[680px] min-w-max">
                {visibleTrajectories.map((option, index) => (
                  <TrajectoryColumn
                    key={option.key}
                    index={index}
                    trajectory={option.trajectory}
                    trajectoryKey={option.key}
                    displayLabel={option.label}
                    selected={selectedKeySet.has(option.key)}
                    roleFilter={roleFilter}
                    setScrollRef={setScrollRef}
                    onSelectedChange={handleSelectedChange}
                    onScroll={handleScroll}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
              请选择至少一条 trajectory 进行对比。
            </div>
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
  onSelectedChange,
}: {
  trajectoryOptions: TrajectoryOption[];
  selectedKeys: string[];
  maxSelection: number;
  onSelectedChange: (trajectoryKey: string, selected: boolean) => void;
}) {
  const selectedKeySet = new Set(selectedKeys);
  const selectedCount = trajectoryOptions.filter((option) =>
    selectedKeySet.has(option.key),
  ).length;

  return (
    <aside className="border-r bg-muted/20">
      <div className="border-b px-3 py-2">
        <div className="text-sm font-semibold">选择对比</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          最多 {maxSelection} 条
        </div>
      </div>
      <div className="max-h-[680px] space-y-1 overflow-y-auto p-2">
        {trajectoryOptions.map((option) => {
          const checked = selectedKeySet.has(option.key);
          const disabled = !checked && selectedCount >= maxSelection;
          return (
            <label
              key={option.key}
              className={cn(
                "flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-background",
                disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
              )}
            >
              <Checkbox
                checked={checked}
                disabled={disabled}
                aria-label={`选择 trajectory ${option.label}`}
                onCheckedChange={(selected) => onSelectedChange(option.key, selected)}
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
