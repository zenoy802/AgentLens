import type { ReactNode } from "react";

export type Role = "system" | "user" | "assistant" | "tool" | string;

export interface TrajectoryMessage {
  row_identity: string;
  role: string;
  content: unknown;
  tool_calls?: unknown;
  raw: Record<string, unknown>;
}

export interface Trajectory {
  group_key: string;
  message_count: number;
  messages: TrajectoryMessage[];
}

export interface TrajectoryViewerProps {
  trajectory: Trajectory;
  renderContent?: (msg: TrajectoryMessage) => ReactNode;
  renderToolCalls?: (msg: TrajectoryMessage) => ReactNode;
  filterRoles?: string[];
  className?: string;
  messageClassName?: string;
  showMetaLine?: boolean;
  metaFields?: string[];
}
