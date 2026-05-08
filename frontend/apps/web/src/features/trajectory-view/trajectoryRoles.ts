import type { Trajectory } from "@/api/types";

export function getTrajectoryRoles(trajectories: Trajectory[]): string[] {
  const roles = new Map<string, string>();
  for (const trajectory of trajectories) {
    for (const message of trajectory.messages) {
      const normalized = normalizeTrajectoryRole(message.role);
      if (!roles.has(normalized)) {
        roles.set(normalized, message.role.trim() || "unknown");
      }
    }
  }
  return Array.from(roles.values());
}

export function normalizeTrajectoryRole(role: string): string {
  return role.trim().toLowerCase() || "unknown";
}
