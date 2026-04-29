import { useEffect, useMemo, useState } from "react";
import { TrajectoryViewer } from "@agentlens/trajectory-viewer";
import type { Trajectory } from "@agentlens/trajectory-viewer";

import { cn } from "@/lib/utils";

interface SingleTrajectoryViewProps {
  trajectory: Trajectory;
  className?: string;
}

const DEFAULT_META_FIELDS = ["created_at", "latency", "latency_ms", "duration_ms"];

export function SingleTrajectoryView({ trajectory, className }: SingleTrajectoryViewProps) {
  const roles = useMemo(() => getRoles(trajectory), [trajectory]);
  const metaFields = useMemo(() => getMetaFields(trajectory), [trajectory]);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(roles);
  const activeRoles = selectedRoles.length === roles.length ? undefined : selectedRoles;

  useEffect(() => {
    setSelectedRoles(roles);
  }, [roles]);

  function toggleRole(role: string) {
    setSelectedRoles((current) => {
      if (current.includes(role)) {
        return current.filter((item) => item !== role);
      }
      return [...current, role];
    });
  }

  return (
    <div
      className={cn(
        "flex h-[620px] min-h-0 flex-col rounded-lg border bg-background",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/40 px-3 py-2">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Role filter
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            {roles.map((role) => (
              <label
                key={role}
                className="inline-flex items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-xs font-medium"
              >
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={selectedRoles.includes(role)}
                  onChange={() => toggleRole(role)}
                />
                {role}
              </label>
            ))}
          </div>
        </div>
        <button
          type="button"
          className="rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          onClick={() => setSelectedRoles(roles)}
        >
          全部显示
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <TrajectoryViewer
          trajectory={trajectory}
          filterRoles={activeRoles}
          showMetaLine
          metaFields={metaFields}
        />
      </div>
    </div>
  );
}

function getRoles(trajectory: Trajectory): string[] {
  const roles = new Map<string, string>();
  for (const message of trajectory.messages) {
    const normalized = message.role.trim().toLowerCase() || "unknown";
    if (!roles.has(normalized)) {
      roles.set(normalized, message.role || "unknown");
    }
  }
  return Array.from(roles.values());
}

function getMetaFields(trajectory: Trajectory): string[] {
  const fields = new Set(DEFAULT_META_FIELDS);
  for (const message of trajectory.messages) {
    for (const field of Object.keys(message.raw)) {
      if (isTimestampMetaField(field)) {
        fields.add(field);
      }
    }
  }
  return Array.from(fields);
}

function isTimestampMetaField(field: string): boolean {
  return /_at$/i.test(field);
}
