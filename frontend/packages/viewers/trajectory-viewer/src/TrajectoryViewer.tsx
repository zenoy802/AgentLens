import { useMemo } from "react";

import { MessageBubble } from "./MessageBubble";
import type {
  MessageClassNameResolver,
  MessageCollapseResolver,
  TrajectoryMessage,
  TrajectoryViewerProps,
} from "./types";

import "./styles.css";

const DEFAULT_AUTO_COLLAPSE_CHAR_LIMIT = 900;
const LENGTH_ESTIMATE_MAX_DEPTH = 8;

export function TrajectoryViewer({
  trajectory,
  renderContent,
  renderCollapsedContent,
  renderToolCalls,
  filterRoles,
  className,
  messageClassName,
  renderMessageActions,
  showHeader = true,
  showMetaLine = false,
  metaFields,
  collapsibleMessages = false,
  defaultMessageCollapsed,
  collapsedContentHeight,
  expandLabel,
  collapseLabel,
}: TrajectoryViewerProps) {
  const messages = useMemo(
    () => filterMessagesByRole(trajectory.messages, filterRoles),
    [filterRoles, trajectory.messages],
  );

  return (
    <section className={joinClassNames("agentlens-trajectory-viewer", className)}>
      {showHeader ? (
        <header className="agentlens-trajectory-header">
          <div>
            <div className="agentlens-trajectory-eyebrow">Trajectory</div>
            <h2 className="agentlens-trajectory-title">{trajectory.group_key}</h2>
          </div>
          <div className="agentlens-trajectory-count">
            {messages.length === trajectory.message_count
              ? `${trajectory.message_count} messages`
              : `${messages.length} / ${trajectory.message_count} messages`}
          </div>
        </header>
      ) : null}
      <div className="agentlens-trajectory-stream">
        {messages.map(({ message, originalIndex }) => (
          <MessageBubble
            key={`${message.row_identity}:${originalIndex}`}
            message={message}
            renderContent={renderContent}
            renderCollapsedContent={renderCollapsedContent}
            renderToolCalls={renderToolCalls}
            actions={renderMessageActions?.(message, originalIndex)}
            showMetaLine={showMetaLine}
            metaFields={metaFields}
            collapsible={collapsibleMessages}
            defaultCollapsed={resolveDefaultCollapsed(message, defaultMessageCollapsed)}
            collapsedContentHeight={collapsedContentHeight}
            expandLabel={expandLabel}
            collapseLabel={collapseLabel}
            className={resolveMessageClassName(message, originalIndex, messageClassName)}
          />
        ))}
      </div>
    </section>
  );
}

function filterMessagesByRole(
  messages: TrajectoryMessage[],
  filterRoles: string[] | undefined,
): Array<{ message: TrajectoryMessage; originalIndex: number }> {
  const indexedMessages = messages.map((message, originalIndex) => ({
    message,
    originalIndex,
  }));

  if (filterRoles === undefined) {
    return indexedMessages;
  }

  const allowedRoles = new Set(filterRoles.map(normalizeRole));
  return indexedMessages.filter(({ message }) =>
    allowedRoles.has(normalizeRole(message.role)),
  );
}

function normalizeRole(role: string): string {
  return role.trim().toLowerCase() || "unknown";
}

function resolveDefaultCollapsed(
  message: TrajectoryMessage,
  resolver: MessageCollapseResolver | undefined,
): boolean {
  if (typeof resolver === "function") {
    return resolver(message);
  }
  if (typeof resolver === "boolean") {
    return resolver;
  }
  return messageExceedsLength(message, DEFAULT_AUTO_COLLAPSE_CHAR_LIMIT);
}

function resolveMessageClassName(
  message: TrajectoryMessage,
  originalIndex: number,
  resolver: MessageClassNameResolver | undefined,
): string | undefined {
  if (typeof resolver === "function") {
    return resolver(message, originalIndex);
  }
  return resolver;
}

function messageExceedsLength(message: TrajectoryMessage, limit: number): boolean {
  const contentLength = estimateValueLengthUpTo(
    message.content,
    limit,
    new WeakSet<object>(),
    0,
  );
  if (contentLength > limit) {
    return true;
  }
  return (
    contentLength +
      estimateValueLengthUpTo(
        message.tool_calls,
        limit - contentLength,
        new WeakSet<object>(),
        0,
      ) >
    limit
  );
}

function estimateValueLengthUpTo(
  value: unknown,
  limit: number,
  seen: WeakSet<object>,
  depth: number,
): number {
  if (value === undefined || value === null) {
    return 0;
  }
  if (typeof value === "string") {
    return depth === 0
      ? Math.min(value.length, limit + 1)
      : estimateJsonStringLengthUpTo(value, limit);
  }
  if (typeof value !== "object") {
    return Math.min(String(value).length, limit + 1);
  }
  if (seen.has(value) || depth >= LENGTH_ESTIMATE_MAX_DEPTH) {
    return limit + 1;
  }

  seen.add(value);
  let total = 2;
  try {
    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        total += index > 0 ? 1 : 0;
        if (total > limit) {
          return limit + 1;
        }
        total += estimateValueLengthUpTo(value[index], limit - total, seen, depth + 1);
        if (total > limit) {
          return limit + 1;
        }
      }
      return total;
    }

    let hasPreviousEntry = false;
    const record = value as Record<string, unknown>;
    for (const key in record) {
      if (!Object.prototype.hasOwnProperty.call(record, key)) {
        continue;
      }
      total += hasPreviousEntry ? 1 : 0;
      hasPreviousEntry = true;
      if (total > limit) {
        return limit + 1;
      }
      total += estimateJsonStringLengthUpTo(key, limit - total) + 1;
      if (total > limit) {
        return limit + 1;
      }
      total += estimateValueLengthUpTo(record[key], limit - total, seen, depth + 1);
      if (total > limit) {
        return limit + 1;
      }
    }
    return total;
  } finally {
    seen.delete(value);
  }
}

function estimateJsonStringLengthUpTo(value: string, limit: number): number {
  let total = 2;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index] ?? "";
    const code = character.charCodeAt(0);
    total +=
      code < 0x20 ? 6 : character === '"' || character === "\\" ? 2 : 1;
    if (total > limit) {
      return limit + 1;
    }
  }
  return total;
}

function joinClassNames(...names: Array<string | undefined | false>): string {
  return names.filter(Boolean).join(" ");
}
