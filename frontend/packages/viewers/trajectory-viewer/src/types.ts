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

export type MessageCollapseResolver = boolean | ((msg: TrajectoryMessage) => boolean);
export type MessageClassNameResolver =
  | string
  | ((msg: TrajectoryMessage, originalIndex: number) => string | undefined);
export type MessageActionRenderer = (msg: TrajectoryMessage, originalIndex: number) => ReactNode;

export interface TrajectoryViewerProps {
  trajectory: Trajectory;
  renderContent?: (msg: TrajectoryMessage) => ReactNode;
  renderToolCalls?: (msg: TrajectoryMessage) => ReactNode;
  filterRoles?: string[];
  className?: string;
  messageClassName?: MessageClassNameResolver;
  renderMessageActions?: MessageActionRenderer;
  showHeader?: boolean;
  showMetaLine?: boolean;
  metaFields?: string[];
  collapsibleMessages?: boolean;
  defaultMessageCollapsed?: MessageCollapseResolver;
  collapsedContentHeight?: number;
  expandLabel?: string;
  collapseLabel?: string;
}
