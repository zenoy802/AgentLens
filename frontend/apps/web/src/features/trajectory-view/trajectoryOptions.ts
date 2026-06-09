import type { Trajectory } from "@/api/types";

export interface TrajectoryOption {
  key: string;
  label: string;
  trajectory: Trajectory;
}

export function getTrajectoryOptions(trajectories: Trajectory[]): TrajectoryOption[] {
  const groupKeyCounts = countGroupKeys(trajectories);

  return trajectories.map((trajectory, index) => ({
    key: String(index),
    label: getTrajectoryLabel(trajectory, index, groupKeyCounts),
    trajectory,
  }));
}

function countGroupKeys(trajectories: Trajectory[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const trajectory of trajectories) {
    counts.set(trajectory.group_key, (counts.get(trajectory.group_key) ?? 0) + 1);
  }
  return counts;
}

function getTrajectoryLabel(
  trajectory: Trajectory,
  index: number,
  groupKeyCounts: Map<string, number>,
): string {
  if ((groupKeyCounts.get(trajectory.group_key) ?? 0) <= 1) {
    return trajectory.group_key;
  }

  const firstRowIdentity = trajectory.messages[0]?.row_identity;
  const suffix = firstRowIdentity ? `row ${firstRowIdentity}` : `#${index + 1}`;
  return `${trajectory.group_key} (${suffix})`;
}
