import {
  TrajectoryViewer,
  type TrajectoryMessage,
} from "@agentlens/trajectory-viewer";
import {
  ChevronDown,
  GripVertical,
  Pin,
  SlidersHorizontal,
} from "lucide-react";
import {
  memo,
  useCallback,
  useMemo,
  useRef,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { Trajectory } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getTrajectoryRoles,
  normalizeTrajectoryRole,
} from "@/features/trajectory-view/trajectoryRoles";
import { cn } from "@/lib/utils";

import {
  COLUMN_WIDTH_PRESETS,
  MAX_COLUMN_WIDTH,
  MIN_COLUMN_WIDTH,
  type ColumnDisplayMode,
} from "./types";

interface TrajectoryColumnProps {
  index: number;
  trajectory: Trajectory;
  trajectoryKey: string;
  displayLabel: string;
  selected: boolean;
  displayMode: ColumnDisplayMode;
  selectedRoles: string[];
  showMeta: boolean;
  width: number;
  pinnedMessageKeys: Set<string>;
  setScrollRef: (index: number, node: HTMLDivElement | null) => void;
  onSelectedChange: (trajectoryKey: string, selected: boolean) => void;
  onDisplayModeChange: (mode: ColumnDisplayMode, nextRoles: string[]) => void;
  onShowMetaChange: (showMeta: boolean) => void;
  onWidthChange: (width: number) => void;
  onMessagePinnedChange: (messageKey: string, pinned: boolean) => void;
}

type ResizeState = {
  pointerId: number;
  startX: number;
  startWidth: number;
};

const DEFAULT_META_FIELDS = ["created_at", "latency", "latency_ms", "duration_ms"];

export const TrajectoryColumn = memo(function TrajectoryColumn({
  index,
  trajectory,
  trajectoryKey,
  displayLabel,
  selected,
  displayMode,
  selectedRoles,
  showMeta,
  width,
  pinnedMessageKeys,
  setScrollRef,
  onSelectedChange,
  onDisplayModeChange,
  onShowMetaChange,
  onWidthChange,
  onMessagePinnedChange,
}: TrajectoryColumnProps) {
  const resizeStateRef = useRef<ResizeState | null>(null);
  const roleOptions = useMemo(() => getTrajectoryRoles([trajectory]), [trajectory]);
  const metaFields = useMemo(() => getMetaFields(trajectory), [trajectory]);
  const selectedRoleSet = useMemo(
    () => new Set(selectedRoles.map((role) => normalizeTrajectoryRole(role))),
    [selectedRoles],
  );
  const activeRoleFilter = useMemo(
    () =>
      roleOptions.every((role) => selectedRoleSet.has(normalizeTrajectoryRole(role))) &&
      selectedRoles.length === roleOptions.length
        ? undefined
        : selectedRoles,
    [roleOptions, selectedRoleSet, selectedRoles],
  );
  const setColumnScrollRef = useCallback(
    (node: HTMLDivElement | null) => setScrollRef(index, node),
    [index, setScrollRef],
  );

  const handleModeChange = useCallback(
    (value: string) => {
      const nextMode = value as ColumnDisplayMode;
      onDisplayModeChange(nextMode, getRolesForMode(nextMode, roleOptions, selectedRoles));
    },
    [onDisplayModeChange, roleOptions, selectedRoles],
  );

  const handleRoleToggle = useCallback(
    (role: string, checked: boolean) => {
      const nextRoleSet = new Set(selectedRoleSet);
      const normalized = normalizeTrajectoryRole(role);
      if (checked) {
        nextRoleSet.add(normalized);
      } else {
        nextRoleSet.delete(normalized);
      }
      onDisplayModeChange(
        "custom",
        roleOptions.filter((option) =>
          nextRoleSet.has(normalizeTrajectoryRole(option)),
        ),
      );
    },
    [onDisplayModeChange, roleOptions, selectedRoleSet],
  );

  const renderMessageActions = useCallback(
    (message: TrajectoryMessage, originalIndex: number) => {
      const messageKey = getMessageKey(message, originalIndex);
      const pinned = pinnedMessageKeys.has(messageKey);
      return (
        <button
          type="button"
          className={cn(
            "inline-flex h-6 w-6 items-center justify-center rounded-full border bg-white/70 text-muted-foreground hover:text-foreground",
            pinned && "border-primary bg-primary text-primary-foreground hover:text-primary-foreground",
          )}
          aria-pressed={pinned}
          aria-label={pinned ? "取消标记 message" : "标记 message"}
          title={pinned ? "取消标记" : "标记"}
          onClick={() => onMessagePinnedChange(messageKey, !pinned)}
        >
          <Pin
            className={cn("h-3.5 w-3.5", pinned && "fill-current")}
            aria-hidden="true"
          />
        </button>
      );
    },
    [onMessagePinnedChange, pinnedMessageKeys],
  );

  const getMessageClassName = useCallback(
    (message: TrajectoryMessage, originalIndex: number) =>
      pinnedMessageKeys.has(getMessageKey(message, originalIndex))
        ? "agentlens-trajectory-message--pinned"
        : undefined,
    [pinnedMessageKeys],
  );

  const handleResizePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      resizeStateRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startWidth: width,
      };
    },
    [width],
  );

  const handleResizePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const state = resizeStateRef.current;
      if (state === null || state.pointerId !== event.pointerId) {
        return;
      }
      onWidthChange(clampColumnWidth(state.startWidth + event.clientX - state.startX));
    },
    [onWidthChange],
  );

  const handleResizePointerEnd = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const state = resizeStateRef.current;
      if (state === null || state.pointerId !== event.pointerId) {
        return;
      }
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      resizeStateRef.current = null;
    },
    [],
  );

  return (
    <section
      className="relative flex h-full shrink-0 flex-col border-r bg-background last:border-r-0"
      style={{ width, minWidth: width, maxWidth: width }}
      aria-label={`Trajectory ${displayLabel}`}
      data-trajectory-column={trajectoryKey}
    >
      <header className="sticky top-0 z-10 border-b bg-muted/40 px-3 py-2">
        <label className="flex min-w-0 items-start gap-2">
          <Checkbox
            checked={selected}
            aria-label={`选择 trajectory ${displayLabel}`}
            className="mt-0.5 shrink-0"
            onCheckedChange={(checked) => onSelectedChange(trajectoryKey, checked === true)}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold" title={displayLabel}>
              Traj #{displayLabel}
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {trajectory.message_count} msgs
            </span>
          </span>
        </label>
        <div className="mt-2 flex min-w-0 items-center gap-1.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 min-w-0 flex-1 justify-between gap-1.5 px-2 text-xs"
                title={`显示：${getDisplayModeLabel(displayMode)}`}
              >
                <span className="inline-flex min-w-0 items-center gap-1.5">
                  <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span className="truncate">{getDisplayModeLabel(displayMode)}</span>
                </span>
                <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
              <DropdownMenuLabel>显示模式</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={displayMode} onValueChange={handleModeChange}>
                <DropdownMenuRadioItem value="all">全部</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="user-assistant">
                  仅 user + assistant
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="assistant">仅 assistant</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="custom">自定义</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>自定义 roles</DropdownMenuLabel>
              {roleOptions.map((role) => (
                <DropdownMenuCheckboxItem
                  key={role}
                  checked={selectedRoleSet.has(normalizeTrajectoryRole(role))}
                  onSelect={(event) => event.preventDefault()}
                  onCheckedChange={(checked) => handleRoleToggle(role, checked === true)}
                >
                  <span className="truncate" title={role}>
                    {role}
                  </span>
                </DropdownMenuCheckboxItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuCheckboxItem
                checked={showMeta}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={(checked) => onShowMetaChange(checked === true)}
              >
                显示元信息
              </DropdownMenuCheckboxItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <div className="inline-flex h-7 shrink-0 overflow-hidden rounded-md border bg-background">
            {COLUMN_WIDTH_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                className={cn(
                  "h-7 px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground",
                  width === preset && "bg-accent text-foreground",
                )}
                aria-label={`设置列宽 ${preset}px`}
                title={`${preset}px`}
                onClick={() => onWidthChange(preset)}
              >
                {preset}
              </button>
            ))}
          </div>
        </div>
      </header>
      <div
        ref={setColumnScrollRef}
        className="min-h-0 flex-1 overflow-y-auto bg-muted/10"
        data-trajectory-column-scroll={trajectoryKey}
      >
        <TrajectoryViewer
          trajectory={trajectory}
          filterRoles={activeRoleFilter}
          renderMessageActions={renderMessageActions}
          messageClassName={getMessageClassName}
          showHeader={false}
          showMetaLine={showMeta}
          metaFields={metaFields}
          collapsibleMessages
          expandLabel="展开"
          collapseLabel="收起"
          className="agentlens-trajectory-viewer--embedded"
        />
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={`调整 trajectory ${displayLabel} 列宽`}
        className="absolute right-0 top-0 z-20 flex h-full w-3 translate-x-1/2 cursor-col-resize items-center justify-center text-muted-foreground/70 hover:text-foreground"
        onPointerDown={handleResizePointerDown}
        onPointerMove={handleResizePointerMove}
        onPointerUp={handleResizePointerEnd}
        onPointerCancel={handleResizePointerEnd}
      >
        <GripVertical className="h-4 w-4" aria-hidden="true" />
      </div>
    </section>
  );
});

export function getMessageKey(message: TrajectoryMessage, originalIndex: number): string {
  return `${message.row_identity}:${originalIndex}`;
}

function getRolesForMode(
  mode: ColumnDisplayMode,
  roleOptions: string[],
  currentRoles: string[],
): string[] {
  if (mode === "all") {
    return roleOptions;
  }
  if (mode === "user-assistant") {
    return roleOptions.filter((role) =>
      ["user", "assistant"].includes(normalizeTrajectoryRole(role)),
    );
  }
  if (mode === "assistant") {
    return roleOptions.filter((role) => normalizeTrajectoryRole(role) === "assistant");
  }
  return currentRoles.length > 0 ? currentRoles : roleOptions;
}

function getDisplayModeLabel(mode: ColumnDisplayMode): string {
  if (mode === "user-assistant") {
    return "仅 user + assistant";
  }
  if (mode === "assistant") {
    return "仅 assistant";
  }
  if (mode === "custom") {
    return "自定义";
  }
  return "全部";
}

function clampColumnWidth(width: number): number {
  return Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, Math.round(width)));
}

function getMetaFields(trajectory: Trajectory): string[] {
  const fields = new Set(DEFAULT_META_FIELDS);
  for (const message of trajectory.messages) {
    for (const field of Object.keys(message.raw)) {
      if (/_at$/i.test(field)) {
        fields.add(field);
      }
    }
  }
  return Array.from(fields);
}
