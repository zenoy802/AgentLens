import { TrajectoryViewer } from "@agentlens/trajectory-viewer";
import { memo, useCallback, useMemo, type UIEvent } from "react";

import type { Trajectory } from "@/api/types";
import { Checkbox } from "@/components/ui/checkbox";

interface TrajectoryColumnProps {
  index: number;
  trajectory: Trajectory;
  trajectoryKey: string;
  displayLabel: string;
  selected: boolean;
  roleFilter: string[];
  setScrollRef: (index: number, node: HTMLDivElement | null) => void;
  onSelectedChange: (trajectoryKey: string, selected: boolean) => void;
  onScroll: (index: number, event: UIEvent<HTMLDivElement>) => void;
}

const DEFAULT_META_FIELDS = ["created_at", "latency", "latency_ms", "duration_ms"];

export const TrajectoryColumn = memo(function TrajectoryColumn({
  index,
  trajectory,
  trajectoryKey,
  displayLabel,
  selected,
  roleFilter,
  setScrollRef,
  onSelectedChange,
  onScroll,
}: TrajectoryColumnProps) {
  const metaFields = useMemo(() => getMetaFields(trajectory), [trajectory]);
  const setColumnScrollRef = useCallback(
    (node: HTMLDivElement | null) => setScrollRef(index, node),
    [index, setScrollRef],
  );
  const handleScroll = useCallback(
    (event: UIEvent<HTMLDivElement>) => onScroll(index, event),
    [index, onScroll],
  );

  return (
    <section
      className="flex h-full w-[400px] shrink-0 flex-col border-r bg-background last:border-r-0"
      aria-label={`Trajectory ${displayLabel}`}
    >
      <header className="sticky top-0 z-10 border-b bg-muted/40 px-3 py-2">
        <label className="flex min-w-0 items-start gap-2">
          <Checkbox
            checked={selected}
            aria-label={`选择 trajectory ${displayLabel}`}
            className="mt-0.5 shrink-0"
            onCheckedChange={(checked) => onSelectedChange(trajectoryKey, checked)}
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
      </header>
      <div
        ref={setColumnScrollRef}
        className="min-h-0 flex-1 overflow-y-auto bg-muted/10"
        onScroll={handleScroll}
      >
        <TrajectoryViewer
          trajectory={trajectory}
          filterRoles={roleFilter}
          showHeader={false}
          showMetaLine
          metaFields={metaFields}
          collapsibleMessages
          expandLabel="展开"
          collapseLabel="收起"
          className="agentlens-trajectory-viewer--embedded"
        />
      </div>
    </section>
  );
});

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
